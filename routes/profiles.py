"""
Discord-Style Profile Card System for AkumaBank.
Supports animated GIF & PNG profile pictures, customizable banners,
custom status, about me, and Owner-exclusive Discord roles and badges with PNG icons.
"""

import base64
import os
import re
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

from database import DATABASE_DIR, get_db

profiles_bp = Blueprint("profiles", __name__)

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
UPLOAD_ROLE_ICONS_DIR = Path("static/uploads/role_icons")
UPLOAD_ROLE_ICONS_DIR.mkdir(parents=True, exist_ok=True)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


def owner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        if session["user"].get("role") != "Owner":
            flash("Only the Bank Owner has authority to assign or configure Discord roles and badges.", "danger")
            return redirect(url_for("profiles.settings"))
        return f(*args, **kwargs)

    return decorated


def _process_image_upload(file_storage, max_size=(512, 512)):
    """
    Validate and convert an uploaded image or animated GIF to a data URI.
    Preserves animated GIFs without losing frames.
    """
    if not file_storage or not file_storage.filename:
        raise ValueError("No file uploaded.")

    filename = file_storage.filename.lower()
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File extension '.{ext}' not allowed. Please choose a GIF, PNG, JPG, or WebP.")

    raw_bytes = file_storage.stream.read(MAX_IMAGE_BYTES + 1)
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("Image must be 8 MB or smaller.")

    # Validate image with Pillow
    with Image.open(BytesIO(raw_bytes)) as img:
        fmt = (img.format or "").upper()
        if fmt not in {"JPEG", "PNG", "GIF", "WEBP"}:
            raise ValueError("Invalid image format.")

        # If it's an animated GIF, preserve original raw bytes completely
        if fmt == "GIF":
            b64 = base64.b64encode(raw_bytes).decode("ascii")
            return f"data:image/gif;base64,{b64}"

        # Otherwise optimize static image
        img = img.convert("RGBA" if fmt == "PNG" or "A" in img.getbands() else "RGB")
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        out = BytesIO()
        if fmt == "PNG":
            img.save(out, format="PNG", optimize=True)
            mime = "image/png"
        else:
            img.save(out, format="WEBP", quality=88)
            mime = "image/webp"

        b64 = base64.b64encode(out.getvalue()).decode("ascii")
        return f"data:{mime};base64,{b64}"


def get_user_discord_profile(user_id: int):
    """Fetch complete Discord profile data for a user including custom roles and badges."""
    conn = get_db()
    user = conn.execute(
        """SELECT UserID, Username, FullName, Email, Role, ProfilePicture, 
                  BannerImage, BannerColor, AboutMe, CustomStatus, Pronouns
           FROM USERS WHERE UserID=?""",
        (user_id,),
    ).fetchone()
    if not user:
        conn.close()
        return None

    # Fetch assigned custom roles ordered by position
    roles = conn.execute(
        """SELECT r.RoleID, r.Name, r.Color, r.Icon, r.Position
           FROM CUSTOM_ROLE r
           JOIN USER_CUSTOM_ROLE ur ON r.RoleID = ur.RoleID
           WHERE ur.UserID = ?
           ORDER BY r.Position ASC, r.Name ASC""",
        (user_id,),
    ).fetchall()

    # Fetch assigned badges
    badges = conn.execute(
        """SELECT b.BadgeID, b.Code, b.Name, b.Description, b.Icon
           FROM BADGE b
           JOIN USER_BADGE ub ON b.BadgeID = ub.BadgeID
           WHERE ub.UserID = ?
           ORDER BY b.BadgeID ASC""",
        (user_id,),
    ).fetchall()

    # Optional account overview if linked customer
    customer = None
    if user["Email"]:
        customer = conn.execute(
            "SELECT CustomerID, Name FROM CUSTOMER WHERE lower(Email)=lower(?)",
            (user["Email"],),
        ).fetchone()

    accounts = []
    if customer:
        accounts = conn.execute(
            "SELECT AccountID, AccountNumber, AccountType, CardTier, Status, Balance FROM ACCOUNT WHERE CustomerID=?",
            (customer["CustomerID"],),
        ).fetchall()

    conn.close()
    return {
        "user": dict(user),
        "roles": [dict(r) for r in roles],
        "badges": [dict(b) for b in badges],
        "accounts": [dict(a) for a in accounts],
        "customer": dict(customer) if customer else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. ACCOUNT SETTINGS (DISCORD PROFILE CUSTOMIZATION)
# ─────────────────────────────────────────────────────────────────────────────

@profiles_bp.route("/account/settings", methods=["GET"])
@login_required
def settings():
    """Render account settings with live Discord Profile Card preview and controls."""
    user_id = session["user"]["id"]
    profile_data = get_user_discord_profile(user_id)
    if not profile_data:
        session.clear()
        flash("User session expired. Please sign in again.", "warning")
        return redirect(url_for("auth.login"))

    conn = get_db()
    all_roles = conn.execute("SELECT * FROM CUSTOM_ROLE ORDER BY Position ASC, Name ASC").fetchall()
    all_badges = conn.execute("SELECT * FROM BADGE ORDER BY BadgeID ASC").fetchall()
    all_users = conn.execute("SELECT UserID, Username, FullName, Email, Role FROM USERS ORDER BY Role='Owner' DESC, Role='Admin' DESC, Username ASC").fetchall()
    conn.close()

    is_owner = session["user"].get("role") == "Owner"
    return render_template(
        "account_settings.html",
        profile=profile_data,
        all_roles=[dict(r) for r in all_roles],
        all_badges=[dict(b) for b in all_badges],
        all_users=[dict(u) for u in all_users],
        is_owner=is_owner,
    )


@profiles_bp.post("/account/settings/avatar")
@login_required
def upload_avatar():
    """Upload custom profile picture (supports animated GIF, PNG, JPG, WebP)."""
    user_id = session["user"]["id"]
    file = request.files.get("avatar")
    try:
        data_uri = _process_image_upload(file, max_size=(256, 256))
        conn = get_db()
        conn.execute("UPDATE USERS SET ProfilePicture=? WHERE UserID=?", (data_uri, user_id))
        conn.commit()
        conn.close()

        session["user"]["profile_picture"] = data_uri
        flash("Profile picture updated successfully (animated GIFs fully supported)!", "success")
    except Exception as err:
        flash(f"Could not update avatar: {err}", "danger")

    return redirect(url_for("profiles.settings"))


@profiles_bp.post("/account/settings/avatar/remove")
@login_required
def remove_avatar():
    """Remove avatar and reset to default letter placeholder."""
    user_id = session["user"]["id"]
    conn = get_db()
    conn.execute("UPDATE USERS SET ProfilePicture=NULL WHERE UserID=?", (user_id,))
    conn.commit()
    conn.close()

    session["user"]["profile_picture"] = None
    flash("Avatar removed. Default placeholder restored.", "info")
    return redirect(url_for("profiles.settings"))


@profiles_bp.post("/account/settings/banner")
@login_required
def update_banner():
    """Upload custom profile banner (GIF/PNG/JPG) or update solid banner color."""
    user_id = session["user"]["id"]
    banner_file = request.files.get("banner_image")
    banner_color = request.form.get("banner_color", "").strip()

    conn = get_db()
    try:
        # Check if file uploaded
        if banner_file and banner_file.filename:
            banner_data_uri = _process_image_upload(banner_file, max_size=(1024, 400))
            conn.execute(
                "UPDATE USERS SET BannerImage=?, BannerColor=? WHERE UserID=?",
                (banner_data_uri, banner_color or "#5865f2", user_id),
            )
            flash("Discord banner image updated (animated GIFs supported)!", "success")
        elif banner_color:
            conn.execute("UPDATE USERS SET BannerColor=? WHERE UserID=?", (banner_color, user_id))
            flash("Discord banner color updated!", "success")
        conn.commit()
    except Exception as err:
        conn.rollback()
        flash(f"Could not update banner: {err}", "danger")
    finally:
        conn.close()

    return redirect(url_for("profiles.settings"))


@profiles_bp.post("/account/settings/banner/remove")
@login_required
def remove_banner():
    """Remove custom banner image, keeping default color."""
    user_id = session["user"]["id"]
    conn = get_db()
    conn.execute("UPDATE USERS SET BannerImage=NULL WHERE UserID=?", (user_id,))
    conn.commit()
    conn.close()
    flash("Custom banner image removed.", "info")
    return redirect(url_for("profiles.settings"))


@profiles_bp.post("/account/settings/profile-info")
@login_required
def update_profile_info():
    """Update About Me, Custom Status, Pronouns, and Display Name."""
    user_id = session["user"]["id"]
    full_name = request.form.get("full_name", "").strip()
    custom_status = request.form.get("custom_status", "").strip()
    about_me = request.form.get("about_me", "").strip()
    pronouns = request.form.get("pronouns", "").strip()

    conn = get_db()
    conn.execute(
        """UPDATE USERS SET 
           FullName=COALESCE(NULLIF(?, ''), FullName),
           CustomStatus=?,
           AboutMe=?,
           Pronouns=?
           WHERE UserID=?""",
        (full_name, custom_status, about_me, pronouns, user_id),
    )
    conn.commit()
    conn.close()

    if full_name:
        session["user"]["name"] = full_name
        session["user"]["full_name"] = full_name

    flash("Discord profile card details updated successfully!", "success")
    return redirect(url_for("profiles.settings"))


# ─────────────────────────────────────────────────────────────────────────────
# 2. OWNER-EXCLUSIVE DISCORD ROLE & BADGE MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@profiles_bp.post("/account/owner/manage-user-roles/<int:target_user_id>")
@owner_required
def manage_user_roles(target_user_id: int):
    """Owner only: Assign or remove custom roles and badges for any user."""
    conn = get_db()
    target_user = conn.execute("SELECT UserID, Username FROM USERS WHERE UserID=?", (target_user_id,)).fetchone()
    if not target_user:
        conn.close()
        flash("Target user not found.", "danger")
        return redirect(url_for("profiles.settings"))

    # Get selected role IDs and badge IDs from form
    selected_role_ids = request.form.getlist("role_ids")
    selected_badge_ids = request.form.getlist("badge_ids")

    try:
        conn.execute("BEGIN IMMEDIATE")
        # Clear existing
        conn.execute("DELETE FROM USER_CUSTOM_ROLE WHERE UserID=?", (target_user_id,))
        conn.execute("DELETE FROM USER_BADGE WHERE UserID=?", (target_user_id,))

        for rid in selected_role_ids:
            if rid.isdigit():
                conn.execute("INSERT OR IGNORE INTO USER_CUSTOM_ROLE (UserID, RoleID) VALUES (?, ?)", (target_user_id, int(rid)))

        for bid in selected_badge_ids:
            if bid.isdigit():
                conn.execute("INSERT OR IGNORE INTO USER_BADGE (UserID, BadgeID) VALUES (?, ?)", (target_user_id, int(bid)))

        conn.commit()
        flash(f"Roles and badges for user @{target_user['Username']} updated successfully by Owner!", "success")
    except Exception as err:
        conn.rollback()
        flash(f"Could not update roles: {err}", "danger")
    finally:
        conn.close()

    return redirect(request.referrer or url_for("profiles.settings"))


@profiles_bp.post("/account/owner/create-custom-role")
@owner_required
def create_custom_role():
    """Owner only: Create a new custom role with custom color and optional PNG icon."""
    name = request.form.get("name", "").strip()
    color = request.form.get("color", "#5865f2").strip()
    icon_file = request.files.get("icon")

    if not name:
        flash("Role name is required.", "danger")
        return redirect(url_for("profiles.settings"))

    icon_path = None
    if icon_file and icon_file.filename:
        filename = secure_filename(icon_file.filename)
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext != "png":
            flash("Role icons must be transparent PNG files.", "danger")
            return redirect(url_for("profiles.settings"))

        save_name = f"role_{re.sub(r'[^a-zA-Z0-9_]', '', name.lower())}_{os.urandom(3).hex()}.png"
        dest_path = UPLOAD_ROLE_ICONS_DIR / save_name
        icon_file.save(dest_path)
        icon_path = f"uploads/role_icons/{save_name}"

    conn = get_db()
    try:
        max_pos = conn.execute("SELECT COALESCE(MAX(Position), 0) + 1 FROM CUSTOM_ROLE").fetchone()[0]
        conn.execute(
            "INSERT INTO CUSTOM_ROLE (Name, Color, Icon, Position) VALUES (?, ?, ?, ?)",
            (name, color, icon_path, max_pos),
        )
        conn.commit()
        flash(f"Custom role '{name}' created with PNG icon!", "success")
    except Exception as err:
        conn.rollback()
        flash(f"Could not create role: {err}", "danger")
    finally:
        conn.close()

    return redirect(url_for("profiles.settings"))


# ─────────────────────────────────────────────────────────────────────────────
# 3. PUBLIC / MODAL PROFILE CARD API & VIEWS
# ─────────────────────────────────────────────────────────────────────────────

@profiles_bp.route("/user/<int:user_id>/profile")
@login_required
def view_profile(user_id: int):
    """View any user's standalone Discord profile card."""
    profile_data = get_user_discord_profile(user_id)
    if not profile_data:
        abort(404, description="User not found")

    is_owner = session["user"].get("role") == "Owner"
    is_self = session["user"].get("id") == user_id

    conn = get_db()
    all_roles = conn.execute("SELECT * FROM CUSTOM_ROLE ORDER BY Position ASC, Name ASC").fetchall()
    all_badges = conn.execute("SELECT * FROM BADGE ORDER BY BadgeID ASC").fetchall()
    conn.close()

    return render_template(
        "discord_profile.html",
        profile=profile_data,
        is_owner=is_owner,
        is_self=is_self,
        all_roles=[dict(r) for r in all_roles],
        all_badges=[dict(b) for b in all_badges],
    )


@profiles_bp.route("/api/user/<int:user_id>/discord-profile")
@login_required
def api_get_discord_profile(user_id: int):
    """API endpoint returning Discord card JSON data for fast modal popups."""
    profile_data = get_user_discord_profile(user_id)
    if not profile_data:
        return jsonify({"error": "User not found"}), 404

    # Sanitize user dictionary
    user = profile_data["user"]
    safe_user = {
        "user_id": user["UserID"],
        "username": user["Username"],
        "full_name": user["FullName"] or user["Username"],
        "email": user["Email"],
        "role": user["Role"],
        "profile_picture": user["ProfilePicture"],
        "banner_image": user["BannerImage"],
        "banner_color": user["BannerColor"] or "#5865f2",
        "about_me": user["AboutMe"] or "No bio written yet.",
        "custom_status": user["CustomStatus"] or "",
        "pronouns": user["Pronouns"] or "",
    }

    return jsonify({
        "user": safe_user,
        "roles": profile_data["roles"],
        "badges": profile_data["badges"],
        "accounts": profile_data["accounts"],
        "is_owner_viewer": session["user"].get("role") == "Owner",
    })
