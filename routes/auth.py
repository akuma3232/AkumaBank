"""Login and logout routes."""

import re
import secrets
import time
import uuid
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db

auth_bp = Blueprint("auth", __name__)


def valid_date_of_birth(value):
    try:
        return date.fromisoformat(value) <= date.today()
    except ValueError:
        return False


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Handle customer login by name/email and staff login by username/email."""
    if "user" in session:
        endpoint = "customer_portal.home" if session["user"]["role"] == "Customer" else "dashboard.dashboard"
        return redirect(url_for(endpoint))

    mode = "staff" if request.args.get("mode") == "staff" else "customer"
    if request.method == "POST":
        mode = request.form.get("mode", "customer")
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        if not identifier or not password:
            flash("Please enter your name or email and password.", "danger")
            return render_template("login.html", mode=mode)

        conn = get_db()
        if mode == "staff":
            candidates = conn.execute(
                """SELECT * FROM USERS
                   WHERE (Username=? OR lower(Email)=lower(?))
                     AND Role IN ('Owner','Admin')
                     AND ApprovalStatus='Approved'""",
                (identifier, identifier),
            ).fetchall()
            user = candidates[0] if len(candidates) == 1 else None
            if len(candidates) > 1:
                flash("That identifier matches multiple staff accounts. Use your email address.", "danger")
                conn.close()
                return render_template("login.html", mode=mode)
        else:
            candidates = conn.execute(
                """SELECT * FROM USERS
                   WHERE Role='Customer' AND
                         (lower(Email)=lower(?) OR lower(FullName)=lower(?))""",
                (identifier, identifier),
            ).fetchall()
            user = candidates[0] if len(candidates) == 1 else None
            if len(candidates) > 1:
                flash("More than one account matches that name. Sign in with your email.", "danger")
                conn.close()
                return render_template("login.html", mode=mode)
            if user and user["ApprovalStatus"] != "Approved":
                if user["ApprovalStatus"] != "Pending":
                    user = None

        password_matches = False
        must_change_password = False
        if user:
            stored_password = user["Password"]
            if stored_password.startswith(("scrypt:", "pbkdf2:")):
                password_matches = check_password_hash(stored_password, password)
            else:
                password_matches = stored_password == password
                if password_matches:
                    conn.execute(
                        "UPDATE USERS SET Password=? WHERE UserID=?",
                        (generate_password_hash(password), user["UserID"]),
                    )
                    conn.commit()
            if password_matches and user["MustChangePassword"]:
                unusable_password = secrets.token_urlsafe(32)
                conn.execute(
                    "UPDATE USERS SET Password=? WHERE UserID=?",
                    (generate_password_hash(unusable_password), user["UserID"]),
                )
                conn.commit()
                must_change_password = True
        conn.close()

        if user and password_matches:
            if user["ApprovalStatus"] == "Pending":
                flash("Your signup is waiting for owner or admin approval.", "warning")
                return render_template("login.html", mode=mode)
            display_name = user["FullName"] or user["Username"]
            session["user"] = {
                "id": user["UserID"],
                "username": display_name,
                "email": user["Email"],
                "role": user["Role"],
                # Keep the cookie small: the avatar is served from its own route.
                "has_pfp": bool(user["ProfilePicture"]),
                "avatar_version": int(time.time()),
                "must_change_password": must_change_password,
            }
            if must_change_password:
                flash("Your temporary password was used. Set a new password to continue.", "warning")
                return redirect(url_for("auth.change_password"))
            flash(f"Welcome back, {display_name}!", "success")
            endpoint = "customer_portal.home" if user["Role"] == "Customer" else "dashboard.dashboard"
            return redirect(url_for(endpoint))

        flash("Invalid username or password.", "danger")

    return render_template("login.html", mode=mode)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Queue an eligible customer's password reset for staff review."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        conn = get_db()
        customer = conn.execute(
            """SELECT UserID FROM USERS
               WHERE lower(Email)=lower(?) AND Role='Customer' AND ApprovalStatus='Approved'""",
            (email,),
        ).fetchone()
        if customer:
            conn.execute(
                """INSERT OR IGNORE INTO PASSWORD_RESET_REQUEST (UserID)
                   SELECT ? WHERE NOT EXISTS (
                       SELECT 1 FROM PASSWORD_RESET_REQUEST
                       WHERE UserID=? AND Status='Pending'
                   )""",
                (customer["UserID"], customer["UserID"]),
            )
            conn.commit()
        conn.close()
        flash(
            "If an approved customer account uses that email, its reset request is now awaiting staff review.",
            "success",
        )
        return redirect(url_for("auth.login"))
    return render_template("forgot_password.html")


@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    """Require customers using a one-time password to set a permanent password."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login"))
    if not user.get("must_change_password"):
        endpoint = "customer_portal.home" if user["role"] == "Customer" else "dashboard.dashboard"
        return redirect(url_for(endpoint))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if len(password) < 12:
            flash("Password must be at least 12 characters.", "danger")
        elif password != confirmation:
            flash("The passwords do not match.", "danger")
        else:
            conn = get_db()
            conn.execute(
                "UPDATE USERS SET Password=?, MustChangePassword=0 WHERE UserID=?",
                (generate_password_hash(password), user["id"]),
            )
            conn.commit()
            conn.close()
            session["user"]["must_change_password"] = False
            flash("Your password has been changed.", "success")
            endpoint = "customer_portal.home" if user["role"] == "Customer" else "dashboard.dashboard"
            return redirect(url_for(endpoint))
    return render_template("change_password.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Accept customer signup requests for manual owner/admin approval."""
    if "user" in session:
        endpoint = "customer_portal.home" if session["user"]["role"] == "Customer" else "dashboard.dashboard"
        return redirect(url_for(endpoint))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        date_of_birth = request.form.get("date_of_birth", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        national_id = request.form.get("national_id", "").strip().upper()
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")

        if len(full_name) < 2 or len(full_name) > 120:
            flash("Enter your full name (2 to 120 characters).", "danger")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Enter a valid email address.", "danger")
        elif not valid_date_of_birth(date_of_birth):
            flash("Enter a valid date of birth that is not in the future.", "danger")
        elif not phone or len(phone) > 30:
            flash("Enter a valid phone number (up to 30 characters).", "danger")
        elif not address or len(address) > 250:
            flash("Enter your address (up to 250 characters).", "danger")
        elif not national_id or len(national_id) > 20:
            flash("Enter your National ID/CIN (up to 20 characters).", "danger")
        elif len(password) < 12:
            flash("Password must be at least 12 characters.", "danger")
        elif password != confirmation:
            flash("The passwords do not match.", "danger")
        else:
            conn = get_db()
            existing = conn.execute(
                "SELECT UserID, Role, ApprovalStatus FROM USERS WHERE lower(Email)=lower(?)",
                (email,),
            ).fetchone()
            if existing and (
                existing["Role"] != "Customer" or existing["ApprovalStatus"] != "Rejected"
            ):
                flash("An account or signup request already uses this email.", "danger")
            else:
                try:
                    hashed_password = generate_password_hash(password)
                    if existing:
                        conn.execute(
                            """UPDATE USERS SET FullName=?, Password=?, DateOfBirth=?, Phone=?,
                                      Address=?, NationalID=?, ApprovalStatus='Pending'
                               WHERE UserID=?""",
                            (
                                full_name, hashed_password, date_of_birth, phone,
                                address, national_id, existing["UserID"],
                            ),
                        )
                    else:
                        conn.execute(
                            """INSERT INTO USERS
                               (Username, Password, FullName, Email, DateOfBirth, Phone,
                                Address, NationalID, ApprovalStatus, Role)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', 'Customer')""",
                            (
                                f"customer-{uuid.uuid4().hex}", hashed_password,
                                full_name, email, date_of_birth, phone, address, national_id,
                            ),
                        )
                    conn.commit()
                    flash(
                        "Signup request submitted. An owner or admin must approve it before you can sign in.",
                        "success",
                    )
                    conn.close()
                    return redirect(url_for("auth.login"))
                except Exception as error:
                    conn.rollback()
                    flash(f"Could not submit signup request: {error}", "danger")
            conn.close()

    return render_template("register.html", today=date.today().isoformat())


@auth_bp.route("/logout")
def logout():
    """Clear session and redirect to login."""
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("auth.login"))
