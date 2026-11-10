"""Profile picture settings for signed-in staff and customers.
Transforms uploaded images into pure Base64 / SVG text code without storing image files on disk or binary blobs.
"""

import base64
import hashlib
import urllib.parse
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

from database import DATABASE_DIR, get_db

profiles_bp = Blueprint("profiles", __name__)
PROFILE_PICTURE_DIR = Path(DATABASE_DIR) / "profile_pictures"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


def generate_svg_avatar_code(seed_text: str) -> str:
    """Generate an algorithmic geometric SVG code avatar as a data URI."""
    h = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    c1 = f"#{h[:6]}"
    c2 = f"#{h[6:12]}"
    c3 = f"#{h[12:18]}"
    c4 = f"#{h[18:24]}"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120">
      <defs>
        <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="{c1}"/>
          <stop offset="100%" stop-color="{c2}"/>
        </linearGradient>
      </defs>
      <rect width="120" height="120" rx="24" fill="url(#g1)"/>
      <circle cx="60" cy="60" r="38" fill="{c3}" opacity="0.85"/>
      <polygon points="60,28 90,82 30,82" fill="{c4}" opacity="0.9"/>
      <circle cx="60" cy="60" r="14" fill="#ffffff" opacity="0.95"/>
    </svg>"""
    encoded = urllib.parse.quote(svg.strip())
    return f"data:image/svg+xml;utf8,{encoded}"


@profiles_bp.route("/account/settings", methods=["GET", "POST"])
@login_required
def settings():
    """
    Profile picture settings:
    Transforms any selected image into a pure Base64 code string.
    Zero picture files are written to the server filesystem or binary storage.
    """
    user_id = session["user"]["id"]
    conn = get_db()
    user = conn.execute(
        "SELECT Username, ProfilePicture FROM USERS WHERE UserID=?",
        (user_id,),
    ).fetchone()
    if user is None:
        conn.close()
        session.clear()
        flash("Your account is no longer available. Please sign in again.", "danger")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        upload = request.files.get("profile_picture")
        if upload is None or not upload.filename:
            flash("Please choose an image file to transform into code.", "danger")
        else:
            try:
                image_bytes = upload.stream.read(MAX_IMAGE_BYTES + 1)
                if len(image_bytes) > MAX_IMAGE_BYTES:
                    raise ValueError("The image must be 5 MB or smaller.")

                with Image.open(BytesIO(image_bytes)) as img:
                    if img.format not in ALLOWED_FORMATS:
                        raise ValueError("Please select a JPEG, PNG, GIF, or WebP image.")
                    if img.width * img.height > MAX_IMAGE_PIXELS:
                        raise ValueError("Image dimensions must be 16 megapixels or smaller.")

                    # Convert and resize to a clean square thumbnail (128x128)
                    img = img.convert("RGBA")
                    img.thumbnail((128, 128), Image.Resampling.LANCZOS)

                    # Encode to WebP Base64 text code
                    out_buffer = BytesIO()
                    img.save(out_buffer, format="WEBP", quality=82)
                    b64_encoded = base64.b64encode(out_buffer.getvalue()).decode("ascii")
                    code_string = f"data:image/webp;base64,{b64_encoded}"

                # Save pure code text into database
                conn.execute(
                    "UPDATE USERS SET ProfilePicture=? WHERE UserID=?",
                    (code_string, user_id),
                )
                conn.commit()
                session["user"]["profile_picture"] = code_string

                # Remove legacy disk file if there was one
                if user["ProfilePicture"] and not user["ProfilePicture"].startswith("data:"):
                    old_picture = PROFILE_PICTURE_DIR / user["ProfilePicture"]
                    if old_picture.parent == PROFILE_PICTURE_DIR and old_picture.exists():
                        old_picture.unlink(missing_ok=True)

                flash(
                    f"Profile picture transformed to code ({len(code_string):,} characters). "
                    "No image file was stored on the server disk.",
                    "success",
                )
            except (UnidentifiedImageError, OSError, ValueError) as error:
                conn.rollback()
                flash(f"Could not transform that image: {error}", "danger")

    # Fetch updated user record
    updated_user = conn.execute(
        "SELECT Username, ProfilePicture FROM USERS WHERE UserID=?",
        (user_id,),
    ).fetchone()
    conn.close()

    current_pic = updated_user["ProfilePicture"] if updated_user else None
    return render_template("account_settings.html", profile_picture=current_pic)


@profiles_bp.post("/account/settings/generate-code-avatar")
@login_required
def generate_avatar():
    """Generate an algorithmic SVG code avatar without uploading any picture."""
    user_id = session["user"]["id"]
    username = session["user"]["username"]

    import random
    salt = random.randint(1000, 99999)
    code_string = generate_svg_avatar_code(f"{username}-{salt}")

    conn = get_db()
    conn.execute(
        "UPDATE USERS SET ProfilePicture=? WHERE UserID=?",
        (code_string, user_id),
    )
    conn.commit()
    conn.close()

    session["user"]["profile_picture"] = code_string
    flash("Algorithmic code avatar generated and saved as pure SVG code.", "success")
    return redirect(url_for("profiles.settings"))


@profiles_bp.post("/account/settings/profile-picture/remove")
@login_required
def remove_picture():
    """Remove the profile picture code."""
    user_id = session["user"]["id"]
    conn = get_db()
    user = conn.execute(
        "SELECT ProfilePicture FROM USERS WHERE UserID=?",
        (user_id,),
    ).fetchone()
    if user is None:
        conn.close()
        session.clear()
        flash("Your account is no longer available. Please sign in again.", "danger")
        return redirect(url_for("auth.login"))

    conn.execute("UPDATE USERS SET ProfilePicture=NULL WHERE UserID=?", (user_id,))
    conn.commit()
    conn.close()
    session["user"]["profile_picture"] = None

    if user["ProfilePicture"] and not user["ProfilePicture"].startswith("data:"):
        old_picture = PROFILE_PICTURE_DIR / user["ProfilePicture"]
        if old_picture.parent == PROFILE_PICTURE_DIR and old_picture.exists():
            old_picture.unlink(missing_ok=True)

    flash("Profile picture code removed.", "success")
    return redirect(url_for("profiles.settings"))


@profiles_bp.get("/profile-pictures/<path:filename>")
@login_required
def picture(filename):
    """Fallback route for legacy files if any."""
    if not (PROFILE_PICTURE_DIR / filename).exists():
        return redirect(url_for("static", filename="images/avatar-placeholder.png"))
    return send_from_directory(PROFILE_PICTURE_DIR, filename)
