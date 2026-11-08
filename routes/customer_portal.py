"""Self-service banking views and operations for approved customer logins."""

from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from database import get_db

customer_portal_bp = Blueprint("customer_portal", __name__)
CENT = Decimal("0.01")


def parse_amount(value):
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount <= 0 or amount != amount.quantize(CENT):
            return None
        return amount
    except (InvalidOperation, ValueError):
        return None


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


@customer_portal_bp.post("/my-banking/withdraw")
@customer_required
def withdraw():
    """Withdraw funds from an active account owned by the signed-in customer."""
    amount = parse_amount(request.form.get("amount", ""))
    account_id = request.form.get("account_id", "")
    if amount is None or not account_id.isdecimal():
        flash("Enter a valid account and positive amount with up to two decimals.", "danger")
        return redirect(url_for("customer_portal.home"))

    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        account = conn.execute(
            """SELECT a.AccountID, a.Balance, a.Status
               FROM ACCOUNT a JOIN CUSTOMER c ON c.CustomerID=a.CustomerID
               WHERE a.AccountID=? AND lower(c.Email)=lower(?)""",
            (int(account_id), session["user"]["email"]),
        ).fetchone()
        if not account:
            conn.rollback()
            flash("That account is not linked to your customer profile.", "danger")
            return redirect(url_for("customer_portal.home"))
        if account["Status"] != "Active":
            conn.rollback()
            flash("Only active accounts can be used for withdrawals.", "danger")
            return redirect(url_for("customer_portal.home"))
        if amount > Decimal(str(account["Balance"])):
            conn.rollback()
            flash("Insufficient balance.", "danger")
            return redirect(url_for("customer_portal.home"))

        balance_after = float(Decimal(str(account["Balance"])) - amount)
        conn.execute(
            """INSERT INTO TRANSACTIONS
               (AccountID, TransactionType, Amount, Description, BalanceAfter)
               VALUES (?, 'Withdrawal', ?, 'Customer withdrawal', ?)""",
            (account["AccountID"], float(amount), balance_after),
        )
        conn.commit()
        flash(f"MAD {amount:,.2f} withdrawn successfully.", "success")
    except Exception as error:
        conn.rollback()
        flash(f"Could not complete withdrawal: {error}", "danger")
    finally:
        conn.close()
    return redirect(url_for("customer_portal.home"))


@customer_portal_bp.post("/my-banking/transfer")
@customer_required
def transfer():
    """Transfer funds from the signed-in customer's account to an active account."""
    amount = parse_amount(request.form.get("amount", ""))
    source_id = request.form.get("from_account_id", "")
    destination_number = request.form.get("to_account_number", "").strip()
    if amount is None or not source_id.isdecimal() or not destination_number:
        flash("Enter a valid source, destination account number, and positive amount.", "danger")
        return redirect(url_for("customer_portal.home"))

    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        source = conn.execute(
            """SELECT a.AccountID, a.AccountNumber, a.Balance, a.Status
               FROM ACCOUNT a JOIN CUSTOMER c ON c.CustomerID=a.CustomerID
               WHERE a.AccountID=? AND lower(c.Email)=lower(?)""",
            (int(source_id), session["user"]["email"]),
        ).fetchone()
        destination = conn.execute(
            """SELECT AccountID, AccountNumber, Balance, Status
               FROM ACCOUNT WHERE AccountNumber=?""",
            (destination_number,),
        ).fetchone()

        if not source or not destination:
            conn.rollback()
            flash("Source or destination account was not found.", "danger")
            return redirect(url_for("customer_portal.home"))
        if source["AccountID"] == destination["AccountID"]:
            conn.rollback()
            flash("Source and destination accounts must differ.", "danger")
            return redirect(url_for("customer_portal.home"))
        if source["Status"] != "Active" or destination["Status"] != "Active":
            conn.rollback()
            flash("Both accounts must be active to transfer funds.", "danger")
            return redirect(url_for("customer_portal.home"))
        source_balance = Decimal(str(source["Balance"]))
        if amount > source_balance:
            conn.rollback()
            flash("Insufficient balance.", "danger")
            return redirect(url_for("customer_portal.home"))

        conn.execute(
            """INSERT INTO TRANSACTIONS
               (AccountID, TransactionType, Amount, Description, BalanceAfter)
               VALUES (?, 'Transfer', ?, ?, ?)""",
            (
                source["AccountID"], float(amount),
                f"Transfer to {destination['AccountNumber']}",
                float(source_balance - amount),
            ),
        )
        conn.execute(
            """INSERT INTO TRANSACTIONS
               (AccountID, TransactionType, Amount, Description, BalanceAfter)
               VALUES (?, 'Deposit', ?, ?, ?)""",
            (
                destination["AccountID"], float(amount),
                f"Transfer from {source['AccountNumber']}",
                float(Decimal(str(destination["Balance"])) + amount),
            ),
        )
        conn.commit()
        flash(f"MAD {amount:,.2f} transferred successfully.", "success")
    except Exception as error:
        conn.rollback()
        flash(f"Could not complete transfer: {error}", "danger")
    finally:
        conn.close()
    return redirect(url_for("customer_portal.home"))
