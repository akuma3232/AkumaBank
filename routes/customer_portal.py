"""Read-only self-service views for approved customer logins."""

from functools import wraps

from flask import Blueprint, redirect, render_template, session, url_for

from database import get_db

customer_portal_bp = Blueprint("customer_portal", __name__)


def customer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("user", {}).get("role") != "Customer":
            return redirect(url_for("dashboard.dashboard"))
        return f(*args, **kwargs)

    return decorated


@customer_portal_bp.get("/my-banking")
@customer_required
def home():
    """Show the signed-in customer's own linked profile and accounts."""
    email = session["user"]["email"]
    conn = get_db()
    customer = conn.execute(
        """SELECT CustomerID, Name, Email, Phone, Address
           FROM CUSTOMER WHERE lower(Email)=lower(?)""",
        (email,),
    ).fetchone()

    accounts = []
    transactions = []
    if customer:
        accounts = conn.execute(
            """SELECT AccountID, AccountNumber, AccountType, Balance, Status,
                      OpeningDate, BranchName, City
               FROM ACCOUNT LEFT JOIN BRANCH USING (BranchID)
               WHERE CustomerID=? ORDER BY AccountID""",
            (customer["CustomerID"],),
        ).fetchall()
        transactions = conn.execute(
            """SELECT t.TransactionDate, t.TransactionType, t.Amount, t.Description,
                      t.BalanceAfter, a.AccountNumber
               FROM TRANSACTIONS t JOIN ACCOUNT a ON a.AccountID=t.AccountID
               WHERE a.CustomerID=? ORDER BY t.TransactionDate DESC, t.TransactionID DESC
               LIMIT 50""",
            (customer["CustomerID"],),
        ).fetchall()
    conn.close()
    return render_template(
        "customer_portal.html",
        customer=customer,
        accounts=accounts,
        transactions=transactions,
    )
