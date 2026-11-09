"""Owner-only staff account management."""

from functools import wraps
import re
import secrets

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from database import get_db

users_bp = Blueprint("users", __name__)


def owner_or_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("user", {}).get("role") not in ("Owner", "Admin"):
            flash("Only an owner or admin can review account requests.", "danger")
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
    reset_requests = conn.execute(
        """SELECT r.RequestID, r.RequestedAt, u.FullName, u.Email
           FROM PASSWORD_RESET_REQUEST r JOIN USERS u ON u.UserID=r.UserID
           WHERE r.Status='Pending' ORDER BY r.RequestedAt, r.RequestID"""
    ).fetchall()
    conn.close()
    return render_template(
        "users.html",
        staff=staff,
        reset_requests=reset_requests,
        is_owner=session.get("user", {}).get("role") == "Owner",
    )


@users_bp.post("/users/password-reset/<int:request_id>/<action>")
@owner_or_admin_required
def review_password_reset(request_id, action):
    if action not in ("approve", "reject"):
        return redirect(url_for("users.users"))

    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        reset_request = conn.execute(
            """SELECT r.UserID, u.Email
               FROM PASSWORD_RESET_REQUEST r JOIN USERS u ON u.UserID=r.UserID
               WHERE r.RequestID=? AND r.Status='Pending' AND u.Role='Customer'
                 AND u.ApprovalStatus='Approved'""",
            (request_id,),
        ).fetchone()
        if not reset_request:
            conn.rollback()
            flash("That password reset request is no longer pending.", "warning")
            return redirect(url_for("users.users"))

        temporary_password = None
        if action == "approve":
            temporary_password = secrets.token_urlsafe(12)
            conn.execute(
                "UPDATE USERS SET Password=?, MustChangePassword=1 WHERE UserID=?",
                (generate_password_hash(temporary_password), reset_request["UserID"]),
            )
            new_status = "Approved"
        else:
            new_status = "Rejected"
        conn.execute(
            """UPDATE PASSWORD_RESET_REQUEST
               SET Status=?, ReviewedAt=datetime('now'), ReviewedBy=?
               WHERE RequestID=? AND Status='Pending'""",
            (new_status, session["user"]["id"], request_id),
        )
        conn.commit()
    except Exception as error:
        conn.rollback()
        flash(f"Could not review password reset request: {error}", "danger")
        return redirect(url_for("users.users"))
    finally:
        conn.close()

    if temporary_password:
        flash(
            f"Temporary password for {reset_request['Email']} (shown once): {temporary_password}. "
            "Deliver it to the customer through a verified channel.",
            "warning",
        )
    else:
        flash("Password reset request rejected.", "success")
    return redirect(url_for("users.users"))
