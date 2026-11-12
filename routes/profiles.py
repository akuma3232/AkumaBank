"""
Executive Profile Card, Role & Badge System for AkumaBank.
Features high-resolution PNG badges and PNG role icons managed by the Bank Owner,
custom assignable profile roles with colors, animated GIF avatars, banners,
custom status, and bio.
"""

import base64
import mimetypes
import os
import re
import time
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from PIL import Image, ImageSequence
from werkzeug.utils import secure_filename

from database import (
    BILLING_MONTH_KEY,
    REVENUE_ACCOUNT_KEY,
    bill_subscriptions,
    billing_period_start,
    get_bank_setting,
    get_db,
    set_bank_setting,
)
from morocco_banking import format_moroccan_rib

profiles_bp = Blueprint("profiles", __name__)

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
UPLOAD_BADGES_DIR = Path("static/uploads/badges")
UPLOAD_BADGES_DIR.mkdir(parents=True, exist_ok=True)

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

DEFAULT_BADGE_COLOR = "#5865f2"
DEFAULT_ROLE_COLOR = "#5865f2"


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
            flash("Only the Bank Owner has authority to manage roles and official bank badges.", "danger")
            return redirect(url_for("profiles.settings"))
        return f(*args, **kwargs)

    return decorated


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _safe_color(value: str, fallback: str = DEFAULT_BADGE_COLOR) -> str:
    """Return a validated hex color, falling back when the input is invalid."""
    value = (value or "").strip()
    return value.lower() if HEX_COLOR_RE.match(value) else fallback


def _icon_meta(icon: str):
    """
    Resolve a stored icon value into a displayable image URL.
    Supports Base64 data URIs, bundled PNG paths (img/badges/...) and absolute URLs.
    Glyph (Bootstrap icon) values are retired and resolve to nothing.
    """
    icon = (icon or "").strip()
    if not icon or icon.startswith(("bi ", "bi-")):
        return {"icon_url": None}
    if icon.startswith(("data:", "http://", "https://")):
        return {"icon_url": icon}
    return {"icon_url": url_for("static", filename="img/" + icon)}


def _decorate_badge(row) -> dict:
    badge = dict(row)
    badge["icon_url"] = _icon_meta(badge.get("Icon"))["icon_url"]
    badge["Color"] = badge.get("Color") or DEFAULT_BADGE_COLOR
    return badge


def _decorate_role(row) -> dict:
    """Normalise a role row. Roles use an uploaded PNG icon (or a color dot)."""
    role = dict(row)
    role["icon_url"] = _icon_meta(role.pop("Icon", None))["icon_url"]
    role["Color"] = role.get("Color") or DEFAULT_ROLE_COLOR
    return role


def _process_image_upload(file_storage, max_size=(512, 512)):
    """
    Validate, downscale and compress an uploaded image into a compact data URI.
    Animated GIFs keep every frame (resized), static images become WebP so they
    stay small enough to store in the database and serve quickly.
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

        # Animated GIF: resize every frame and keep the animation intact.
        if fmt == "GIF" and getattr(img, "is_animated", False):
            frame_count = getattr(img, "n_frames", 1)
            if frame_count > 150:
                raise ValueError("Animated GIF has too many frames (max 150). Please use a shorter animation.")

            frames, durations = [], []
            for frame in ImageSequence.Iterator(img):
                durations.append(frame.info.get("duration", img.info.get("duration", 80)) or 80)
                resized = frame.convert("RGBA")
                resized.thumbnail(max_size, Image.Resampling.LANCZOS)
                frames.append(resized)

            out = BytesIO()
            frames[0].save(
                out,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=img.info.get("loop", 0),
                disposal=2,
                optimize=True,
            )
            b64 = base64.b64encode(out.getvalue()).decode("ascii")
            return f"data:image/gif;base64,{b64}"

        # Static image (including single-frame GIF): normalise to WebP.
        img = img.convert("RGBA" if "A" in img.getbands() or fmt == "PNG" else "RGB")
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        out = BytesIO()
        img.save(out, format="WEBP", quality=85, method=6)
        b64 = base64.b64encode(out.getvalue()).decode("ascii")
        return f"data:image/webp;base64,{b64}"


def _stored_icon_from_png(file_storage, label: str = "Badge icon") -> str:
    """Validate an uploaded PNG and return an optimized Base64 data URI."""
    if not file_storage or not file_storage.filename:
        raise ValueError(f"No {label.lower()} supplied.")

    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext != "png":
        raise ValueError(f"{label} must be a PNG file format.")

    raw_bytes = file_storage.stream.read(MAX_IMAGE_BYTES + 1)
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        raise ValueError(f"{label} exceeds 8 MB.")

    with Image.open(BytesIO(raw_bytes)) as img:
        if (img.format or "").upper() != "PNG":
            raise ValueError(f"{label} is not a valid PNG image.")
        img = img.convert("RGBA")
        img.thumbnail((64, 64), Image.Resampling.LANCZOS)
        out = BytesIO()
        img.save(out, format="PNG", optimize=True)
        return f"data:image/png;base64,{base64.b64encode(out.getvalue()).decode('ascii')}"


def get_user_profile(user_id: int):
    """Retrieve full user profile data including roles, badges and bank accounts."""
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

    # Fetch assigned badges (with grant date)
    badges = conn.execute(
        """SELECT b.BadgeID, b.Code, b.Name, b.Description, b.Icon, b.Color, ub.GrantedAt
           FROM BADGE b
           JOIN USER_BADGE ub ON b.BadgeID = ub.BadgeID
           WHERE ub.UserID = ?
           ORDER BY b.BadgeID ASC""",
        (user_id,),
    ).fetchall()

    # Fetch assigned custom profile roles
    roles = conn.execute(
        """SELECT r.RoleID, r.Name, r.Color, r.Icon, r.Position
           FROM CUSTOM_ROLE r
           JOIN USER_CUSTOM_ROLE ur ON r.RoleID = ur.RoleID
           WHERE ur.UserID = ?
           ORDER BY r.Position ASC, r.RoleID ASC""",
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
        "roles": [_decorate_role(r) for r in roles],
        "badges": [_decorate_badge(b) for b in badges],
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

    is_owner = session["user"].get("role") == "Owner"
    is_customer = session["user"].get("role") == "Customer"

    # Customers cannot edit their card directly: changes go through an
    # owner/admin approval request. Show their latest request (and preview
    # the proposed values while it is still pending).
    profile_request = None
    if is_customer:
        conn = get_db()
        profile_request = conn.execute(
            "SELECT * FROM PROFILE_CHANGE_REQUEST WHERE UserID=? ORDER BY RequestID DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        conn.close()
        if profile_request and profile_request["Status"] == "Pending":
            user_view = profile_data["user"]
            user_view["FullName"] = profile_request["FullName"] or user_view["FullName"]
            user_view["CustomStatus"] = profile_request["CustomStatus"]
            user_view["Pronouns"] = profile_request["Pronouns"]
            user_view["AboutMe"] = profile_request["AboutMe"]

    return render_template(
        "account_settings.html",
        profile=profile_data,
        is_owner=is_owner,
        is_customer=is_customer,
        profile_request=profile_request,
    )


def _owner_studio_context() -> dict:
    """Collect roles, badges, members and assignments for the Owner Studio."""
    conn = get_db()
    all_badges = conn.execute("SELECT * FROM BADGE ORDER BY BadgeID DESC").fetchall()
    all_roles = conn.execute("SELECT * FROM CUSTOM_ROLE ORDER BY Position ASC, RoleID ASC").fetchall()
    all_users = conn.execute(
        "SELECT UserID, Username, FullName, Email, Role, ProfilePicture IS NOT NULL AS HasPicture "
        "FROM USERS ORDER BY Role='Owner' DESC, Role='Admin' DESC, Username ASC"
    ).fetchall()
    user_roles = conn.execute(
        """SELECT ur.UserID, r.RoleID, r.Name, r.Color, r.Icon
           FROM USER_CUSTOM_ROLE ur
           JOIN CUSTOM_ROLE r ON r.RoleID = ur.RoleID
           ORDER BY r.Position ASC, r.RoleID ASC"""
    ).fetchall()
    user_badges = conn.execute(
        """SELECT ub.UserID, b.BadgeID, b.Name, b.Icon, b.Color
           FROM USER_BADGE ub
           JOIN BADGE b ON b.BadgeID = ub.BadgeID"""
    ).fetchall()
    role_member_counts = {
        row["RoleID"]: row["total"]
        for row in conn.execute(
            "SELECT RoleID, COUNT(*) AS total FROM USER_CUSTOM_ROLE GROUP BY RoleID"
        )
    }

    # Time management: revenue settlement account and subscription billing history.
    revenue_account = None
    revenue_raw = get_bank_setting(conn, REVENUE_ACCOUNT_KEY)
    if revenue_raw:
        try:
            revenue_account = conn.execute(
                "SELECT a.AccountID, a.AccountNumber, a.Balance, a.Status, c.Name AS CustomerName "
                "FROM ACCOUNT a LEFT JOIN CUSTOMER c ON c.CustomerID = a.CustomerID "
                "WHERE a.AccountID=?",
                (int(revenue_raw),),
            ).fetchone()
        except (TypeError, ValueError):
            revenue_account = None

    billing_history = conn.execute(
        """SELECT BillingPeriod,
                  COUNT(*) AS total,
                  COALESCE(SUM(CASE WHEN Status='Posted' THEN Amount END), 0) AS collected,
                  COALESCE(SUM(CASE WHEN Status='Unpaid' THEN 1 ELSE 0 END), 0) AS unpaid
           FROM SUBSCRIPTION_CHARGE
           GROUP BY BillingPeriod
           ORDER BY BillingPeriod DESC
           LIMIT 6"""
    ).fetchall()
    recent_charges = conn.execute(
        """SELECT sc.BillingPeriod, sc.Amount, sc.Status, sc.TierName, a.AccountNumber
           FROM SUBSCRIPTION_CHARGE sc
           JOIN ACCOUNT a ON a.AccountID = sc.AccountID
           ORDER BY sc.ChargeID DESC
           LIMIT 8"""
    ).fetchall()
    last_billed = get_bank_setting(conn, BILLING_MONTH_KEY)
    next_period = billing_period_start(conn)
    conn.close()

    role_map = {}
    for row in user_roles:
        role_map.setdefault(row["UserID"], []).append(_decorate_role(row))
    badge_map = {}
    for row in user_badges:
        badge_map.setdefault(row["UserID"], []).append(_decorate_badge(row))

    return {
        "all_badges": [_decorate_badge(b) for b in all_badges],
        "all_roles": [_decorate_role(r) for r in all_roles],
        "all_users": [dict(u) for u in all_users],
        "user_role_map": role_map,
        "user_badge_map": badge_map,
        "role_member_counts": role_member_counts,
        "billing": {
            "revenue": dict(revenue_account) if revenue_account else None,
            "last_billed": last_billed,
            "next_period": next_period,
            "history": [dict(row) for row in billing_history],
            "charges": [dict(row) for row in recent_charges],
        },
    }


@profiles_bp.route("/owner/studio", methods=["GET"])
@owner_required
def owner_studio():
    """Dedicated Owner Studio: create roles & badges and assign them to members."""
    return render_template("owner_studio.html", **_owner_studio_context())


@profiles_bp.post("/owner/studio/revenue-account")
@owner_required
def set_revenue_account():
    """Nominate the account that receives bank fees and subscription revenue."""
    rib = "".join((request.form.get("rib") or "").split())
    conn = get_db()
    try:
        if not rib:
            conn.execute("DELETE FROM BANK_SETTING WHERE Key=?", (REVENUE_ACCOUNT_KEY,))
            conn.commit()
            flash("Bank revenue account cleared. Fees are no longer credited to a settlement account.", "info")
        else:
            account = conn.execute(
                "SELECT AccountID, AccountNumber, Status FROM ACCOUNT WHERE REPLACE(AccountNumber,' ','')=?",
                (rib,),
            ).fetchone()
            if not account:
                flash("No bank account matches that RIB. Copy the 24-digit RIB from the Accounts page.", "danger")
            elif account["Status"] != "Active":
                flash("That account is not active, so it cannot hold bank revenue.", "danger")
            else:
                set_bank_setting(conn, REVENUE_ACCOUNT_KEY, account["AccountID"])
                conn.commit()
                flash(
                    f"Bank revenue now settles into RIB {format_moroccan_rib(account['AccountNumber'])}.",
                    "success",
                )
    except Exception as error:
        conn.rollback()
        flash(f"Could not save the revenue account: {error}", "danger")
    finally:
        conn.close()
    return redirect(url_for("profiles.owner_studio"))


@profiles_bp.post("/owner/studio/billing/advance")
@owner_required
def advance_billing_month():
    """Bill one more month of card subscriptions into the revenue account."""
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        result = bill_subscriptions(conn)
        if not result["success"]:
            conn.rollback()
            flash(result["message"], "danger")
        else:
            conn.commit()
            flash(result["message"], "success")
    except Exception as error:
        conn.rollback()
        flash(f"Billing run failed: {error}", "danger")
    finally:
        conn.close()
    return redirect(url_for("profiles.owner_studio"))


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

        # Never place the image itself in the session cookie: only a small flag
        # and a version so every page can request the avatar from its route.
        session["user"]["has_pfp"] = True
        session["user"]["avatar_version"] = int(time.time())
        flash("Profile picture updated and applied across the bank!", "success")
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

    session["user"]["has_pfp"] = False
    session["user"]["avatar_version"] = int(time.time())
    flash("Avatar removed. Default profile placeholder restored.", "info")
    return redirect(url_for("profiles.settings"))


def _stored_image_response(stored: str):
    """Return a stored profile image (data URI or legacy file path) as a response."""
    if not stored:
        abort(404)

    if stored.startswith("data:"):
        try:
            header, encoded = stored.split(",", 1)
            mime = header[5:].split(";", 1)[0] or "image/webp"
            payload = base64.b64decode(encoded)
        except Exception:
            abort(404)
    else:
        filename = secure_filename(stored)
        path = os.path.join("static", "uploads", "avatars", filename)
        if not os.path.isfile(path):
            abort(404)
        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as fh:
            payload = fh.read()

    response = Response(payload, mimetype=mime)
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


@profiles_bp.route("/user/<int:user_id>/avatar")
@login_required
def user_avatar(user_id: int):
    """Serve a member's profile picture from the database (or legacy file path)."""
    conn = get_db()
    row = conn.execute("SELECT ProfilePicture FROM USERS WHERE UserID=?", (user_id,)).fetchone()
    conn.close()
    return _stored_image_response(row["ProfilePicture"] if row else None)


@profiles_bp.route("/user/<int:user_id>/banner")
@login_required
def user_banner(user_id: int):
    """Serve a member's profile banner image from the database."""
    conn = get_db()
    row = conn.execute("SELECT BannerImage FROM USERS WHERE UserID=?", (user_id,)).fetchone()
    conn.close()
    return _stored_image_response(row["BannerImage"] if row else None)


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
    """Update profile details, or queue the change for approval when a customer asks."""
    user_id = session["user"]["id"]
    full_name = request.form.get("full_name", "").strip()
    custom_status = request.form.get("custom_status", "").strip()
    about_me = request.form.get("about_me", "").strip()
    pronouns = request.form.get("pronouns", "").strip()

    if len(full_name) > 120 or len(custom_status) > 150 or len(pronouns) > 50 or len(about_me) > 500:
        flash("One of the profile fields is longer than allowed. Please shorten it and try again.", "danger")
        return redirect(url_for("profiles.settings"))

    if session["user"].get("role") == "Customer":
        conn = get_db()
        try:
            pending = conn.execute(
                "SELECT RequestID FROM PROFILE_CHANGE_REQUEST WHERE UserID=? AND Status='Pending'",
                (user_id,),
            ).fetchone()
            if pending:
                conn.execute(
                    """UPDATE PROFILE_CHANGE_REQUEST
                       SET FullName=?, CustomStatus=?, Pronouns=?, AboutMe=?, RequestedAt=datetime('now')
                       WHERE RequestID=?""",
                    (full_name, custom_status, pronouns, about_me, pending["RequestID"]),
                )
            else:
                conn.execute(
                    """INSERT INTO PROFILE_CHANGE_REQUEST (UserID, FullName, CustomStatus, Pronouns, AboutMe)
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_id, full_name, custom_status, pronouns, about_me),
                )
            conn.commit()
        except Exception as err:
            conn.rollback()
            flash(f"Could not submit your profile change request: {err}", "danger")
        else:
            flash("Profile change request submitted. The Bank Owner or an Admin must approve it before it appears on your card.", "info")
        finally:
            conn.close()
        return redirect(url_for("profiles.settings"))

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
    """Owner only: register a badge from an uploaded PNG icon."""
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    color = _safe_color(request.form.get("color"))
    icon_file = request.files.get("badge_icon")

    if not name:
        flash("Badge name is required.", "danger")
        return redirect(url_for("profiles.owner_studio"))
    if len(name) > 48:
        flash("Badge name must be 48 characters or fewer.", "danger")
        return redirect(url_for("profiles.owner_studio"))
    if not icon_file or not icon_file.filename:
        flash("Upload a PNG icon for the badge.", "danger")
        return redirect(url_for("profiles.owner_studio"))

    try:
        stored_icon = _stored_icon_from_png(icon_file)

        conn = get_db()
        code = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower()) + "_" + os.urandom(3).hex()
        conn.execute(
            "INSERT INTO BADGE (Code, Name, Description, Icon, Color) VALUES (?, ?, ?, ?, ?)",
            (code, name, description, stored_icon, color),
        )
        conn.commit()
        conn.close()
        flash(f"Official badge '{name}' registered successfully!", "success")
    except Exception as err:
        flash(f"Could not create badge: {err}", "danger")

    return redirect(url_for("profiles.owner_studio"))


@profiles_bp.post("/account/owner/badges/<int:badge_id>/delete")
@owner_required
def delete_badge(badge_id: int):
    """Owner only: Delete a badge from the bank registry."""
    conn = get_db()
    badge = conn.execute("SELECT Name FROM BADGE WHERE BadgeID=?", (badge_id,)).fetchone()
    if not badge:
        conn.close()
        flash("Badge not found.", "warning")
        return redirect(url_for("profiles.owner_studio"))

    conn.execute("DELETE FROM USER_BADGE WHERE BadgeID=?", (badge_id,))
    conn.execute("DELETE FROM BADGE WHERE BadgeID=?", (badge_id,))
    conn.commit()
    conn.close()
    flash(f"Badge '{badge['Name']}' has been removed from the registry.", "info")
    return redirect(url_for("profiles.owner_studio"))


@profiles_bp.post("/account/owner/badges/assign/<int:target_user_id>")
@owner_required
def assign_user_badges(target_user_id: int):
    """Owner only: Assign or remove badges for any user."""
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

    return redirect(request.referrer or url_for("profiles.owner_studio"))


# ─────────────────────────────────────────────────────────────────────────────
# 3. OWNER CUSTOM ROLE SYSTEM (CREATE, DELETE, ASSIGN)
# ─────────────────────────────────────────────────────────────────────────────

@profiles_bp.post("/account/owner/roles/create")
@owner_required
def create_role():
    """Owner only: create a custom profile role with its display color."""
    name = request.form.get("name", "").strip()
    color = _safe_color(request.form.get("color"), DEFAULT_ROLE_COLOR)
    icon_file = request.files.get("role_icon")

    if not name:
        flash("Role name is required.", "danger")
        return redirect(url_for("profiles.owner_studio"))
    if len(name) > 40:
        flash("Role name must be 40 characters or fewer.", "danger")
        return redirect(url_for("profiles.owner_studio"))

    conn = get_db()
    try:
        exists = conn.execute("SELECT 1 FROM CUSTOM_ROLE WHERE lower(Name)=lower(?)", (name,)).fetchone()
        if exists:
            flash(f"A role named '{name}' already exists.", "warning")
            conn.close()
            return redirect(url_for("profiles.owner_studio"))

        stored_icon = _stored_icon_from_png(icon_file, "Role icon") if icon_file and icon_file.filename else None
        next_position = conn.execute("SELECT COALESCE(MAX(Position), 0) + 1 FROM CUSTOM_ROLE").fetchone()[0]
        conn.execute(
            "INSERT INTO CUSTOM_ROLE (Name, Color, Icon, Position) VALUES (?, ?, ?, ?)",
            (name, color, stored_icon, next_position),
        )
        conn.commit()
        flash(f"Custom role '{name}' created successfully!", "success")
    except Exception as err:
        conn.rollback()
        flash(f"Could not create role: {err}", "danger")
    finally:
        conn.close()

    return redirect(url_for("profiles.owner_studio"))


@profiles_bp.post("/account/owner/roles/<int:role_id>/delete")
@owner_required
def delete_role(role_id: int):
    """Owner only: delete a custom role and revoke it from every user."""
    conn = get_db()
    role = conn.execute("SELECT Name FROM CUSTOM_ROLE WHERE RoleID=?", (role_id,)).fetchone()
    if not role:
        conn.close()
        flash("Role not found.", "warning")
        return redirect(url_for("profiles.owner_studio"))

    conn.execute("DELETE FROM USER_CUSTOM_ROLE WHERE RoleID=?", (role_id,))
    conn.execute("DELETE FROM CUSTOM_ROLE WHERE RoleID=?", (role_id,))
    conn.commit()
    conn.close()
    flash(f"Role '{role['Name']}' has been deleted.", "info")
    return redirect(url_for("profiles.owner_studio"))


@profiles_bp.post("/account/owner/roles/assign/<int:target_user_id>")
@owner_required
def assign_user_roles(target_user_id: int):
    """Owner only: assign or revoke custom roles for any user."""
    conn = get_db()
    target_user = conn.execute("SELECT UserID, Username FROM USERS WHERE UserID=?", (target_user_id,)).fetchone()
    if not target_user:
        conn.close()
        flash("Target user not found.", "danger")
        return redirect(url_for("profiles.settings"))

    selected_role_ids = request.form.getlist("role_ids")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM USER_CUSTOM_ROLE WHERE UserID=?", (target_user_id,))
        for rid in selected_role_ids:
            if rid.isdigit():
                conn.execute("INSERT OR IGNORE INTO USER_CUSTOM_ROLE (UserID, RoleID) VALUES (?, ?)", (target_user_id, int(rid)))
        conn.commit()
        flash(f"Profile roles for @{target_user['Username']} updated successfully!", "success")
    except Exception as err:
        conn.rollback()
        flash(f"Could not update roles: {err}", "danger")
    finally:
        conn.close()

    return redirect(request.referrer or url_for("profiles.owner_studio"))


# ─────────────────────────────────────────────────────────────────────────────
# 4. PROFILE VIEWS & GLOBAL MODAL API
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
    all_roles = conn.execute("SELECT * FROM CUSTOM_ROLE ORDER BY Position ASC, RoleID ASC").fetchall()
    conn.close()

    return render_template(
        "profile_card.html",
        profile=profile_data,
        is_owner=is_owner,
        is_self=is_self,
        all_badges=[_decorate_badge(b) for b in all_badges],
        all_roles=[_decorate_role(r) for r in all_roles],
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
        "avatar_url": (
            url_for("profiles.user_avatar", user_id=u["UserID"], v=len(u["ProfilePicture"]))
            if u["ProfilePicture"] else None
        ),
        "banner_url": (
            url_for("profiles.user_banner", user_id=u["UserID"], v=len(u["BannerImage"]))
            if u["BannerImage"] else None
        ),
        "banner_color": u["BannerColor"] or "#0f172a",
        "about_me": u["AboutMe"] or "Verified member of AkumaBank Moroccan banking suite.",
        "custom_status": u["CustomStatus"] or "",
        "pronouns": u["Pronouns"] or "",
        "member_code": f"AKUMA-{u['UserID']:06d}",
    }

    roles = [
        {
            "role_id": r["RoleID"],
            "name": r["Name"],
            "color": r["Color"],
            "icon_url": r["icon_url"],
        }
        for r in profile_data["roles"]
    ]

    badges = [
        {
            "badge_id": b["BadgeID"],
            "name": b["Name"],
            "description": b["Description"] or "",
            "icon_url": b["icon_url"],
            "color": b["Color"],
            "granted_at": b["GrantedAt"],
        }
        for b in profile_data["badges"]
    ]

    return jsonify({
        "user": safe_user,
        "roles": roles,
        "badges": badges,
        "accounts": profile_data["accounts"],
        "stats": {
            "roles": len(roles),
            "badges": len(badges),
            "accounts": len(profile_data["accounts"]),
        },
        "is_owner_viewer": session["user"].get("role") == "Owner",
    })
