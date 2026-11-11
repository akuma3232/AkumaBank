"""
routes/customers.py - Full CRUD for Customer management
"""

import secrets
import sqlite3
import uuid
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash

from database import get_db

customers_bp = Blueprint("customers", __name__)


def queue_temporary_password(email, password):
    delivery_id = secrets.token_urlsafe(12)
    deliveries = session.get("pending_temporary_passwords", [])
    deliveries.append({"id": delivery_id, "email": email, "password": password})
    session["pending_temporary_passwords"] = deliveries


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@customers_bp.route("/customers")
@login_required
def customers():
    """List all customers with optional search."""
    search = request.args.get("q", "").strip()
    conn = get_db()
    if search:
        rows = conn.execute("""
            SELECT c.*,
                   COUNT(a.AccountID) AS account_count,
                   COALESCE(SUM(a.Balance), 0) AS total_balance
            FROM CUSTOMER c
            LEFT JOIN ACCOUNT a ON c.CustomerID = a.CustomerID
            WHERE c.Name LIKE ? OR c.Email LIKE ? OR c.Phone LIKE ?
            GROUP BY c.CustomerID
            ORDER BY c.Name
        """, (f"%{search}%", f"%{search}%", f"%{search}%")).fetchall()
    else:
        rows = conn.execute("""
            SELECT c.*,
                   COUNT(a.AccountID) AS account_count,
                   COALESCE(SUM(a.Balance), 0) AS total_balance
            FROM CUSTOMER c
            LEFT JOIN ACCOUNT a ON c.CustomerID = a.CustomerID
            GROUP BY c.CustomerID
            ORDER BY c.Name
        """).fetchall()
    can_review_signups = session.get("user", {}).get("role") in ("Owner", "Admin")
    pending_signups = []
    reset_requests = []
    if can_review_signups:
        pending_signups = conn.execute(
            """SELECT UserID, FullName, Email, DateOfBirth, Phone, Address, NationalID
               FROM USERS WHERE Role='Customer' AND ApprovalStatus='Pending'
               ORDER BY UserID"""
        ).fetchall()
        reset_requests = conn.execute(
            """SELECT r.RequestID, r.RequestedAt, u.FullName, u.Email
               FROM PASSWORD_RESET_REQUEST r JOIN USERS u ON u.UserID=r.UserID
               WHERE r.Status='Pending' ORDER BY r.RequestedAt, r.RequestID"""
        ).fetchall()
    conn.close()
    return render_template(
        "customers.html",
        customers=rows,
        search=search,
        pending_signups=pending_signups,
        reset_requests=reset_requests,
        pending_temporary_passwords=(
            session.get("pending_temporary_passwords", []) if can_review_signups else []
        ),
        can_review_signups=can_review_signups,
    )


@customers_bp.post("/customers/temporary-password/<delivery_id>/copied")
@login_required
def acknowledge_temporary_password(delivery_id):
    if session.get("user", {}).get("role") not in ("Owner", "Admin"):
        return jsonify({"error": "forbidden"}), 403
    deliveries = session.get("pending_temporary_passwords", [])
    remaining = [item for item in deliveries if item.get("id") != delivery_id]
    if len(remaining) == len(deliveries):
        return jsonify({"error": "not found"}), 404
    session["pending_temporary_passwords"] = remaining
    return jsonify({"ok": True})


@customers_bp.post("/customers/signup/<int:user_id>/<decision>")
@login_required
def review_customer_signup(user_id, decision):
    """Approve a signup by creating its customer profile, or reject it."""
    if session.get("user", {}).get("role") not in ("Owner", "Admin"):
        flash("Only an owner or admin can review customer signups.", "danger")
        return redirect(url_for("customers.customers"))
    if decision not in ("approve", "reject"):
        return "Invalid decision", 400

    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        signup = conn.execute(
            """SELECT FullName, Email, DateOfBirth, Phone, Address, NationalID
               FROM USERS
               WHERE UserID=? AND Role='Customer' AND ApprovalStatus='Pending'""",
            (user_id,),
        ).fetchone()
        if not signup:
            conn.rollback()
            flash("That signup request is no longer pending.", "warning")
            return redirect(request.referrer or url_for("accounts.requests_center", tab="signups"))

        if decision == "reject":
            conn.execute(
                "UPDATE USERS SET ApprovalStatus='Rejected' WHERE UserID=?",
                (user_id,),
            )
            conn.commit()
            flash("Customer signup rejected.", "success")
            return redirect(request.referrer or url_for("accounts.requests_center", tab="signups"))

        duplicate = conn.execute(
            """SELECT 1 FROM CUSTOMER
               WHERE lower(Email)=lower(?) OR upper(NationalID)=upper(?) LIMIT 1""",
            (signup["Email"], signup["NationalID"]),
        ).fetchone()
        if duplicate:
            conn.rollback()
            flash(
                "This signup's email or National ID is already linked to a customer. "
                "Resolve the duplicate before approving it.",
                "danger",
            )
            return redirect(request.referrer or url_for("accounts.requests_center", tab="signups"))

        conn.execute(
            """INSERT INTO CUSTOMER (Name, DateOfBirth, Email, Phone, Address, NationalID)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                signup["FullName"], signup["DateOfBirth"], signup["Email"],
                signup["Phone"], signup["Address"], signup["NationalID"],
            ),
        )
        conn.execute(
            "UPDATE USERS SET ApprovalStatus='Approved' WHERE UserID=?",
            (user_id,),
        )
        conn.commit()
        flash(
            f"Customer '{signup['FullName']}' approved and added. An owner or admin can now open a bank account.",
            "success",
        )
    except sqlite3.IntegrityError as error:
        conn.rollback()
        flash(f"Could not approve signup because of a customer data conflict: {error}", "danger")
    finally:
        conn.close()
    return redirect(request.referrer or url_for("accounts.requests_center", tab="signups"))


@customers_bp.route("/customers/add", methods=["POST"])
@login_required
def add_customer():
    """Add a customer and create a forced-password-change login."""
    if session.get("user", {}).get("role") not in ("Owner", "Admin"):
        flash("Only an owner or admin can create customer accounts.", "danger")
        return redirect(url_for("customers.customers"))

    data = request.form
    name    = data.get("name","").strip()
    dob     = data.get("dob","").strip()
    email   = data.get("email","").strip().lower()
    phone   = data.get("phone","").strip()
    address = data.get("address","").strip()
    national_id = data.get("national_id","").strip().upper()

    if not all([name, dob, email, phone, address, national_id]):
        flash("All fields are required.", "danger")
        return redirect(url_for("customers.customers"))

    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute(
            """SELECT 1 FROM USERS WHERE lower(Email)=lower(?)
               UNION ALL
               SELECT 1 FROM CUSTOMER WHERE lower(Email)=lower(?) LIMIT 1""",
            (email, email),
        ).fetchone():
            conn.rollback()
            flash("That email address is already linked to an account or customer.", "danger")
            return redirect(url_for("customers.customers"))

        conn.execute(
            "INSERT INTO CUSTOMER (Name,DateOfBirth,Email,Phone,Address,NationalID) VALUES (?,?,?,?,?,?)",
            (name, dob, email, phone, address, national_id),
        )
        temporary_password = secrets.token_urlsafe(12)
        conn.execute(
            """INSERT INTO USERS
               (Username, Password, FullName, Email, DateOfBirth, Phone, Address,
                NationalID, ApprovalStatus, MustChangePassword, Role)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Approved', 1, 'Customer')""",
            (
                f"customer-{uuid.uuid4().hex}", generate_password_hash(temporary_password),
                name, email, dob, phone, address, national_id,
            ),
        )
        conn.commit()
        queue_temporary_password(email, temporary_password)
        flash(f"Customer '{name}' created. Copy the temporary password from this page and deliver it through a verified channel.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("customers.customers"))


@customers_bp.route("/customers/edit/<int:cid>", methods=["POST"])
@login_required
def edit_customer(cid):
    """Update customer details."""
    data = request.form
    conn = get_db()
    try:
        conn.execute("""
            UPDATE CUSTOMER SET Name=?, DateOfBirth=?, Email=?, Phone=?, Address=?, NationalID=?
            WHERE CustomerID=?
        """, (data["name"], data["dob"], data["email"], data["phone"],
              data["address"], data["national_id"], cid))
        conn.commit()
        flash("Customer updated successfully.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("customers.customers"))


@customers_bp.route("/customers/delete/<int:cid>", methods=["POST"])
@login_required
def delete_customer(cid):
    """Delete a customer (cascades to accounts, transactions, loans)."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM CUSTOMER WHERE CustomerID=?", (cid,))
        conn.commit()
        flash("Customer deleted.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("customers.customers"))


@customers_bp.route("/customers/get/<int:cid>")
@login_required
def get_customer(cid):
    """Return customer JSON for edit modal."""
    conn = get_db()
    row = conn.execute("SELECT * FROM CUSTOMER WHERE CustomerID=?", (cid,)).fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({}), 404
