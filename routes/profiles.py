"""Profile picture settings for signed-in staff."""

import uuid
from functools import wraps
from pathlib import Path

from io import BytesIO

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
MAX_ANIMATED_IMAGE_PIXELS = 80_000_000
MAX_GIF_FRAMES = 150
ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


@profiles_bp.route("/account/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Let the signed-in user upload or remove their own profile picture."""
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
            flash("Choose an image to upload.", "danger")
        else:
            try:
                image_bytes = upload.stream.read(MAX_IMAGE_BYTES + 1)
                if len(image_bytes) > MAX_IMAGE_BYTES:
                    raise ValueError("The image must be 5 MB or smaller.")

                with Image.open(BytesIO(image_bytes)) as image:
                    image_format = image.format
                    if image_format not in ALLOWED_FORMATS:
                        raise ValueError("Use a JPEG, PNG, GIF, or WebP image.")
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise ValueError("Image dimensions must be 16 megapixels or smaller.")
                    frame_count = getattr(image, "n_frames", 1)
                    if frame_count > MAX_GIF_FRAMES:
                        raise ValueError("Animated images may contain at most 150 frames.")
                    if image.width * image.height * frame_count > MAX_ANIMATED_IMAGE_PIXELS:
                        raise ValueError("The total animation size is too large.")
                    for frame in range(frame_count):
                        image.seek(frame)
                        image.load()

                extension = ALLOWED_FORMATS[image_format]
                filename = f"{user_id}_{uuid.uuid4().hex}.{extension}"
                PROFILE_PICTURE_DIR.mkdir(parents=True, exist_ok=True)
                destination = PROFILE_PICTURE_DIR / secure_filename(filename)
                destination.write_bytes(image_bytes)

                try:
                    conn.execute(
                        "UPDATE USERS SET ProfilePicture=? WHERE UserID=?",
                        (filename, user_id),
                    )
                    conn.commit()
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
                session["user"]["profile_picture"] = filename
                if user["ProfilePicture"]:
                    old_picture = PROFILE_PICTURE_DIR / user["ProfilePicture"]
                    if old_picture.parent == PROFILE_PICTURE_DIR and old_picture != destination:
                        old_picture.unlink(missing_ok=True)
                flash("Profile picture updated.", "success")
            except (UnidentifiedImageError, OSError, ValueError) as error:
                conn.rollback()
                flash(f"Could not use that image: {error}", "danger")

    conn.close()
    return render_template("account_settings.html", profile_picture=user["ProfilePicture"])


@profiles_bp.post("/account/settings/profile-picture/remove")
@login_required
def remove_picture():
    """Remove only the signed-in user's profile picture."""
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

    if user["ProfilePicture"]:
        old_picture = PROFILE_PICTURE_DIR / user["ProfilePicture"]
        if old_picture.parent == PROFILE_PICTURE_DIR:
            old_picture.unlink(missing_ok=True)
    flash("Profile picture removed.", "success")
    return redirect(url_for("profiles.settings"))


@profiles_bp.get("/profile-pictures/<path:filename>")
@login_required
def picture(filename):
    """Serve stored pictures only to authenticated users."""
    if Path(filename).name != filename:
        return "", 404
    response = current_app.make_response(
        send_from_directory(PROFILE_PICTURE_DIR, filename, conditional=True)
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response
