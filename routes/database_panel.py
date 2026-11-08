"""
routes/database_panel.py
Database Explorer page — shows all tables, views, trigger, indexes,
and runs live SQL feature demonstrations for the DBMS project.
"""

from flask import Blueprint, render_template, redirect, url_for, session, request, jsonify
from database import get_db
from functools import wraps

database_bp = Blueprint("database_panel", __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def run_query(conn, sql):
    """Run a SQL query and return (columns, rows, error)."""
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows    = [list(r) for r in cur.fetchall()]
        return columns, rows, None
    except Exception as e:
        return [], [], str(e)


@database_bp.route("/database")
@login_required
def database():
    conn = get_db()

    # ── 1. Tables with row counts ──────────────────────────────────────────
    tables_raw = conn.execute("""
        SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """).fetchall()

    tables = []
    for t in tables_raw:
        name = t["name"]
        count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        # Get column info via PRAGMA
        cols_raw = conn.execute(f"PRAGMA table_info([{name}])").fetchall()
        cols = [{"cid": c["cid"], "name": c["name"], "type": c["type"],
                 "notnull": c["notnull"], "pk": c["pk"], "dflt_value": c["dflt_value"]}
                for c in cols_raw]
        # Get foreign keys
        fks_raw = conn.execute(f"PRAGMA foreign_key_list([{name}])").fetchall()
        fks = [{"from": f["from"], "table": f["table"], "to": f["to"]} for f in fks_raw]
        tables.append({"name": name, "count": count, "columns": cols, "foreign_keys": fks})

    # ── 2. Views ───────────────────────────────────────────────────────────
    views_raw = conn.execute("""
        SELECT name, sql FROM sqlite_master WHERE type='view' ORDER BY name
    """).fetchall()
    views = [{"name": v["name"], "sql": v["sql"]} for v in views_raw]

    # ── 3. Triggers ────────────────────────────────────────────────────────
    triggers_raw = conn.execute("""
        SELECT name, sql, tbl_name FROM sqlite_master WHERE type='trigger' ORDER BY name
    """).fetchall()
    triggers = [{"name": t["name"], "tbl_name": t["tbl_name"], "sql": t["sql"]}
                for t in triggers_raw]

    # ── 4. Indexes ─────────────────────────────────────────────────────────
    indexes_raw = conn.execute("""
        SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL
        ORDER BY tbl_name, name
    """).fetchall()
    indexes = [{"name": i["name"], "tbl_name": i["tbl_name"], "sql": i["sql"]}
               for i in indexes_raw]

    # ── 5. Feature demos ───────────────────────────────────────────────────

    # JOIN query — 3-table join
    join_cols, join_rows, join_err = run_query(conn, """
        SELECT c.Name AS Customer, a.AccountNumber, a.AccountType,
               printf('MAD %,.2f', a.Balance) AS Balance, b.BranchName
        FROM CUSTOMER c
        JOIN ACCOUNT  a ON c.CustomerID = a.CustomerID
        LEFT JOIN BRANCH b ON a.BranchID = b.BranchID
        ORDER BY a.Balance DESC LIMIT 10
    """)

    # AGGREGATE query
    agg_cols, agg_rows, agg_err = run_query(conn, """
        SELECT AccountType,
               COUNT(*)                      AS Total_Accounts,
               printf('MAD %,.0f', SUM(Balance))  AS Total_Balance,
               printf('MAD %,.0f', AVG(Balance))  AS Avg_Balance,
               printf('MAD %,.0f', MAX(Balance))  AS Max_Balance,
               printf('MAD %,.0f', MIN(Balance))  AS Min_Balance
        FROM ACCOUNT
        GROUP BY AccountType
        ORDER BY SUM(Balance) DESC
    """)

    # SUBQUERY — above-average balance customers
    sub_cols, sub_rows, sub_err = run_query(conn, """
        SELECT c.Name, c.Email,
               printf('MAD %,.0f', SUM(a.Balance)) AS Total_Balance
        FROM CUSTOMER c
        JOIN ACCOUNT a ON c.CustomerID = a.CustomerID
        WHERE a.Status = 'Active'
        GROUP BY c.CustomerID
        HAVING SUM(a.Balance) > (
            SELECT AVG(Balance) FROM ACCOUNT WHERE Status = 'Active'
        )
        ORDER BY SUM(a.Balance) DESC
    """)

    # VIEW — CustomerAccountSummary
    view1_cols, view1_rows, view1_err = run_query(conn,
        "SELECT CustomerName, AccountNumber, AccountType, "
        "printf('MAD %,.2f', Balance) AS Balance, AccountStatus, BranchName "
        "FROM CustomerAccountSummary LIMIT 10"
    )

    # VIEW — TransactionDetails
    view2_cols, view2_rows, view2_err = run_query(conn,
        "SELECT TransactionID, CustomerName, AccountNumber, TransactionType, "
        "printf('MAD %,.2f', Amount) AS Amount, TransactionDate "
        "FROM TransactionDetails ORDER BY TransactionDate DESC LIMIT 10"
    )

    # TRIGGER proof — show last 5 rows where BalanceAfter = current Balance
    trig_cols, trig_rows, trig_err = run_query(conn, """
        SELECT t.TransactionID,
               a.AccountNumber,
               printf('MAD %,.2f', t.Amount)       AS Transaction_Amount,
               t.TransactionType,
               printf('MAD %,.2f', t.BalanceAfter) AS BalanceAfter_in_TXN,
               printf('MAD %,.2f', a.Balance)       AS Current_ACCOUNT_Balance,
               CASE WHEN ROUND(t.BalanceAfter,2)=ROUND(a.Balance,2)
                    THEN '✓ Trigger Synced' ELSE '✗ Mismatch' END AS Trigger_Status
        FROM TRANSACTIONS t
        JOIN ACCOUNT a ON t.AccountID = a.AccountID
        WHERE t.TransactionID = (
            SELECT MAX(TransactionID) FROM TRANSACTIONS WHERE AccountID = t.AccountID
        )
        ORDER BY t.TransactionID DESC LIMIT 8
    """)

    # AGGREGATE — Loan summary by type
    loan_cols, loan_rows, loan_err = run_query(conn, """
        SELECT LoanType,
               COUNT(*)                            AS Applications,
               printf('MAD %,.0f', SUM(Amount))       AS Total_Amount,
               printf('MAD %,.0f', AVG(Amount))       AS Avg_Amount,
               printf('%.1f%%', AVG(InterestRate)) AS Avg_Rate,
               SUM(CASE WHEN Status='Approved' THEN 1 ELSE 0 END) AS Approved,
               SUM(CASE WHEN Status='Pending'  THEN 1 ELSE 0 END) AS Pending
        FROM LOAN
        GROUP BY LoanType
        ORDER BY SUM(Amount) DESC
    """)

    # Monthly AGGREGATE
    monthly_cols, monthly_rows, monthly_err = run_query(conn, """
        SELECT strftime('%Y-%m', TransactionDate)      AS Month,
               COUNT(*)                                 AS Transactions,
               printf('MAD %,.0f', SUM(Amount))            AS Total_Amount,
               printf('MAD %,.0f',
                 SUM(CASE WHEN TransactionType='Deposit' THEN Amount ELSE 0 END))
                                                         AS Deposits,
               printf('MAD %,.0f',
                 SUM(CASE WHEN TransactionType='Withdrawal' THEN Amount ELSE 0 END))
                                                         AS Withdrawals
        FROM TRANSACTIONS
        GROUP BY Month
        ORDER BY Month DESC LIMIT 12
    """)

    # SUBQUERY — inactive accounts (no tx in 90 days)
    inactive_cols, inactive_rows, inactive_err = run_query(conn, """
        SELECT a.AccountNumber, c.Name,
               printf('MAD %,.2f', a.Balance) AS Balance, a.Status
        FROM ACCOUNT a
        JOIN CUSTOMER c ON a.CustomerID = c.CustomerID
        WHERE a.AccountID NOT IN (
            SELECT DISTINCT AccountID FROM TRANSACTIONS
            WHERE TransactionDate >= date('now', '-90 days')
        )
        ORDER BY a.Balance DESC
    """)

    conn.close()

    return render_template("database_panel.html",
        tables=tables,
        views=views,
        triggers=triggers,
        indexes=indexes,
        # feature demos
        join_cols=join_cols, join_rows=join_rows, join_err=join_err,
        agg_cols=agg_cols,   agg_rows=agg_rows,   agg_err=agg_err,
        sub_cols=sub_cols,   sub_rows=sub_rows,   sub_err=sub_err,
        view1_cols=view1_cols, view1_rows=view1_rows, view1_err=view1_err,
        view2_cols=view2_cols, view2_rows=view2_rows, view2_err=view2_err,
        trig_cols=trig_cols, trig_rows=trig_rows, trig_err=trig_err,
        loan_cols=loan_cols, loan_rows=loan_rows, loan_err=loan_err,
        monthly_cols=monthly_cols, monthly_rows=monthly_rows, monthly_err=monthly_err,
        inactive_cols=inactive_cols, inactive_rows=inactive_rows, inactive_err=inactive_err,
    )


@database_bp.route("/database/run", methods=["POST"])
@login_required
def run_sql():
    """Execute a custom SQL query (SELECT only for safety)."""
    sql = request.json.get("sql", "").strip()
    if not sql:
        return jsonify({"error": "No SQL provided."}), 400
    if not sql.upper().startswith("SELECT") and not sql.upper().startswith("PRAGMA"):
        return jsonify({"error": "Only SELECT and PRAGMA queries are allowed here."}), 400
    conn = get_db()
    cols, rows, err = run_query(conn, sql)
    conn.close()
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"columns": cols, "rows": rows, "count": len(rows)})
