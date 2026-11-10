"""
routes/accounts.py - Account management: create, view, freeze/activate
Uses CustomerAccountSummary VIEW and JOIN queries.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db
from functools import wraps
import random

from morocco_banking import generate_moroccan_rib, generate_card_number, format_moroccan_rib
from card_tiers import get_card_tier

accounts_bp = Blueprint("accounts", __name__)


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
            flash("Only an owner or admin can open a bank account.", "danger")
            return redirect(url_for("accounts.accounts"))
        return f(*args, **kwargs)
    return decorated


def generate_account_number(branch_id=None):
    """Generate a valid 24-digit Moroccan RIB (Bank Al-Maghrib standard)."""
    return generate_moroccan_rib(branch_id=branch_id)


@accounts_bp.route("/accounts")
@login_required
def accounts():
    """List all accounts using the CustomerAccountSummary view."""
    search = request.args.get("q", "").strip()
    conn = get_db()

    # Use the VIEW for a join-based summary
    if search:
        rows = conn.execute("""
            SELECT * FROM CustomerAccountSummary
            WHERE CustomerName LIKE ? OR AccountNumber LIKE ? OR AccountType LIKE ?
            ORDER BY AccountID
        """, (f"%{search}%", f"%{search}%", f"%{search}%")).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM CustomerAccountSummary ORDER BY AccountID"
        ).fetchall()

    # Customer list for the add-account modal dropdown
    customers = conn.execute(
        "SELECT CustomerID, Name FROM CUSTOMER ORDER BY Name"
    ).fetchall()
    branches = conn.execute(
        "SELECT BranchID, BranchName, City FROM BRANCH ORDER BY BranchName"
    ).fetchall()

    # Aggregate stats
    stats = conn.execute("""
        SELECT
            COUNT(*)                          AS total,
            SUM(CASE WHEN Status='Active'  THEN 1 ELSE 0 END) AS active,
            SUM(CASE WHEN Status='Frozen'  THEN 1 ELSE 0 END) AS frozen,
            COALESCE(SUM(Balance), 0)         AS total_balance,
            COALESCE(AVG(Balance), 0)         AS avg_balance
        FROM ACCOUNT
    """).fetchone()

    conn.close()
    return render_template(
        "accounts.html",
        accounts=rows,
        customers=customers,
        branches=branches,
        stats=stats,
        search=search,
        can_create_account=session.get("user", {}).get("role") in ("Owner", "Admin"),
    )


@accounts_bp.route("/accounts/add", methods=["POST"])
@login_required
@owner_or_admin_required
def add_account():
    data = request.form
    cid      = data.get("customer_id")
    atype    = data.get("account_type")
    card_tier = data.get("card_tier", "standard").strip() or "standard"
    balance  = float(data.get("balance", 0))
    branch   = data.get("branch_id") or None

    if not all([cid, atype]):
        flash("Customer and account type are required.", "danger")
        return redirect(url_for("accounts.accounts"))

    tier_info = get_card_tier(card_tier)
    max_balance = tier_info.get("max_balance")
    if max_balance is not None and balance > max_balance:
        flash(f"Opening deposit of MAD {balance:,.2f} exceeds the subscription ceiling (Max Balance: {tier_info['plafond']}).", "danger")
        return redirect(url_for("accounts.accounts"))

    conn = get_db()
    try:
        # Generate unique 24-digit Moroccan RIB and 16-digit Luhn card number
        acc_no = generate_moroccan_rib(branch_id=branch)
        while conn.execute("SELECT 1 FROM ACCOUNT WHERE AccountNumber=?", (acc_no,)).fetchone():
            acc_no = generate_moroccan_rib(branch_id=branch)

        card_no = generate_card_number(acc_no)

        conn.execute("""
            INSERT INTO ACCOUNT (CustomerID, AccountNumber, CardNumber, CardTier, AccountType, Balance, BranchID)
            VALUES (?,?,?,?,?,?,?)
        """, (cid, acc_no, card_no, card_tier, atype, balance, branch))
        conn.commit()

        # Record opening deposit if balance > 0
        if balance > 0:
            conn.execute("""
                INSERT INTO TRANSACTIONS (AccountID, TransactionType, Amount, Description, BalanceAfter)
                VALUES (
                    (SELECT AccountID FROM ACCOUNT WHERE AccountNumber=?),
                    'Deposit', ?, 'Account opening deposit', ?
                )
            """, (acc_no, balance, balance))
            conn.commit()

        flash(f"Account opened successfully. Moroccan RIB: {format_moroccan_rib(acc_no)}", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("accounts.accounts"))


@accounts_bp.route("/accounts/status/<int:aid>", methods=["POST"])
@login_required
def toggle_status(aid):
    """Freeze or activate an account."""
    conn = get_db()
    try:
        current = conn.execute("SELECT Status FROM ACCOUNT WHERE AccountID=?", (aid,)).fetchone()
        if current:
            new_status = "Active" if current["Status"] == "Frozen" else "Frozen"
            conn.execute("UPDATE ACCOUNT SET Status=? WHERE AccountID=?", (new_status, aid))
            conn.commit()
            flash(f"Account status changed to {new_status}.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("accounts.accounts"))


@accounts_bp.route("/accounts/get/<int:aid>")
@login_required
def get_account(aid):
    conn = get_db()
    row = conn.execute("SELECT * FROM ACCOUNT WHERE AccountID=?", (aid,)).fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({}), 404
