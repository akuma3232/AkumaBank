"""Self-service banking views and operations for approved customer logins."""

from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from database import TRANSFER_FEE, get_db

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
    loans = []
    loan_summary = {"total_disbursed": 0}
    total_account_balance = Decimal("0.00")
    if customer:
        accounts = conn.execute(
            """SELECT a.AccountID, a.AccountNumber, a.CardNumber, a.CardTier, a.AccountType, a.Balance, a.Status,
                      a.OpeningDate, b.BranchName, b.City
               FROM ACCOUNT a LEFT JOIN BRANCH b ON a.BranchID = b.BranchID
               WHERE a.CustomerID=? ORDER BY a.AccountID""",
            (customer["CustomerID"],),
        ).fetchall()
        total_account_balance = sum(
            (Decimal(str(account["Balance"])) for account in accounts),
            Decimal("0.00"),
        )
        transactions = conn.execute(
            """SELECT t.TransactionDate, t.TransactionType, t.Amount, t.Description,
                      t.BalanceAfter, a.AccountNumber
               FROM TRANSACTIONS t JOIN ACCOUNT a ON a.AccountID=t.AccountID
               WHERE a.CustomerID=? ORDER BY t.TransactionDate DESC, t.TransactionID DESC
               LIMIT 50""",
            (customer["CustomerID"],),
        ).fetchall()
        loans = conn.execute(
            """SELECT l.LoanType, l.Amount, l.InterestRate, l.StartDate, l.Status,
                      l.DisbursedAt, a.AccountNumber AS DisbursementAccount
               FROM LOAN l LEFT JOIN ACCOUNT a ON a.AccountID=l.DisbursementAccountID
               WHERE l.CustomerID=? ORDER BY l.LoanID DESC""",
            (customer["CustomerID"],),
        ).fetchall()
        loan_summary = conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN DisbursedAt IS NOT NULL THEN Amount ELSE 0 END), 0)
                      AS total_disbursed
               FROM LOAN WHERE CustomerID=?""",
            (customer["CustomerID"],),
        ).fetchone()

        closure_requests = conn.execute(
            """SELECT * FROM ACCOUNT_CLOSURE_REQUEST WHERE CustomerID=? ORDER BY RequestedAt DESC""",
            (customer["CustomerID"],),
        ).fetchall()
        pending_closure_map = {r["AccountID"]: dict(r) for r in closure_requests if r["Status"] == "Pending"}

        opening_requests = conn.execute(
            """SELECT * FROM ACCOUNT_OPENING_REQUEST WHERE CustomerID=? ORDER BY RequestedAt DESC""",
            (customer["CustomerID"],),
        ).fetchall()
        branches = conn.execute("SELECT BranchID, BranchName, City FROM BRANCH ORDER BY BranchName").fetchall()
    else:
        closure_requests = []
        pending_closure_map = {}
        opening_requests = []
        branches = []
    conn.close()
    return render_template(
        "customer_portal.html",
        customer=customer,
        accounts=accounts,
        active_accounts=[account for account in accounts if account["Status"] == "Active"],
        transactions=transactions,
        loans=loans,
        loan_summary=loan_summary,
        total_account_balance=total_account_balance,
        transfer_fee=TRANSFER_FEE,
        closure_requests=closure_requests,
        pending_closure_map=pending_closure_map,
        opening_requests=opening_requests,
        branches=branches,
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
    raw_dest = request.form.get("to_account_number", "").strip()
    clean_dest = raw_dest.replace(" ", "").upper()
    if clean_dest.startswith("MA64") and len(clean_dest) == 28:
        destination_number = clean_dest[4:]
    else:
        destination_number = clean_dest

    if amount is None or not source_id.isdecimal() or not destination_number:
        flash("Enter a valid source, destination account number (24-digit RIB or IBAN), and positive amount.", "danger")
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
               FROM ACCOUNT
               WHERE AccountNumber=? OR REPLACE(AccountNumber, ' ', '')=?""",
            (destination_number, destination_number),
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
        if amount <= TRANSFER_FEE:
            conn.rollback()
            flash(f"Transfer amount must exceed the MAD {TRANSFER_FEE:.2f} bank fee.", "danger")
            return redirect(url_for("customer_portal.home"))

        # Fee is deducted from what the recipient receives — sender loses exactly `amount`
        received_amount = amount - TRANSFER_FEE
        source_after_transfer = source_balance - amount
        conn.execute(
            """INSERT INTO TRANSACTIONS
               (AccountID, TransactionType, Amount, Description, BalanceAfter)
               VALUES (?, 'Transfer', ?, ?, ?)""",
            (
                source["AccountID"], float(amount),
                f"Transfer to {destination['AccountNumber']}",
                float(source_after_transfer),
            ),
        )
        conn.execute(
            """INSERT INTO TRANSACTIONS
               (AccountID, TransactionType, Amount, Description, BalanceAfter)
               VALUES (?, 'Deposit', ?, ?, ?)""",
            (
                destination["AccountID"], float(received_amount),
                f"Transfer from {source['AccountNumber']} (MAD {TRANSFER_FEE:.2f} bank fee deducted)",
                float(Decimal(str(destination["Balance"])) + received_amount),
            ),
        )
        conn.commit()
        flash(
            f"MAD {amount:,.2f} sent. Recipient receives MAD {received_amount:,.2f} after the MAD {TRANSFER_FEE:,.2f} bank fee.",
            "success",
        )
    except Exception as error:
        conn.rollback()
        flash(f"Could not complete transfer: {error}", "danger")
    finally:
        conn.close()
    return redirect(url_for("customer_portal.home"))


@customer_portal_bp.post("/my-banking/loans")
@customer_required
def request_loan():
    loan_type = request.form.get("loan_type", "")
    amount = parse_amount(request.form.get("amount", ""))
    account_id = request.form.get("account_id", "")
    if loan_type not in ("Home", "Car", "Personal", "Education", "Business"):
        flash("Choose a valid loan type.", "danger")
        return redirect(url_for("customer_portal.home"))
    if amount is None or amount < Decimal("1000") or amount > Decimal("100000000"):
        flash("Enter a loan amount between MAD 1,000 and MAD 100,000,000.", "danger")
        return redirect(url_for("customer_portal.home"))
    if not account_id.isdecimal():
        flash("Choose an active account to receive the loan funds.", "danger")
        return redirect(url_for("customer_portal.home"))

    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        customer = conn.execute(
            "SELECT CustomerID FROM CUSTOMER WHERE lower(Email)=lower(?)",
            (session["user"]["email"],),
        ).fetchone()
        if not customer:
            conn.rollback()
            flash("A verified customer profile is required to request a loan.", "danger")
            return redirect(url_for("customer_portal.home"))
        account = conn.execute(
            """SELECT AccountID FROM ACCOUNT
               WHERE AccountID=? AND CustomerID=? AND Status='Active'""",
            (int(account_id), customer["CustomerID"]),
        ).fetchone()
        if not account:
            conn.rollback()
            flash("Choose an active account linked to your customer profile.", "danger")
            return redirect(url_for("customer_portal.home"))
        conn.execute(
            """INSERT INTO LOAN
               (CustomerID, LoanType, Amount, InterestRate, StartDate, Status, DisbursementAccountID)
               VALUES (?, ?, ?, 1.0, date('now'), 'Pending', ?)""",
            (customer["CustomerID"], loan_type, float(amount), account["AccountID"]),
        )
        conn.commit()
        flash("Loan request submitted for staff review. The displayed rate is provisional.", "success")
    except Exception as error:
        conn.rollback()
        flash(f"Could not submit loan request: {error}", "danger")
    finally:
        conn.close()
    return redirect(url_for("customer_portal.home"))


@customer_portal_bp.post("/my-banking/account/<int:aid>/request-closure")
@customer_required
def request_account_closure(aid):
    """Customer submits an account closure request."""
    email = session.get("user", {}).get("email")
    reason = request.form.get("reason", "Customer requested closure").strip()

    conn = get_db()
    customer = conn.execute("SELECT CustomerID FROM CUSTOMER WHERE lower(Email)=lower(?)", (email,)).fetchone()
    if not customer:
        conn.close()
        flash("Customer profile not found.", "danger")
        return redirect(url_for("customer_portal.home"))

    account = conn.execute(
        "SELECT * FROM ACCOUNT WHERE AccountID=? AND CustomerID=?",
        (aid, customer["CustomerID"]),
    ).fetchone()

    if not account:
        conn.close()
        flash("Account not found or access denied.", "danger")
        return redirect(url_for("customer_portal.home"))

    if account["Status"] == "Closed":
        conn.close()
        flash("This account is already closed.", "warning")
        return redirect(url_for("customer_portal.home"))

    if float(account["Balance"] or 0) < 0:
        conn.close()
        flash(
            f"This account is overdrawn by MAD {abs(float(account['Balance'])):,.2f}. "
            "Settle the negative balance before requesting closure.",
            "danger",
        )
        return redirect(url_for("customer_portal.home"))

    # Check for existing pending request
    existing = conn.execute(
        "SELECT 1 FROM ACCOUNT_CLOSURE_REQUEST WHERE AccountID=? AND Status='Pending'",
        (aid,),
    ).fetchone()
    if existing:
        conn.close()
        flash("A closure request for this account is already pending review.", "info")
        return redirect(url_for("customer_portal.home"))

    conn.execute("""
        INSERT INTO ACCOUNT_CLOSURE_REQUEST (AccountID, CustomerID, Reason, Status)
        VALUES (?, ?, ?, 'Pending')
    """, (aid, customer["CustomerID"], reason))
    conn.commit()
    conn.close()

    flash("Account closure request submitted for review. A bank officer will process your request.", "success")
    return redirect(url_for("customer_portal.home"))


@customer_portal_bp.post("/my-banking/request-account-opening")
@customer_required
def request_account_opening():
    """Customer submits a request to open an additional account."""
    email = session.get("user", {}).get("email")
    conn = get_db()
    customer = conn.execute("SELECT CustomerID FROM CUSTOMER WHERE lower(Email)=lower(?)", (email,)).fetchone()
    if not customer:
        conn.close()
        flash("Customer profile not found.", "danger")
        return redirect(url_for("customer_portal.home"))

    account_type = request.form.get("account_type", "Current").strip()
    card_tier = request.form.get("card_tier", "standard").strip()
    branch_id = request.form.get("branch_id") or None
    reason = request.form.get("reason", "Additional account opening").strip()
    try:
        initial_deposit = max(0.0, float(request.form.get("initial_deposit", 0.0)))
    except ValueError:
        initial_deposit = 0.0

    conn.execute("""
        INSERT INTO ACCOUNT_OPENING_REQUEST (CustomerID, AccountType, CardTier, InitialDeposit, BranchID, Reason, Status)
        VALUES (?, ?, ?, ?, ?, ?, 'Pending')
    """, (customer["CustomerID"], account_type, card_tier, initial_deposit, branch_id, reason))
    conn.commit()
    conn.close()

    flash("Account opening request submitted successfully. Our operations team will review and approve your account.", "success")
    return redirect(url_for("customer_portal.home"))


