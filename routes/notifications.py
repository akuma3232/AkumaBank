"""Notification inbox endpoints: open one, or mark everything as read."""

from urllib.parse import urlparse

from flask import Blueprint, jsonify, redirect, request, session, url_for

from database import get_db
from notifications import ensure_schema

notifications_bp = Blueprint("notifications", __name__)


def _home_for(user):
    return url_for(
        "customer_portal.home" if user.get("role") == "Customer" else "dashboard.dashboard"
    )


@notifications_bp.get("/notifications/<int:nid>/open")
def open_notification(nid):
    """Mark a notification read and follow its link (or fall back home)."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login"))

    conn = get_db()
    ensure_schema(conn)
    row = conn.execute(
        "SELECT Link FROM NOTIFICATION WHERE NotificationID=? AND UserID=?",
        (nid, user["id"]),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE NOTIFICATION SET IsRead=1 WHERE NotificationID=? AND UserID=?",
            (nid, user["id"]),
        )
        conn.commit()
    conn.close()

    target = (row["Link"] if row else None) or ""
    if not target.startswith("/") or target.startswith("//"):
        target = _home_for(user)
    return redirect(target)


@notifications_bp.post("/notifications/<int:nid>/read")
def mark_read(nid):
    """Mark one notification read in place, without leaving the page."""
    user = session.get("user")
    if not user:
        return jsonify({"ok": False}), 401

    conn = get_db()
    ensure_schema(conn)
    conn.execute(
        "UPDATE NOTIFICATION SET IsRead=1 WHERE NotificationID=? AND UserID=?",
        (nid, user["id"]),
    )
    conn.commit()
    unread = conn.execute(
        "SELECT COUNT(*) FROM NOTIFICATION WHERE UserID=? AND IsRead=0", (user["id"],)
    ).fetchone()[0]
    conn.close()
    return jsonify({"ok": True, "unread": unread})


@notifications_bp.post("/notifications/read-all")
def read_all():
    """Clear the unread badge for the signed-in user."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login"))

    conn = get_db()
    ensure_schema(conn)
    conn.execute("UPDATE NOTIFICATION SET IsRead=1 WHERE UserID=? AND IsRead=0", (user["id"],))
    conn.commit()
    conn.close()

    referrer = request.referrer
    if referrer and urlparse(referrer).netloc != request.host:
        referrer = None  # never bounce to another origin
    return redirect(referrer or _home_for(user))
