"""Owner-only staff account management."""

from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from database import get_db

users_bp = Blueprint("users", __name__)


def owner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("user", {}).get("role") != "Owner":
            flash("Only the owner can manage staff accounts.", "danger")
            return redirect(url_for("dashboard.dashboard"))
        return f(*args, **kwargs)

    return decorated


@users_bp.route("/users", methods=["GET", "POST"])
@owner_required
def users():
    """List staff and create Admin or Employee accounts."""
    conn = get_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password_confirmation = request.form.get("password_confirmation", "")
        role = request.form.get("role", "")

        if not username or role not in ("Admin", "Employee"):
            flash("Enter a username and choose Admin or Employee.", "danger")
        elif len(password) < 12:
            flash("Passwords must be at least 12 characters.", "danger")
        elif password != password_confirmation:
            flash("The passwords do not match.", "danger")
        else:
            try:
                conn.execute(
                    "INSERT INTO USERS (Username, Password, Role) VALUES (?, ?, ?)",
                    (username, generate_password_hash(password), role),
                )
                conn.commit()
                flash(f"{role} account '{username}' created.", "success")
            except Exception as error:
                conn.rollback()
                flash(f"Could not create account: {error}", "danger")

    staff = conn.execute(
        "SELECT UserID, Username, Role FROM USERS ORDER BY "
        "CASE Role WHEN 'Owner' THEN 0 WHEN 'Admin' THEN 1 ELSE 2 END, Username"
    ).fetchall()
    conn.close()
    return render_template("users.html", staff=staff)
