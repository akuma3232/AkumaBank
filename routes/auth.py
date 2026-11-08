"""Login and logout routes."""

import re
import uuid

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Handle user login with username/password."""
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
            user = conn.execute(
                """SELECT * FROM USERS
                   WHERE Username=? AND Role IN ('Owner','Admin','Employee')
                     AND ApprovalStatus='Approved'""",
                (identifier,),
            ).fetchone()
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
                "profile_picture": user["ProfilePicture"],
            }
            flash(f"Welcome back, {display_name}!", "success")
            endpoint = "customer_portal.home" if user["Role"] == "Customer" else "dashboard.dashboard"
            return redirect(url_for(endpoint))

        flash("Invalid username or password.", "danger")

    return render_template("login.html", mode=mode)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Accept customer signup requests for manual owner/admin approval."""
    if "user" in session:
        endpoint = "customer_portal.home" if session["user"]["role"] == "Customer" else "dashboard.dashboard"
        return redirect(url_for(endpoint))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")

        if len(full_name) < 2 or len(full_name) > 120:
            flash("Enter your full name (2 to 120 characters).", "danger")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Enter a valid email address.", "danger")
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
                            """UPDATE USERS SET FullName=?, Password=?, ApprovalStatus='Pending'
                               WHERE UserID=?""",
                            (full_name, hashed_password, existing["UserID"]),
                        )
                    else:
                        conn.execute(
                            """INSERT INTO USERS
                               (Username, Password, FullName, Email, ApprovalStatus, Role)
                               VALUES (?, ?, ?, ?, 'Pending', 'Customer')""",
                            (f"customer-{uuid.uuid4().hex}", hashed_password, full_name, email),
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

    return render_template("register.html")


@auth_bp.route("/logout")
def logout():
    """Clear session and redirect to login."""
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("auth.login"))
