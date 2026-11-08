"""Owner-only staff account management."""

from functools import wraps
import re

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from database import get_db

users_bp = Blueprint("users", __name__)


def owner_or_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("user", {}).get("role") not in ("Owner", "Admin"):
            flash("Only an owner or admin can review signup requests.", "danger")
            return redirect(url_for("dashboard.dashboard"))
        return f(*args, **kwargs)

    return decorated


@users_bp.route("/users", methods=["GET", "POST"])
@owner_or_admin_required
def users():
    """Review customer signup requests and let owners create staff accounts."""
    conn = get_db()
    if request.method == "POST":
        if session.get("user", {}).get("role") != "Owner":
            conn.close()
            flash("Only the owner can create staff accounts.", "danger")
            return redirect(url_for("users.users"))

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirmation = request.form.get("password_confirmation", "")
        role = request.form.get("role", "")

        if not username or role not in ("Admin", "Employee"):
            flash("Enter a username and choose Admin or Employee.", "danger")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Enter a valid email address.", "danger")
        elif conn.execute(
            "SELECT 1 FROM USERS WHERE lower(Email)=lower(?) LIMIT 1", (email,)
        ).fetchone():
            flash("That email address is already in use.", "danger")
        elif len(password) < 12:
            flash("Passwords must be at least 12 characters.", "danger")
        elif password != password_confirmation:
            flash("The passwords do not match.", "danger")
        else:
            try:
                conn.execute(
                    "INSERT INTO USERS (Username, Password, Email, Role) VALUES (?, ?, ?, ?)",
                    (username, generate_password_hash(password), email, role),
                )
                conn.commit()
                flash(f"{role} account '{username}' ({email}) created.", "success")
            except Exception as error:
                conn.rollback()
                flash(f"Could not create account: {error}", "danger")

    staff = conn.execute(
        "SELECT UserID, Username, Email, Role FROM USERS WHERE Role IN ('Owner','Admin','Employee') ORDER BY "
        "CASE Role WHEN 'Owner' THEN 0 WHEN 'Admin' THEN 1 ELSE 2 END, Username"
    ).fetchall()
    pending_customers = conn.execute(
        """SELECT UserID, FullName, Email
           FROM USERS WHERE Role='Customer' AND ApprovalStatus='Pending'
           ORDER BY UserID"""
    ).fetchall()
    conn.close()
    return render_template(
        "users.html",
        staff=staff,
        pending_customers=pending_customers,
        is_owner=session.get("user", {}).get("role") == "Owner",
    )


@users_bp.post("/users/customer/<int:user_id>/<decision>")
@owner_or_admin_required
def review_customer_signup(user_id, decision):
    """Approve or reject one pending customer signup."""
    if decision not in ("approve", "reject"):
        return "Invalid decision", 400

    approval_status = "Approved" if decision == "approve" else "Rejected"
    conn = get_db()
    cursor = conn.execute(
        """UPDATE USERS SET ApprovalStatus=?
           WHERE UserID=? AND Role='Customer' AND ApprovalStatus='Pending'""",
        (approval_status, user_id),
    )
    conn.commit()
    conn.close()

    if cursor.rowcount:
        flash(f"Customer signup {approval_status.lower()}.", "success")
    else:
        flash("That signup request is no longer pending.", "warning")
    return redirect(url_for("users.users"))
