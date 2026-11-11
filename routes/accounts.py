"""
routes/accounts.py - Account management: create, view, freeze/activate
Uses CustomerAccountSummary VIEW and JOIN queries.
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db, close_account_permanently
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
            SUM(CASE WHEN Status='Closed'  THEN 1 ELSE 0 END) AS closed,
            COALESCE(SUM(Balance), 0)         AS total_balance,
            COALESCE(AVG(Balance), 0)         AS avg_balance
        FROM ACCOUNT
    """).fetchone()

    # Closure requests
    closure_requests = conn.execute("""
        SELECT r.*, a.AccountNumber, a.Balance, a.CardTier, c.Name as CustomerName
        FROM ACCOUNT_CLOSURE_REQUEST r
        JOIN ACCOUNT a ON a.AccountID = r.AccountID
        JOIN CUSTOMER c ON c.CustomerID = r.CustomerID
        ORDER BY CASE WHEN r.Status='Pending' THEN 1 ELSE 2 END, r.RequestedAt DESC
    """).fetchall()
    pending_closures_count = sum(1 for r in closure_requests if r["Status"] == "Pending")

    # Document requests
    document_requests = conn.execute("""
        SELECT dr.*, c.Name as CustomerName, a.AccountNumber, a.CardTier, a.AccountType
        FROM DOCUMENT_REQUEST dr
        JOIN CUSTOMER c ON c.CustomerID = dr.CustomerID
        LEFT JOIN ACCOUNT a ON a.AccountID = dr.AccountID
        ORDER BY CASE WHEN dr.Status='Pending' THEN 1 ELSE 2 END, dr.RequestedAt DESC
    """).fetchall()
    pending_documents_count = sum(1 for r in document_requests if r["Status"] == "Pending")

    # Account opening requests
    opening_requests = conn.execute("""
        SELECT aor.*, c.Name as CustomerName, c.Email, c.Phone, b.BranchName
        FROM ACCOUNT_OPENING_REQUEST aor
        JOIN CUSTOMER c ON c.CustomerID = aor.CustomerID
        LEFT JOIN BRANCH b ON b.BranchID = aor.BranchID
        ORDER BY CASE WHEN aor.Status='Pending' THEN 1 ELSE 2 END, aor.RequestedAt DESC
    """).fetchall()
    pending_openings_count = sum(1 for r in opening_requests if r["Status"] == "Pending")

    # Loan requests
    loan_requests = conn.execute("""
        SELECT l.*, c.Name as CustomerName, a.AccountNumber as DisbAccount
        FROM LOAN l
        JOIN CUSTOMER c ON c.CustomerID = l.CustomerID
        LEFT JOIN ACCOUNT a ON a.AccountID = l.DisbursementAccountID
        ORDER BY CASE WHEN l.Status='Pending' THEN 1 ELSE 2 END, l.StartDate DESC
    """).fetchall()
    pending_loans_count = sum(1 for r in loan_requests if r["Status"] == "Pending")

    # Password reset requests
    password_requests = conn.execute("""
        SELECT pr.*, u.Username, u.Email, u.FullName
        FROM PASSWORD_RESET_REQUEST pr
        JOIN USERS u ON u.UserID = pr.UserID
        ORDER BY CASE WHEN pr.Status='Pending' THEN 1 ELSE 2 END, pr.RequestedAt DESC
    """).fetchall()
    pending_passwords_count = sum(1 for r in password_requests if r["Status"] == "Pending")

    # Customer signup / creation requests (from customer page)
    signup_requests = conn.execute("""
        SELECT UserID, FullName, Email, DateOfBirth, Phone, Address, NationalID
        FROM USERS
        WHERE Role='Customer' AND ApprovalStatus='Pending'
        ORDER BY UserID DESC
    """).fetchall()
    pending_signups_count = len(signup_requests)

    total_pending_requests = (
        pending_signups_count +
        pending_closures_count +
        pending_documents_count +
        pending_openings_count +
        pending_loans_count +
        pending_passwords_count
    )

    conn.close()
    return render_template(
        "accounts.html",
        accounts=rows,
        customers=customers,
        branches=branches,
        stats=stats,
        search=search,
        signup_requests=signup_requests,
        pending_signups_count=pending_signups_count,
        closure_requests=closure_requests,
        pending_closures_count=pending_closures_count,
        document_requests=document_requests,
        pending_documents_count=pending_documents_count,
        opening_requests=opening_requests,
        pending_openings_count=pending_openings_count,
        loan_requests=loan_requests,
        pending_loans_count=pending_loans_count,
        password_requests=password_requests,
        pending_passwords_count=pending_passwords_count,
        total_pending_requests=total_pending_requests,
        can_create_account=session.get("user", {}).get("role") in ("Owner", "Admin"),
    )


@accounts_bp.route("/requests")
@login_required
@owner_or_admin_required
def requests_center():
    """Unified Operations Requests Center (all bank requests in one dedicated place)."""
    conn = get_db()

    signup_requests = conn.execute("""
        SELECT UserID, FullName, Email, DateOfBirth, Phone, Address, NationalID
        FROM USERS
        WHERE Role='Customer' AND ApprovalStatus='Pending'
        ORDER BY UserID DESC
    """).fetchall()
    pending_signups_count = len(signup_requests)

    closure_requests = conn.execute("""
        SELECT r.*, a.AccountNumber, a.Balance, a.CardTier, c.Name as CustomerName
        FROM ACCOUNT_CLOSURE_REQUEST r
        JOIN ACCOUNT a ON a.AccountID = r.AccountID
        JOIN CUSTOMER c ON c.CustomerID = r.CustomerID
        ORDER BY CASE WHEN r.Status='Pending' THEN 1 ELSE 2 END, r.RequestedAt DESC
    """).fetchall()
    pending_closures_count = sum(1 for r in closure_requests if r["Status"] == "Pending")

    document_requests = conn.execute("""
        SELECT dr.*, c.Name as CustomerName, a.AccountNumber, a.CardTier, a.AccountType
        FROM DOCUMENT_REQUEST dr
        JOIN CUSTOMER c ON c.CustomerID = dr.CustomerID
        LEFT JOIN ACCOUNT a ON a.AccountID = dr.AccountID
        ORDER BY CASE WHEN dr.Status='Pending' THEN 1 ELSE 2 END, dr.RequestedAt DESC
    """).fetchall()
    pending_documents_count = sum(1 for r in document_requests if r["Status"] == "Pending")

    opening_requests = conn.execute("""
        SELECT aor.*, c.Name as CustomerName, c.Email, c.Phone, b.BranchName
        FROM ACCOUNT_OPENING_REQUEST aor
        JOIN CUSTOMER c ON c.CustomerID = aor.CustomerID
        LEFT JOIN BRANCH b ON b.BranchID = aor.BranchID
        ORDER BY CASE WHEN aor.Status='Pending' THEN 1 ELSE 2 END, aor.RequestedAt DESC
    """).fetchall()
    pending_openings_count = sum(1 for r in opening_requests if r["Status"] == "Pending")

    loan_requests = conn.execute("""
        SELECT l.*, c.Name as CustomerName, a.AccountNumber as DisbAccount
        FROM LOAN l
        JOIN CUSTOMER c ON c.CustomerID = l.CustomerID
        LEFT JOIN ACCOUNT a ON a.AccountID = l.DisbursementAccountID
        ORDER BY CASE WHEN l.Status='Pending' THEN 1 ELSE 2 END, l.StartDate DESC
    """).fetchall()
    pending_loans_count = sum(1 for r in loan_requests if r["Status"] == "Pending")

    password_requests = conn.execute("""
        SELECT pr.*, u.Username, u.Email, u.FullName
        FROM PASSWORD_RESET_REQUEST pr
        JOIN USERS u ON u.UserID = pr.UserID
        ORDER BY CASE WHEN pr.Status='Pending' THEN 1 ELSE 2 END, pr.RequestedAt DESC
    """).fetchall()
    pending_passwords_count = sum(1 for r in password_requests if r["Status"] == "Pending")

    total_pending_requests = (
        pending_signups_count +
        pending_closures_count +
        pending_documents_count +
        pending_openings_count +
        pending_loans_count +
        pending_passwords_count
    )

    pending_temporary_passwords = session.get("pending_temporary_passwords", [])
    active_tab = request.args.get("tab")
    if not active_tab:
        if pending_signups_count > 0:
            active_tab = "signups"
        elif pending_closures_count > 0:
            active_tab = "closures"
        elif pending_documents_count > 0:
            active_tab = "docs"
        elif pending_openings_count > 0:
            active_tab = "openings"
        elif pending_loans_count > 0:
            active_tab = "loans"
        elif pending_passwords_count > 0:
            active_tab = "passwords"
        else:
            active_tab = "signups"

    conn.close()
    return render_template(
        "requests_center.html",
        signup_requests=signup_requests,
        pending_signups_count=pending_signups_count,
        closure_requests=closure_requests,
        pending_closures_count=pending_closures_count,
        document_requests=document_requests,
        pending_documents_count=pending_documents_count,
        opening_requests=opening_requests,
        pending_openings_count=pending_openings_count,
        loan_requests=loan_requests,
        pending_loans_count=pending_loans_count,
        password_requests=password_requests,
        pending_passwords_count=pending_passwords_count,
        total_pending_requests=total_pending_requests,
        pending_temporary_passwords=pending_temporary_passwords,
        active_tab=active_tab,
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


@accounts_bp.route("/accounts/close/<int:aid>", methods=["POST"])
@login_required
@owner_or_admin_required
def close_account(aid):
    """Directly close an account and liquidate balance."""
    reason = request.form.get("reason", "Administrative closure").strip()
    result = close_account_permanently(aid, reason=reason, reviewed_by=session["user"]["id"])
    if result["success"]:
        flash(f"{result['message']} Official Closure Certificate (PDF) is now available for download.", "success")
    else:
        flash(f"Error: {result['message']}", "danger")
    return redirect(url_for("accounts.accounts"))


@accounts_bp.route("/accounts/closure-requests/<int:rid>/approve", methods=["POST"])
@login_required
@owner_or_admin_required
def approve_closure_request(rid):
    """Approve a customer's account closure request."""
    conn = get_db()
    req = conn.execute("SELECT * FROM ACCOUNT_CLOSURE_REQUEST WHERE RequestID=?", (rid,)).fetchone()
    conn.close()
    if not req:
        flash("Closure request not found.", "danger")
        return redirect(url_for("accounts.accounts"))

    admin_note = request.form.get("admin_note", "Approved by branch administrator").strip()
    result = close_account_permanently(
        req["AccountID"],
        reason=f"{req['Reason']} ({admin_note})" if req["Reason"] else admin_note,
        reviewed_by=session["user"]["id"],
    )
    if result["success"]:
        flash(f"Closure request #{rid} approved. {result['message']} Closure Certificate is ready.", "success")
    else:
        flash(f"Error approving closure request: {result['message']}", "danger")
    return redirect(url_for("accounts.accounts"))


@accounts_bp.route("/accounts/closure-requests/<int:rid>/reject", methods=["POST"])
@login_required
@owner_or_admin_required
def reject_closure_request(rid):
    """Reject a customer's account closure request."""
    admin_note = request.form.get("admin_note", "Request rejected by administration").strip()
    conn = get_db()
    conn.execute("""
        UPDATE ACCOUNT_CLOSURE_REQUEST
        SET Status='Rejected', ReviewedBy=?, ReviewedAt=datetime('now'), AdminNote=?
        WHERE RequestID=?
    """, (session["user"]["id"], admin_note, rid))
    conn.commit()
    conn.close()
    flash(f"Closure request #{rid} has been rejected.", "info")
    return redirect(url_for("accounts.accounts"))


@accounts_bp.route("/accounts/opening-requests/<int:rid>/approve", methods=["POST"])
@login_required
@owner_or_admin_required
def approve_opening_request(rid):
    """Approve customer account opening request and generate account & card."""
    conn = get_db()
    req = conn.execute("SELECT * FROM ACCOUNT_OPENING_REQUEST WHERE RequestID=?", (rid,)).fetchone()
    if not req:
        conn.close()
        flash("Opening request not found.", "danger")
        return redirect(url_for("accounts.accounts"))

    if req["Status"] != "Pending":
        conn.close()
        flash("This request is already processed.", "warning")
        return redirect(url_for("accounts.accounts"))

    cid = req["CustomerID"]
    atype = req["AccountType"] or "Current"
    card_tier = req["CardTier"] or "standard"
    initial_deposit = float(req["InitialDeposit"] or 0.0)
    branch = req["BranchID"]

    try:
        acc_no = generate_moroccan_rib(branch_id=branch)
        while conn.execute("SELECT 1 FROM ACCOUNT WHERE AccountNumber=?", (acc_no,)).fetchone():
            acc_no = generate_moroccan_rib(branch_id=branch)

        card_no = generate_card_number(acc_no)

        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ACCOUNT (CustomerID, AccountNumber, CardNumber, CardTier, AccountType, Balance, BranchID)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (cid, acc_no, card_no, card_tier, atype, initial_deposit, branch))
        new_aid = cur.lastrowid

        if initial_deposit > 0:
            cur.execute("""
                INSERT INTO TRANSACTIONS (AccountID, TransactionType, Amount, Description, BalanceAfter)
                VALUES (?, 'Deposit', ?, 'Initial opening deposit', ?)
            """, (new_aid, initial_deposit, initial_deposit))

        admin_note = request.form.get("admin_note", "Approved and created").strip()
        cur.execute("""
            UPDATE ACCOUNT_OPENING_REQUEST
            SET Status='Approved', ReviewedBy=?, ReviewedAt=datetime('now'), AdminNote=?, CreatedAccountID=?
            WHERE RequestID=?
        """, (session["user"]["id"], admin_note, new_aid, rid))

        conn.commit()
        flash(f"Account opening request #{rid} approved! Account created with RIB: {format_moroccan_rib(acc_no)}", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error approving opening request: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for("accounts.accounts"))


@accounts_bp.route("/accounts/opening-requests/<int:rid>/reject", methods=["POST"])
@login_required
@owner_or_admin_required
def reject_opening_request(rid):
    """Reject customer account opening request."""
    admin_note = request.form.get("admin_note", "Rejected by bank administration").strip()
    conn = get_db()
    conn.execute("""
        UPDATE ACCOUNT_OPENING_REQUEST
        SET Status='Rejected', ReviewedBy=?, ReviewedAt=datetime('now'), AdminNote=?
        WHERE RequestID=?
    """, (session["user"]["id"], admin_note, rid))
    conn.commit()
    conn.close()
    flash(f"Account opening request #{rid} has been rejected.", "info")
    return redirect(url_for("accounts.accounts"))


