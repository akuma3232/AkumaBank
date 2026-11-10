"""
routes/transactions.py - Deposit, Withdraw, Fund Transfer
Uses the TransferMoney stored-procedure equivalent and the trigger UpdateBalanceAfterTransaction.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db, transfer_money, DEPOSIT_FEE
from card_tiers import get_card_tier
from functools import wraps

transactions_bp = Blueprint("transactions", __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def owner_or_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("user", {}).get("role") not in ("Owner", "Admin"):
            flash("Only an owner or admin can make deposits.", "danger")
            return redirect(url_for("transactions.transactions"))
        return f(*args, **kwargs)
    return decorated


@transactions_bp.route("/transactions")
@login_required
def transactions():
    """View all transactions with filters."""
    search   = request.args.get("q", "").strip()
    txn_type = request.args.get("type", "").strip()
    conn     = get_db()

    # Use TransactionDetails VIEW (join query)
    base_query = "SELECT * FROM TransactionDetails"
    params     = []
    conditions = []

    if search:
        conditions.append("(CustomerName LIKE ? OR AccountNumber LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if txn_type:
        conditions.append("TransactionType = ?")
        params.append(txn_type)

    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)
    base_query += " ORDER BY TransactionDate DESC LIMIT 200"

    txns     = conn.execute(base_query, params).fetchall()
    accounts = conn.execute(
        "SELECT a.AccountID, a.AccountNumber, c.Name FROM ACCOUNT a JOIN CUSTOMER c ON a.CustomerID=c.CustomerID WHERE a.Status='Active' ORDER BY a.AccountNumber"
    ).fetchall()

    # Aggregate stats
    stats = conn.execute("""
        SELECT
            COUNT(*)                                                        AS total_count,
            COALESCE(SUM(CASE WHEN TransactionType='Deposit'    THEN Amount ELSE 0 END), 0) AS total_deposits,
            COALESCE(SUM(CASE WHEN TransactionType='Withdrawal' THEN Amount ELSE 0 END), 0) AS total_withdrawals,
            COALESCE(SUM(CASE WHEN TransactionType='Transfer'   THEN Amount ELSE 0 END), 0) AS total_transfers
        FROM TRANSACTIONS
    """).fetchone()

    conn.close()
    return render_template(
        "transactions.html",
        txns=txns,
        accounts=accounts,
        stats=stats,
        search=search,
        txn_type=txn_type,
        can_deposit=session.get("user", {}).get("role") in ("Owner", "Admin"),
    )


@transactions_bp.route("/transactions/deposit", methods=["POST"])
@login_required
@owner_or_admin_required
def deposit():
    """Credit an amount to an account after deducting the MAD 1.00 deposit fee."""
    account_id  = request.form.get("account_id")
    amount      = float(request.form.get("amount", 0))
    description = request.form.get("description", "Cash deposit").strip()

    if not account_id or amount <= 0:
        flash("Valid account and positive amount required.", "danger")
        return redirect(url_for("transactions.transactions"))

    from decimal import Decimal
    deposit_amount = Decimal(str(amount))
    if deposit_amount <= DEPOSIT_FEE:
        flash(f"Deposit amount must exceed the MAD {DEPOSIT_FEE:.2f} bank fee.", "danger")
        return redirect(url_for("transactions.transactions"))

    credited_amount = deposit_amount - DEPOSIT_FEE   # what actually lands in the account

    conn = get_db()
    try:
        acct = conn.execute("SELECT Balance, Status, CardTier FROM ACCOUNT WHERE AccountID=?", (account_id,)).fetchone()
        if not acct:
            flash("Account not found.", "danger")
            return redirect(url_for("transactions.transactions"))
        if acct["Status"] != "Active":
            flash("Account is not active.", "danger")
            return redirect(url_for("transactions.transactions"))

        new_balance = Decimal(str(acct["Balance"])) + credited_amount
        tier_info = get_card_tier(acct["CardTier"] if "CardTier" in acct.keys() else "standard")
        max_balance = tier_info.get("max_balance")
        if max_balance is not None and new_balance > Decimal(str(max_balance)):
            flash(
                f"Deposit rejected: The new balance (MAD {new_balance:,.2f}) would exceed the account ceiling (Max Balance: {tier_info['plafond']}).",
                "danger",
            )
            return redirect(url_for("transactions.transactions"))
        # INSERT fires the UpdateBalanceAfterTransaction trigger automatically
        conn.execute("""
            INSERT INTO TRANSACTIONS (AccountID, TransactionType, Amount, Description, BalanceAfter)
            VALUES (?, 'Deposit', ?, ?, ?)
        """, (account_id, float(credited_amount), f"{description} (MAD {DEPOSIT_FEE:.2f} bank fee deducted)", float(new_balance)))
        conn.commit()
        flash(
            f"MAD {credited_amount:,.2f} credited (MAD {DEPOSIT_FEE:,.2f} bank fee deducted from MAD {deposit_amount:,.2f} deposit).",
            "success",
        )
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("transactions.transactions"))


@transactions_bp.route("/transactions/withdraw", methods=["POST"])
@login_required
def withdraw():
    """Debit an amount from an account."""
    account_id  = request.form.get("account_id")
    amount      = float(request.form.get("amount", 0))
    description = request.form.get("description", "ATM withdrawal").strip()

    if not account_id or amount <= 0:
        flash("Valid account and positive amount required.", "danger")
        return redirect(url_for("transactions.transactions"))

    conn = get_db()
    try:
        acct = conn.execute("SELECT Balance, Status FROM ACCOUNT WHERE AccountID=?", (account_id,)).fetchone()
        if not acct:
            flash("Account not found.", "danger")
            return redirect(url_for("transactions.transactions"))
        if acct["Status"] != "Active":
            flash("Account is not active.", "danger")
            return redirect(url_for("transactions.transactions"))
        if acct["Balance"] < amount:
            flash("Insufficient balance.", "danger")
            return redirect(url_for("transactions.transactions"))

        new_balance = acct["Balance"] - amount
        conn.execute("""
            INSERT INTO TRANSACTIONS (AccountID, TransactionType, Amount, Description, BalanceAfter)
            VALUES (?, 'Withdrawal', ?, ?, ?)
        """, (account_id, amount, description, new_balance))
        conn.commit()
        flash(f"MAD {amount:,.2f} withdrawn successfully.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("transactions.transactions"))


@transactions_bp.route("/transactions/transfer", methods=["POST"])
@login_required
def transfer():
    """Fund transfer via the TransferMoney stored-procedure equivalent."""
    from_id = int(request.form.get("from_account_id", 0))
    to_id   = int(request.form.get("to_account_id", 0))
    amount  = float(request.form.get("amount", 0))

    if not from_id or not to_id or amount <= 0:
        flash("All transfer fields are required.", "danger")
        return redirect(url_for("transactions.transactions"))
    if from_id == to_id:
        flash("Source and destination accounts must differ.", "danger")
        return redirect(url_for("transactions.transactions"))

    result = transfer_money(from_id, to_id, amount)
    flash(result["message"], "success" if result["success"] else "danger")
    return redirect(url_for("transactions.transactions"))
