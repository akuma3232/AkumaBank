"""Owner-only staff account management."""

from functools import wraps
import re
import secrets

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from database import get_db
from routes.customers import queue_temporary_password

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

        if not username or role not in ("Admin",):
            flash("Enter a username; every staff account is an Admin.", "danger")
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
        "SELECT UserID, Username, Email, Role, ProfilePicture IS NOT NULL AS HasPicture "
        "FROM USERS WHERE Role IN ('Owner','Admin') ORDER BY "
        "CASE Role WHEN 'Owner' THEN 0 ELSE 1 END, Username"
    ).fetchall()
    conn.close()
    return render_template(
        "users.html",
        staff=staff,
        is_owner=session.get("user", {}).get("role") == "Owner",
    )


@users_bp.post("/users/profile-request/<int:request_id>/<action>")
@owner_or_admin_required
def review_profile_request(request_id, action):
    """Approve or reject a customer's requested profile change."""
    if action not in ("approve", "reject"):
        return redirect(url_for("accounts.requests_center", tab="profiles"))

    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        change = conn.execute(
            "SELECT * FROM PROFILE_CHANGE_REQUEST WHERE RequestID=? AND Status='Pending'",
            (request_id,),
        ).fetchone()
        if not change:
            conn.rollback()
            flash("That profile change request is no longer pending.", "warning")
            return redirect(url_for("accounts.requests_center", tab="profiles"))

        if action == "approve":
            conn.execute(
                """UPDATE USERS SET
                   FullName=COALESCE(NULLIF(?, ''), FullName),
                   CustomStatus=?, Pronouns=?, AboutMe=?
                   WHERE UserID=?""",
                (
                    change["FullName"] or "",
                    change["CustomStatus"] or "",
                    change["Pronouns"] or "",
                    change["AboutMe"] or "",
                    change["UserID"],
                ),
            )

        conn.execute(
            """UPDATE PROFILE_CHANGE_REQUEST
               SET Status=?, ReviewedAt=datetime('now'), ReviewedBy=?
               WHERE RequestID=? AND Status='Pending'""",
            ("Approved" if action == "approve" else "Rejected", session["user"]["id"], request_id),
        )
        conn.commit()
        flash(
            "Profile change approved and applied to the customer's card."
            if action == "approve"
            else "Profile change request rejected.",
            "success" if action == "approve" else "info",
        )
    except Exception as error:
        conn.rollback()
        flash(f"Could not review the profile change request: {error}", "danger")
    finally:
        conn.close()

    return redirect(request.referrer or url_for("accounts.requests_center", tab="profiles"))


@users_bp.post("/users/password-reset/<int:request_id>/<action>")
@owner_or_admin_required
def review_password_reset(request_id, action):
    if action not in ("approve", "reject"):
        return redirect(url_for("customers.customers"))

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
            return redirect(url_for("customers.customers"))

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
        return redirect(request.referrer or url_for("accounts.requests_center", tab="passwords"))
    finally:
        conn.close()

    if temporary_password:
        queue_temporary_password(reset_request["Email"], temporary_password)
        flash("Password reset approved. Copy the temporary password from the Temporary Passwords queue and deliver it through a verified channel.", "warning")
    else:
        flash("Password reset request rejected.", "success")
    return redirect(request.referrer or url_for("accounts.requests_center", tab="passwords"))
