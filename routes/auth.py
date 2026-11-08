"""Login and logout routes."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Handle user login with username/password."""
    if "user" in session:
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please enter both username and password.", "danger")
            return render_template("login.html")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM USERS WHERE Username=?",
            (username,),
        ).fetchone()

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
            session["user"] = {
                "id": user["UserID"],
                "username": user["Username"],
                "role": user["Role"],
                "profile_picture": user["ProfilePicture"],
            }
            flash(f"Welcome back, {user['Username']}!", "success")
            return redirect(url_for("dashboard.dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    """Clear session and redirect to login."""
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("auth.login"))
