"""Live update polling endpoint.

The browser polls this route and reloads the current view when the database
changes, so edits made by any signed-in user appear without a manual refresh.
"""

import os

from flask import Blueprint, jsonify

from database import DB_PATH

live_bp = Blueprint("live", __name__)


@live_bp.get("/api/live/version")
def live_version():
    """Return a cheap fingerprint of the SQLite file that changes on every commit."""
    try:
        stat = os.stat(DB_PATH)
        version = f"{stat.st_mtime_ns}-{stat.st_size}"
    except OSError:
        version = "0-0"

    response = jsonify({"version": version})
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response
