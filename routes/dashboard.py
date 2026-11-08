"""
routes/dashboard.py - Dashboard with aggregate analytics
Uses SQL aggregate functions and joins to compute KPI metrics.
"""

from flask import Blueprint, render_template, redirect, url_for, session
from database import get_db

dashboard_bp = Blueprint("dashboard", __name__)


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()

    # ── Aggregate KPIs ──────────────────────────────────────────────────────
    total_customers  = conn.execute("SELECT COUNT(*) FROM CUSTOMER").fetchone()[0]
    total_accounts   = conn.execute("SELECT COUNT(*) FROM ACCOUNT").fetchone()[0]
    total_balance    = conn.execute("SELECT COALESCE(SUM(Balance),0) FROM ACCOUNT WHERE Status='Active'").fetchone()[0]
    total_txns       = conn.execute("SELECT COUNT(*) FROM TRANSACTIONS").fetchone()[0]
    pending_loans    = conn.execute("SELECT COUNT(*) FROM LOAN WHERE Status='Pending'").fetchone()[0]
    active_accounts  = conn.execute("SELECT COUNT(*) FROM ACCOUNT WHERE Status='Active'").fetchone()[0]

    # ── Recent 10 transactions (JOIN query) ─────────────────────────────────
    recent_txns = conn.execute("""
        SELECT t.TransactionID, t.TransactionDate, t.TransactionType,
               t.Amount, t.BalanceAfter, t.Description,
               a.AccountNumber, c.Name AS CustomerName
        FROM TRANSACTIONS t
        JOIN ACCOUNT  a ON t.AccountID  = a.AccountID
        JOIN CUSTOMER c ON a.CustomerID = c.CustomerID
        ORDER BY t.TransactionDate DESC
        LIMIT 10
    """).fetchall()

    # ── Monthly transaction totals for chart (aggregate + subquery) ─────────
    monthly_data = conn.execute("""
        SELECT strftime('%Y-%m', TransactionDate) AS month,
               TransactionType,
               SUM(Amount) AS total
        FROM TRANSACTIONS
        GROUP BY month, TransactionType
        ORDER BY month DESC
        LIMIT 18
    """).fetchall()

    # ── Account type distribution ────────────────────────────────────────────
    acct_types = conn.execute("""
        SELECT AccountType, COUNT(*) AS cnt, SUM(Balance) AS total
        FROM ACCOUNT
        GROUP BY AccountType
    """).fetchall()

    # ── Top 5 customers by balance (subquery) ────────────────────────────────
    top_customers = conn.execute("""
        SELECT c.Name, SUM(a.Balance) AS total_balance
        FROM CUSTOMER c
        JOIN ACCOUNT a ON c.CustomerID = a.CustomerID
        WHERE a.Status = 'Active'
        GROUP BY c.CustomerID
        ORDER BY total_balance DESC
        LIMIT 5
    """).fetchall()

    # Convert sqlite3.Row objects to plain dicts so tojson works in templates
    monthly_data  = [dict(r) for r in monthly_data]
    acct_types    = [dict(r) for r in acct_types]
    top_customers = [dict(r) for r in top_customers]
    recent_txns   = [dict(r) for r in recent_txns]

    conn.close()

    return render_template(
        "dashboard.html",
        total_customers=total_customers,
        total_accounts=total_accounts,
        total_balance=total_balance,
        total_txns=total_txns,
        pending_loans=pending_loans,
        active_accounts=active_accounts,
        recent_txns=recent_txns,
        monthly_data=monthly_data,
        acct_types=acct_types,
        top_customers=top_customers,
    )
