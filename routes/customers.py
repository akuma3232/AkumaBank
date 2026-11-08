"""
routes/customers.py - Full CRUD for Customer management
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db
from functools import wraps

customers_bp = Blueprint("customers", __name__)


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
    conn.close()
    return render_template("customers.html", customers=rows, search=search)


@customers_bp.route("/customers/add", methods=["POST"])
@login_required
def add_customer():
    """Add a new customer."""
    data = request.form
    name    = data.get("name","").strip()
    dob     = data.get("dob","").strip()
    email   = data.get("email","").strip()
    phone   = data.get("phone","").strip()
    address = data.get("address","").strip()
    national_id = data.get("national_id","").strip()

    if not all([name, dob, email, phone, address, national_id]):
        flash("All fields are required.", "danger")
        return redirect(url_for("customers.customers"))

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO CUSTOMER (Name,DateOfBirth,Email,Phone,Address,NationalID) VALUES (?,?,?,?,?,?)",
            (name, dob, email, phone, address, national_id),
        )
        conn.commit()
        flash(f"Customer '{name}' added successfully.", "success")
    except Exception as e:
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
