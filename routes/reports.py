"""
routes/reports.py - Transaction, Customer, and Loan reports using SQL aggregates and joins
"""

from flask import Blueprint, render_template, request, redirect, url_for, session
from database import get_db
from functools import wraps

reports_bp = Blueprint("reports", __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@reports_bp.route("/reports")
@login_required
def reports():
    conn = get_db()

    # ── Transaction history report (last 100 via VIEW) ──────────────────────
    txn_history = conn.execute("""
        SELECT * FROM TransactionDetails
        ORDER BY TransactionDate DESC
        LIMIT 100
    """).fetchall()

    # ── Monthly summary using aggregate functions ────────────────────────────
    monthly_summary = conn.execute("""
        SELECT
            strftime('%Y-%m', TransactionDate) AS month,
            COUNT(*)                            AS count,
            SUM(Amount)                         AS total_amount,
            SUM(CASE WHEN TransactionType='Deposit'    THEN Amount ELSE 0 END) AS deposits,
            SUM(CASE WHEN TransactionType='Withdrawal' THEN Amount ELSE 0 END) AS withdrawals,
            SUM(CASE WHEN TransactionType='Transfer'   THEN Amount ELSE 0 END) AS transfers
        FROM TRANSACTIONS
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    """).fetchall()

    # ── Customer report (JOIN with account aggregates) ───────────────────────
    customer_report = conn.execute("""
        SELECT
            c.CustomerID, c.Name, c.Email, c.Phone,
            COUNT(a.AccountID)           AS accounts,
            COALESCE(SUM(a.Balance), 0)  AS total_balance,
            COALESCE(MAX(a.Balance), 0)  AS max_balance,
            COUNT(l.LoanID)              AS total_loans,
            COALESCE(SUM(l.Amount), 0)   AS total_loan_amount
        FROM CUSTOMER c
        LEFT JOIN ACCOUNT a ON c.CustomerID = a.CustomerID AND a.Status='Active'
        LEFT JOIN LOAN    l ON c.CustomerID = l.CustomerID AND l.Status='Approved'
        GROUP BY c.CustomerID
        ORDER BY total_balance DESC
    """).fetchall()

    # ── Loan report ──────────────────────────────────────────────────────────
    loan_report = conn.execute("""
        SELECT
            l.LoanType,
            COUNT(*)             AS count,
            SUM(l.Amount)        AS total_amount,
            AVG(l.Amount)        AS avg_amount,
            AVG(l.InterestRate)  AS avg_rate,
            SUM(CASE WHEN l.Status='Approved' THEN 1 ELSE 0 END) AS approved,
            SUM(CASE WHEN l.Status='Pending'  THEN 1 ELSE 0 END) AS pending
        FROM LOAN l
        GROUP BY l.LoanType
        ORDER BY total_amount DESC
    """).fetchall()

    # ── Subquery: customers with balance above average ────────────────────────
    high_balance_customers = conn.execute("""
        SELECT c.Name, c.Email, SUM(a.Balance) AS total
        FROM CUSTOMER c
        JOIN ACCOUNT a ON c.CustomerID = a.CustomerID
        WHERE a.Status = 'Active'
        GROUP BY c.CustomerID
        HAVING SUM(a.Balance) > (
            SELECT AVG(Balance) FROM ACCOUNT WHERE Status='Active'
        )
        ORDER BY total DESC
    """).fetchall()

    # ── Accounts with no recent transactions (subquery) ──────────────────────
    inactive_accounts = conn.execute("""
        SELECT a.AccountNumber, c.Name, a.Balance, a.Status
        FROM ACCOUNT a
        JOIN CUSTOMER c ON a.CustomerID = c.CustomerID
        WHERE a.AccountID NOT IN (
            SELECT DISTINCT AccountID FROM TRANSACTIONS
            WHERE TransactionDate >= date('now', '-90 days')
        )
        ORDER BY a.Balance DESC
    """).fetchall()

    # Convert sqlite3.Row objects to plain dicts so tojson works in templates
    monthly_summary       = [dict(r) for r in monthly_summary]
    loan_report           = [dict(r) for r in loan_report]
    txn_history           = [dict(r) for r in txn_history]
    customer_report       = [dict(r) for r in customer_report]
    high_balance_customers= [dict(r) for r in high_balance_customers]
    inactive_accounts     = [dict(r) for r in inactive_accounts]

    conn.close()
    return render_template(
        "reports.html",
        txn_history=txn_history,
        monthly_summary=monthly_summary,
        customer_report=customer_report,
        loan_report=loan_report,
        high_balance_customers=high_balance_customers,
        inactive_accounts=inactive_accounts,
    )
