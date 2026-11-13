"""In-app notifications.

Every review decision (signup, account opening/closure, document, loan,
profile change, password reset) drops a row in NOTIFICATION for the customer
it concerns, and the bell in the top bar renders whichever rows belong to the
signed-in user.
"""

from database import get_db

_SCHEMA = """
CREATE TABLE IF NOT EXISTS NOTIFICATION (
    NotificationID INTEGER PRIMARY KEY AUTOINCREMENT,
    UserID     INTEGER NOT NULL,
    Title      TEXT    NOT NULL,
    Body       TEXT,
    Category   TEXT    NOT NULL DEFAULT 'info',
    Icon       TEXT    DEFAULT 'bell-fill',
    Link       TEXT,
    IsRead     INTEGER NOT NULL DEFAULT 0 CHECK(IsRead IN (0,1)),
    CreatedAt  TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (UserID) REFERENCES USERS(UserID) ON DELETE CASCADE
)
"""

ALLOWED_CATEGORIES = ("info", "success", "danger", "warning", "primary")
_schema_ready = False


def ensure_schema(conn):
    """Create the notification table once per process, on old databases only."""
    global _schema_ready
    if _schema_ready:
        return
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='NOTIFICATION'"
    ).fetchone()
    if not exists:
        conn.execute(_SCHEMA)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notification_user "
            "ON NOTIFICATION(UserID, IsRead)"
        )
    _schema_ready = True


def notify(
    user_id,
    title,
    body="",
    category="info",
    icon="bell-fill",
    link=None,
    conn=None,
):
    """Store one notification for a user.

    Pass ``conn`` when the caller already holds a transaction so the
    notification is committed (or rolled back) with the decision itself.
    """
    if not user_id:
        return
    category = category if category in ALLOWED_CATEGORIES else "info"
    owned = conn is None
    conn = conn or get_db()
    try:
        ensure_schema(conn)
        conn.execute(
            """INSERT INTO NOTIFICATION (UserID, Title, Body, Category, Icon, Link)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (int(user_id), title, body or "", category, icon or "bell-fill", link),
        )
        if owned:
            conn.commit()
    finally:
        if owned:
            conn.close()


def customer_user_id(customer_id, conn):
    """Resolve a CUSTOMER row to the USERS login that can read notifications."""
    if not customer_id:
        return None
    row = conn.execute(
        """SELECT u.UserID
           FROM USERS u JOIN CUSTOMER c ON lower(u.Email) = lower(c.Email)
           WHERE c.CustomerID = ? AND u.Role = 'Customer'""",
        (customer_id,),
    ).fetchone()
    return row["UserID"] if row else None


def notify_customer(customer_id, title, body="", **kwargs):
    """Send a notification to the login behind a customer record."""
    conn = kwargs.pop("conn", None)
    owned = conn is None
    conn = conn or get_db()
    try:
        user_id = customer_user_id(customer_id, conn)
        if user_id:
            kwargs["conn"] = conn
            notify(user_id, title, body, **kwargs)
        if owned:
            conn.commit()
    finally:
        if owned:
            conn.close()


def notify_account(account_id, title, body="", **kwargs):
    """Send a notification to the owner of an account."""
    conn = kwargs.pop("conn", None)
    owned = conn is None
    conn = conn or get_db()
    try:
        row = conn.execute(
            "SELECT CustomerID FROM ACCOUNT WHERE AccountID=?", (account_id,)
        ).fetchone()
        if row:
            kwargs["conn"] = conn
            notify_customer(row["CustomerID"], title, body, **kwargs)
        if owned:
            conn.commit()
    finally:
        if owned:
            conn.close()
