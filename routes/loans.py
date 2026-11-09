"""
routes/loans.py - Loan application, approval, and management
"""

from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db
from functools import wraps

loans_bp = Blueprint("loans", __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@loans_bp.route("/loans")
@login_required
def loans():
    """List loans with JOIN to customer data."""
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    conn   = get_db()

    query  = """
        SELECT l.*, c.Name AS CustomerName, c.Email, c.Phone,
             da.AccountNumber AS DisbursementAccountNumber,
               ROUND(l.Amount * l.InterestRate / 100, 2) AS annual_interest,
               ROUND(l.Amount * (1 + l.InterestRate / 100), 2) AS total_repayable
        FROM LOAN l
        JOIN CUSTOMER c ON l.CustomerID = c.CustomerID
         LEFT JOIN ACCOUNT da ON da.AccountID = l.DisbursementAccountID
    """
    params = []
    conds  = []

    if search:
        conds.append("(c.Name LIKE ? OR l.LoanType LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if status:
        conds.append("l.Status = ?")
        params.append(status)

    if conds:
        query += " WHERE " + " AND ".join(conds)
    query += " ORDER BY l.LoanID DESC"

    rows = conn.execute(query, params).fetchall()

    # Aggregate stats using aggregate functions
    stats = conn.execute("""
        SELECT
            COUNT(*)                                                            AS total,
            COALESCE(SUM(Amount), 0)                                            AS total_amount,
            COALESCE(AVG(Amount), 0)                                            AS avg_amount,
            COALESCE(SUM(CASE WHEN Status='Pending'  THEN 1 ELSE 0 END), 0)    AS pending,
            COALESCE(SUM(CASE WHEN Status='Approved' THEN 1 ELSE 0 END), 0)    AS approved,
            COALESCE(SUM(CASE WHEN Status='Rejected' THEN 1 ELSE 0 END), 0)    AS rejected,
            COALESCE(SUM(CASE WHEN Status='Approved' THEN Amount ELSE 0 END), 0) AS approved_amount
        FROM LOAN
    """).fetchone()

    customers = conn.execute("SELECT CustomerID, Name FROM CUSTOMER ORDER BY Name").fetchall()
    disbursement_accounts = conn.execute(
        """SELECT a.AccountID, a.CustomerID, a.AccountNumber, c.Name AS CustomerName
           FROM ACCOUNT a JOIN CUSTOMER c ON c.CustomerID=a.CustomerID
           WHERE a.Status='Active' ORDER BY c.Name, a.AccountNumber"""
    ).fetchall()
    disbursement_accounts_by_customer = {}
    for account in disbursement_accounts:
        disbursement_accounts_by_customer.setdefault(account["CustomerID"], []).append(account)
    conn.close()

    return render_template(
        "loans.html",
        loans=rows,
        stats=stats,
        customers=customers,
        disbursement_accounts=disbursement_accounts,
        disbursement_accounts_by_customer=disbursement_accounts_by_customer,
        search=search,
        status_filter=status,
    )


@loans_bp.route("/loans/apply", methods=["POST"])
@login_required
def apply_loan():
    data = request.form
    cid      = data.get("customer_id")
    ltype    = data.get("loan_type")
    account_id = data.get("disbursement_account_id", "")
    try:
        amount = Decimal(data.get("amount", ""))
        rate = Decimal(data.get("interest_rate", ""))
    except InvalidOperation:
        amount = rate = Decimal("0")
    start    = data.get("start_date")

    if (
        not cid or not cid.isdecimal()
        or ltype not in ("Home", "Car", "Personal", "Education", "Business")
        or not account_id.isdecimal()
        or not start
        or not amount.is_finite() or not Decimal("1000") <= amount <= Decimal("100000000")
        or not rate.is_finite() or not Decimal("0.1") <= rate <= Decimal("30")
    ):
        flash("All loan fields are required.", "danger")
        return redirect(url_for("loans.loans"))

    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        account = conn.execute(
            """SELECT AccountID FROM ACCOUNT
               WHERE AccountID=? AND CustomerID=? AND Status='Active'""",
            (int(account_id), int(cid)),
        ).fetchone()
        if not account:
            conn.rollback()
            flash("Choose an active account belonging to the selected customer.", "danger")
            return redirect(url_for("loans.loans"))
        conn.execute(
            """INSERT INTO LOAN
               (CustomerID, LoanType, Amount, InterestRate, StartDate, DisbursementAccountID)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (int(cid), ltype, float(amount), float(rate), start, account["AccountID"]),
        )
        conn.commit()
        flash("Loan application submitted successfully.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("loans.loans"))


@loans_bp.route("/loans/update/<int:lid>", methods=["POST"])
@login_required
def update_loan(lid):
    """Approve, reject, or close a loan (Admin only)."""
    if session.get("user", {}).get("role") not in ("Admin", "Owner"):
        flash("Only Admin or Owner can change loan status.", "danger")
        return redirect(url_for("loans.loans"))

    new_status = request.form.get("status")
    if new_status not in ("Approved", "Rejected", "Closed"):
        flash("Choose a valid loan status.", "danger")
        return redirect(url_for("loans.loans"))

    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        loan = conn.execute(
            """SELECT CustomerID, Amount, Status, DisbursementAccountID, DisbursedAt
               FROM LOAN WHERE LoanID=?""",
            (lid,),
        ).fetchone()
        if not loan:
            conn.rollback()
            flash("Loan not found.", "danger")
            return redirect(url_for("loans.loans"))

        if new_status == "Approved":
            if loan["Status"] != "Pending" or loan["DisbursedAt"]:
                conn.rollback()
                flash("Only an undistributed pending loan can be approved.", "warning")
                return redirect(url_for("loans.loans"))
            try:
                final_rate = float(request.form.get("interest_rate", ""))
            except ValueError:
                final_rate = 0
            if not 0.1 <= final_rate <= 30:
                conn.rollback()
                flash("Set a final interest rate between 0.1% and 30% before approval.", "danger")
                return redirect(url_for("loans.loans"))

            account_value = request.form.get("disbursement_account_id", "").strip()
            if account_value and not account_value.isdecimal():
                conn.rollback()
                flash("Choose a valid disbursement account.", "danger")
                return redirect(url_for("loans.loans"))
            account_id = int(account_value) if account_value else loan["DisbursementAccountID"]
            account = conn.execute(
                """SELECT AccountID, AccountNumber, Balance FROM ACCOUNT
                   WHERE AccountID=? AND CustomerID=? AND Status='Active'""",
                (account_id, loan["CustomerID"]),
            ).fetchone() if account_id else None
            if not account:
                conn.rollback()
                flash("An active account for this customer is required before approving the loan.", "danger")
                return redirect(url_for("loans.loans"))

            balance_after = float(Decimal(str(account["Balance"])) + Decimal(str(loan["Amount"])))
            conn.execute(
                """INSERT INTO TRANSACTIONS
                   (AccountID, TransactionType, Amount, Description, BalanceAfter)
                   VALUES (?, 'Deposit', ?, ?, ?)""",
                (account["AccountID"], loan["Amount"], f"Loan disbursement #{lid}", balance_after),
            )
            updated = conn.execute(
                """UPDATE LOAN
                   SET Status='Approved', InterestRate=?, DisbursementAccountID=?, DisbursedAt=datetime('now')
                   WHERE LoanID=? AND Status='Pending' AND DisbursedAt IS NULL""",
                (final_rate, account["AccountID"], lid),
            )
            if updated.rowcount != 1:
                conn.rollback()
                flash("This loan has already been processed.", "warning")
                return redirect(url_for("loans.loans"))
            conn.commit()
            flash(
                f"Loan approved. MAD {loan['Amount']:,.2f} was deposited into {account['AccountNumber']}.",
                "success",
            )
        elif new_status == "Rejected":
            if loan["Status"] != "Pending":
                conn.rollback()
                flash("Only pending loans can be rejected.", "warning")
                return redirect(url_for("loans.loans"))
            conn.execute("UPDATE LOAN SET Status='Rejected' WHERE LoanID=? AND Status='Pending'", (lid,))
            conn.commit()
            flash("Loan rejected.", "success")
        else:
            if loan["Status"] != "Approved":
                conn.rollback()
                flash("Only approved loans can be closed.", "warning")
                return redirect(url_for("loans.loans"))
            conn.execute("UPDATE LOAN SET Status='Closed' WHERE LoanID=? AND Status='Approved'", (lid,))
            conn.commit()
            flash("Loan closed.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("loans.loans"))


@loans_bp.route("/loans/delete/<int:lid>", methods=["POST"])
@login_required
def delete_loan(lid):
    if session.get("user", {}).get("role") not in ("Admin", "Owner"):
        flash("Only Admin or Owner can delete a loan.", "danger")
        return redirect(url_for("loans.loans"))
    conn = get_db()
    try:
        conn.execute("DELETE FROM LOAN WHERE LoanID=?", (lid,))
        conn.commit()
        flash("Loan record deleted.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("loans.loans"))


@loans_bp.route("/loans/get/<int:lid>")
@login_required
def get_loan(lid):
    conn = get_db()
    row = conn.execute("SELECT * FROM LOAN WHERE LoanID=?", (lid,)).fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({}), 404
