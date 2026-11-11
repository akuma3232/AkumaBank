"""
Executive Profile Card & Badge System for AkumaBank.
Features high-resolution PNG badges uploadable by the Bank Owner,
animated GIF avatars, customizable banners, custom status, and bio.
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
UPLOAD_BADGES_DIR = Path("static/uploads/badges")
UPLOAD_BADGES_DIR.mkdir(parents=True, exist_ok=True)


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
            flash("Only the Bank Owner has authority to create, upload, and assign official bank badges.", "danger")
            return redirect(url_for("profiles.settings"))
        return f(*args, **kwargs)

    return decorated


def _process_image_upload(file_storage, max_size=(512, 512)):
    """
    Validate and convert an uploaded image or animated GIF to a data URI.
    Preserves all animated GIF frames without quality or animation loss.
    """
    if not file_storage or not file_storage.filename:
        raise ValueError("No file uploaded.")

    filename = file_storage.filename.lower()
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Extension '.{ext}' is not supported. Please select a GIF, PNG, JPG, or WebP.")

    raw_bytes = file_storage.stream.read(MAX_IMAGE_BYTES + 1)
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("File exceeds 8 MB size limit.")

    with Image.open(BytesIO(raw_bytes)) as img:
        fmt = (img.format or "").upper()
        if fmt not in {"JPEG", "PNG", "GIF", "WEBP"}:
            raise ValueError("Unsupported image file format.")

        # Preserve full animation for GIFs
        if fmt == "GIF":
            b64 = base64.b64encode(raw_bytes).decode("ascii")
            return f"data:image/gif;base64,{b64}"

        # Convert and optimize static images
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


def get_user_profile(user_id: int):
    """Retrieve full user profile data including assigned PNG badges and bank accounts."""
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

    # Fetch assigned badges
    badges = conn.execute(
        """SELECT b.BadgeID, b.Name, b.Description, b.Icon
           FROM BADGE b
           JOIN USER_BADGE ub ON b.BadgeID = ub.BadgeID
           WHERE ub.UserID = ?
           ORDER BY b.BadgeID ASC""",
        (user_id,),
    ).fetchall()

    # Fetch customer accounts if customer
    customer = None
    if user["Email"]:
        customer = conn.execute(
            "SELECT CustomerID, Name, DateOfBirth, NationalID FROM CUSTOMER WHERE lower(Email)=lower(?)",
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
        "badges": [dict(b) for b in badges],
        "accounts": [dict(a) for a in accounts],
        "customer": dict(customer) if customer else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. ACCOUNT SETTINGS & PROFILE MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@profiles_bp.route("/account/settings", methods=["GET"])
@login_required
def settings():
    """Render account settings with live Executive Profile Card preview."""
    user_id = session["user"]["id"]
    profile_data = get_user_profile(user_id)
    if not profile_data:
        session.clear()
        flash("Your session has expired. Please sign in again.", "warning")
        return redirect(url_for("auth.login"))

    conn = get_db()
    all_badges = conn.execute("SELECT * FROM BADGE ORDER BY BadgeID DESC").fetchall()
    all_users = conn.execute(
        "SELECT UserID, Username, FullName, Email, Role FROM USERS ORDER BY Role='Owner' DESC, Role='Admin' DESC, Username ASC"
    ).fetchall()
    conn.close()

    is_owner = session["user"].get("role") == "Owner"
    return render_template(
        "account_settings.html",
        profile=profile_data,
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
        flash("Profile picture updated (animated GIFs fully supported)!", "success")
    except Exception as err:
        flash(f"Could not update avatar: {err}", "danger")

    return redirect(url_for("profiles.settings"))


@profiles_bp.post("/account/settings/avatar/remove")
@login_required
def remove_avatar():
    """Remove avatar and reset to default letter badge."""
    user_id = session["user"]["id"]
    conn = get_db()
    conn.execute("UPDATE USERS SET ProfilePicture=NULL WHERE UserID=?", (user_id,))
    conn.commit()
    conn.close()

    session["user"]["profile_picture"] = None
    flash("Avatar removed. Default profile placeholder restored.", "info")
    return redirect(url_for("profiles.settings"))


@profiles_bp.post("/account/settings/banner")
@login_required
def update_banner():
    """Upload custom banner image/GIF or update solid banner color."""
    user_id = session["user"]["id"]
    banner_file = request.files.get("banner_image")
    banner_color = request.form.get("banner_color", "").strip()

    conn = get_db()
    try:
        if banner_file and banner_file.filename:
            banner_data_uri = _process_image_upload(banner_file, max_size=(1024, 400))
            conn.execute(
                "UPDATE USERS SET BannerImage=?, BannerColor=? WHERE UserID=?",
                (banner_data_uri, banner_color or "#0f172a", user_id),
            )
            flash("Profile banner image updated (animated GIFs supported)!", "success")
        elif banner_color:
            conn.execute("UPDATE USERS SET BannerColor=? WHERE UserID=?", (banner_color, user_id))
            flash("Profile banner color updated!", "success")
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
    """Remove custom banner image, reverting to solid theme color."""
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
    """Update Display Name, Custom Status, Title/Pronouns, and About Me Bio."""
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

    flash("Profile card information updated successfully!", "success")
    return redirect(url_for("profiles.settings"))


# ─────────────────────────────────────────────────────────────────────────────
# 2. OWNER BADGE SYSTEM (UPLOADABLE PNGs & ASSIGNMENT)
# ─────────────────────────────────────────────────────────────────────────────

@profiles_bp.post("/account/owner/badges/create")
@owner_required
def create_badge():
    """Owner only: Upload a new custom badge with a transparent PNG icon."""
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    icon_file = request.files.get("badge_icon")

    if not name:
        flash("Badge name is required.", "danger")
        return redirect(url_for("profiles.settings"))

    if not icon_file or not icon_file.filename:
        flash("Please upload a PNG badge icon file.", "danger")
        return redirect(url_for("profiles.settings"))

    filename = secure_filename(icon_file.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext != "png":
        flash("Badge icon must be a PNG file format.", "danger")
        return redirect(url_for("profiles.settings"))

    try:
        # Validate PNG file with PIL
        raw_bytes = icon_file.stream.read(MAX_IMAGE_BYTES + 1)
        if len(raw_bytes) > MAX_IMAGE_BYTES:
            raise ValueError("PNG icon exceeds 8 MB.")

        with Image.open(BytesIO(raw_bytes)) as img:
            if (img.format or "").upper() != "PNG":
                raise ValueError("Uploaded file is not a valid PNG image.")
            # Convert to optimized Base64 PNG data URI for maximum portability and zero-broken-link safety
            img = img.convert("RGBA")
            img.thumbnail((64, 64), Image.Resampling.LANCZOS)
            out = BytesIO()
            img.save(out, format="PNG", optimize=True)
            icon_data_uri = f"data:image/png;base64,{base64.b64encode(out.getvalue()).decode('ascii')}"

        conn = get_db()
        code = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower()) + "_" + os.urandom(3).hex()
        badge_cols = {row["name"] for row in conn.execute("PRAGMA table_info(BADGE)")}
        if "Code" in badge_cols:
            conn.execute(
                "INSERT INTO BADGE (Code, Name, Description, Icon) VALUES (?, ?, ?, ?)",
                (code, name, description, icon_data_uri),
            )
        else:
            conn.execute(
                "INSERT INTO BADGE (Name, Description, Icon) VALUES (?, ?, ?)",
                (name, description, icon_data_uri),
            )
        conn.commit()
        conn.close()
        flash(f"Official PNG badge '{name}' uploaded and registered successfully!", "success")
    except Exception as err:
        flash(f"Could not upload badge icon: {err}", "danger")

    return redirect(url_for("profiles.settings"))


@profiles_bp.post("/account/owner/badges/<int:badge_id>/delete")
@owner_required
def delete_badge(badge_id: int):
    """Owner only: Delete an uploaded badge from the bank registry."""
    conn = get_db()
    badge = conn.execute("SELECT Name FROM BADGE WHERE BadgeID=?", (badge_id,)).fetchone()
    if not badge:
        conn.close()
        flash("Badge not found.", "warning")
        return redirect(url_for("profiles.settings"))

    conn.execute("DELETE FROM USER_BADGE WHERE BadgeID=?", (badge_id,))
    conn.execute("DELETE FROM BADGE WHERE BadgeID=?", (badge_id,))
    conn.commit()
    conn.close()
    flash(f"Badge '{badge['Name']}' has been removed from the registry.", "info")
    return redirect(url_for("profiles.settings"))


@profiles_bp.post("/account/owner/badges/assign/<int:target_user_id>")
@owner_required
def assign_user_badges(target_user_id: int):
    """Owner only: Assign or remove uploaded PNG badges for any user."""
    conn = get_db()
    target_user = conn.execute("SELECT UserID, Username FROM USERS WHERE UserID=?", (target_user_id,)).fetchone()
    if not target_user:
        conn.close()
        flash("Target user not found.", "danger")
        return redirect(url_for("profiles.settings"))

    selected_badge_ids = request.form.getlist("badge_ids")

    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM USER_BADGE WHERE UserID=?", (target_user_id,))
        for bid in selected_badge_ids:
            if bid.isdigit():
                conn.execute("INSERT OR IGNORE INTO USER_BADGE (UserID, BadgeID) VALUES (?, ?)", (target_user_id, int(bid)))
        conn.commit()
        flash(f"Official badges for @{target_user['Username']} updated successfully by Bank Owner!", "success")
    except Exception as err:
        conn.rollback()
        flash(f"Could not update badges: {err}", "danger")
    finally:
        conn.close()

    return redirect(request.referrer or url_for("profiles.settings"))


# ─────────────────────────────────────────────────────────────────────────────
# 3. PROFILE VIEWS & GLOBAL MODAL API
# ─────────────────────────────────────────────────────────────────────────────

@profiles_bp.route("/user/<int:user_id>/profile")
@login_required
def view_profile(user_id: int):
    """View any user's standalone Executive Profile Card."""
    profile_data = get_user_profile(user_id)
    if not profile_data:
        abort(404, description="User not found")

    is_owner = session["user"].get("role") == "Owner"
    is_self = session["user"].get("id") == user_id

    conn = get_db()
    all_badges = conn.execute("SELECT * FROM BADGE ORDER BY BadgeID ASC").fetchall()
    conn.close()

    return render_template(
        "profile_card.html",
        profile=profile_data,
        is_owner=is_owner,
        is_self=is_self,
        all_badges=[dict(b) for b in all_badges],
    )


@profiles_bp.route("/api/user/<int:user_id>/profile")
@login_required
def api_get_profile(user_id: int):
    """API endpoint returning sanitized profile card JSON for fast modal popups."""
    profile_data = get_user_profile(user_id)
    if not profile_data:
        return jsonify({"error": "User profile not found"}), 404

    u = profile_data["user"]
    safe_user = {
        "user_id": u["UserID"],
        "username": u["Username"],
        "full_name": u["FullName"] or u["Username"],
        "email": u["Email"],
        "role": u["Role"],
        "profile_picture": u["ProfilePicture"],
        "banner_image": u["BannerImage"],
        "banner_color": u["BannerColor"] or "#0f172a",
        "about_me": u["AboutMe"] or "Verified member of AkumaBank Moroccan banking suite.",
        "custom_status": u["CustomStatus"] or "",
        "pronouns": u["Pronouns"] or "",
    }

    # Format badges with data URIs or paths
    formatted_badges = []
    for b in profile_data["badges"]:
        icon_url = b["Icon"] if b["Icon"].startswith("data:") else url_for("static", filename="img/" + b["Icon"])
        formatted_badges.append({
            "badge_id": b["BadgeID"],
            "name": b["Name"],
            "description": b["Description"] or "",
            "icon_url": icon_url,
        })

    return jsonify({
        "user": safe_user,
        "badges": formatted_badges,
        "accounts": profile_data["accounts"],
        "is_owner_viewer": session["user"].get("role") == "Owner",
    })
