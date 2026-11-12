"""
routes/documents.py - Official PDF Document Endpoints & Customer Document Portal for AkumaBank
Handles:
1. Direct document viewing and downloading (inline preview or attachment).
2. Customer "My Documents" section: request official documents, view status, cancel pending requests.
3. Bank staff workflow: review document requests, generate draft PDFs, sign/upload certified PDFs, and approve.
"""

import os
import uuid
from functools import wraps
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from database import get_db, SIGNED_DOCS_DIR
from card_tiers import get_card_tier
from pdf_generator import (
    generate_opening_certificate_pdf,
    generate_closure_certificate_pdf,
    generate_card_subscription_pdf,
    generate_rib_attestation_pdf,
    generate_statement_pdf,
    generate_solvency_certificate_pdf,
)

documents_bp = Blueprint("documents", __name__)

DOCUMENT_TYPES = {
    "RIB_ATTESTATION": {
        "title": "Official 24-Digit RIB Attestation",
        "description": "Standard Moroccan RIB slip with BAM codes and IBAN for salaries & direct debits.",
        "icon": "bi-bank",
    },
    "WELCOME_PACK": {
        "title": "Account Opening Certificate & Welcome Kit",
        "description": "Official confirmation of account opening with card visual template and subscription limits.",
        "icon": "bi-file-earmark-text",
    },
    "CARD_CERTIFICATE": {
        "title": "Card Subscription Specification Sheet",
        "description": "Detailed card documentation with EMV parameters, contactless limits, and travel insurance.",
        "icon": "bi-credit-card",
    },
    "ACCOUNT_STATEMENT": {
        "title": "Official Account Statement & Activity Logs",
        "description": "Certified financial summary and detailed transaction activity stream.",
        "icon": "bi-receipt",
    },
    "SOLVENCY_CERTIFICATE": {
        "title": "Attestation de Solvabilité (Solvency Certificate)",
        "description": "Official certificate of financial standing and account balance for visa & administrative bodies.",
        "icon": "bi-shield-check",
    },
    "CLOSURE_CERTIFICATE": {
        "title": "Account Closure Certificate & Discharge (Quittus)",
        "description": "Official certificate of permanent account termination and zero-balance clearance.",
        "icon": "bi-file-earmark-x",
    },
}


def document_access_required(f):
    """
    Ensure the user is signed in and authorized:
    - Staff (Owner, Admin) can access direct document generation routes.
    - Customer is restricted: direct PDF downloads are not permitted;
      they must formally request documents through the Document Request portal.
    """
    @wraps(f)
    def decorated(aid, *args, **kwargs):
        if "user" not in session:
            flash("Please sign in to access documents.", "warning")
            return redirect(url_for("auth.login"))

        user = session["user"]
        role = user.get("role")

        # Direct document generation is strictly restricted to bank staff officers
        if role == "Customer":
            flash("Direct document downloads are restricted to bank officers. Please submit an official document request via My Documents.", "warning")
            return redirect(url_for("documents.customer_documents"))

        conn = get_db()
        account = conn.execute("SELECT * FROM ACCOUNT WHERE AccountID=?", (aid,)).fetchone()
        if not account:
            conn.close()
            abort(404, description="Account not found")

        conn.close()
        return f(aid, *args, **kwargs)

    return decorated


def customer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        if session["user"].get("role") != "Customer":
            flash("Only registered customers can access the customer document portal.", "warning")
            return redirect(url_for("dashboard.dashboard"))
        return f(*args, **kwargs)

    return decorated


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        if session["user"].get("role") not in ("Owner", "Admin"):
            flash("Staff privileges required.", "danger")
            return redirect(url_for("customer_portal.home"))
        return f(*args, **kwargs)

    return decorated


def _fetch_account_context(aid: int):
    """Fetch all related data for an account needed by PDF generators."""
    conn = get_db()
    account = conn.execute("SELECT * FROM ACCOUNT WHERE AccountID=?", (aid,)).fetchone()
    if not account:
        conn.close()
        return None, None, None, None

    customer = conn.execute("SELECT * FROM CUSTOMER WHERE CustomerID=?", (account["CustomerID"],)).fetchone()
    branch = None
    if account["BranchID"]:
        branch = conn.execute("SELECT * FROM BRANCH WHERE BranchID=?", (account["BranchID"],)).fetchone()

    if not branch:
        branch = {
            "BranchName": "Casablanca Central Agency",
            "BranchCode": "810",
            "Address": "Boulevard Mohammed V",
            "City": "Casablanca",
        }

    tier = get_card_tier(account["CardTier"] if "CardTier" in account.keys() else "standard")
    conn.close()
    return dict(account), dict(customer) if customer else {}, dict(branch), tier


def _closed_only(doc_type: str, account: dict) -> bool:
    """Closure documents are issued only after the account has actually been closed."""
    return doc_type == "CLOSURE_CERTIFICATE" and account.get("Status") != "Closed"


def _generate_pdf_for_doc_type(doc_type: str, account: dict, customer: dict, branch: dict, tier: dict, purpose: str = None):
    """Helper to route and generate the right PDF document bytes."""
    conn = get_db()
    if doc_type == "RIB_ATTESTATION":
        return generate_rib_attestation_pdf(account, customer, branch)
    elif doc_type == "WELCOME_PACK":
        return generate_opening_certificate_pdf(account, customer, branch, tier)
    elif doc_type == "CARD_CERTIFICATE":
        return generate_card_subscription_pdf(account, customer, tier)
    elif doc_type == "ACCOUNT_STATEMENT":
        txs = conn.execute(
            "SELECT * FROM TRANSACTIONS WHERE AccountID=? ORDER BY TransactionDate DESC LIMIT 60",
            (account["AccountID"],),
        ).fetchall()
        conn.close()
        return generate_statement_pdf(account, customer, branch, [dict(t) for t in txs])
    elif doc_type == "SOLVENCY_CERTIFICATE":
        conn.close()
        return generate_solvency_certificate_pdf(account, customer, branch, purpose=purpose)
    elif doc_type == "CLOSURE_CERTIFICATE":
        closure_req = conn.execute(
            "SELECT Reason FROM ACCOUNT_CLOSURE_REQUEST WHERE AccountID=? ORDER BY RequestID DESC LIMIT 1",
            (account["AccountID"],),
        ).fetchone()
        conn.close()
        reason = closure_req["Reason"] if closure_req else (purpose or "Customer Request / Mutual Discharge")
        return generate_closure_certificate_pdf(account, customer, branch, reason=reason)
    else:
        conn.close()
        return generate_rib_attestation_pdf(account, customer, branch)


# ─────────────────────────────────────────────────────────────────────────────
# 1. DIRECT DOCUMENT ACCESS (OPENING, CLOSURE, CARD, RIB, STATEMENT)
# ─────────────────────────────────────────────────────────────────────────────

@documents_bp.route("/documents/account/<int:aid>/opening-certificate")
@document_access_required
def download_opening_certificate(aid):
    account, customer, branch, tier = _fetch_account_context(aid)
    if not account:
        abort(404)
    pdf_buffer = generate_opening_certificate_pdf(account, customer, branch, tier)
    filename = f"AkumaBank_Welcome_Pack_{account.get('AccountNumber', aid)}.pdf"
    as_attachment = request.args.get("download") == "1"
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=as_attachment, download_name=filename)


@documents_bp.route("/documents/account/<int:aid>/closure-certificate")
@document_access_required
def download_closure_certificate(aid):
    account, customer, branch, _ = _fetch_account_context(aid)
    if not account:
        abort(404)
    if account.get("Status") != "Closed":
        flash("The closure certificate (Quittus) is issued only once the account has been closed.", "warning")
        fallback = (
            url_for("documents.customer_documents")
            if session.get("user", {}).get("role") == "Customer"
            else url_for("accounts.accounts")
        )
        return redirect(request.referrer or fallback)
    conn = get_db()
    closure_req = conn.execute(
        "SELECT Reason FROM ACCOUNT_CLOSURE_REQUEST WHERE AccountID=? ORDER BY RequestID DESC LIMIT 1",
        (aid,),
    ).fetchone()
    conn.close()
    reason = closure_req["Reason"] if closure_req else "Customer Request / Mutual Discharge"
    pdf_buffer = generate_closure_certificate_pdf(account, customer, branch, reason=reason)
    filename = f"AkumaBank_Closure_Certificate_{account.get('AccountNumber', aid)}.pdf"
    as_attachment = request.args.get("download") == "1"
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=as_attachment, download_name=filename)


@documents_bp.route("/documents/account/<int:aid>/card-certificate")
@document_access_required
def download_card_certificate(aid):
    account, customer, _, tier = _fetch_account_context(aid)
    if not account:
        abort(404)
    pdf_buffer = generate_card_subscription_pdf(account, customer, tier)
    filename = f"AkumaBank_Card_Subscription_{tier.get('id', 'card')}_{account.get('AccountNumber', aid)}.pdf"
    as_attachment = request.args.get("download") == "1"
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=as_attachment, download_name=filename)


@documents_bp.route("/documents/account/<int:aid>/rib-attestation")
@document_access_required
def download_rib_attestation(aid):
    account, customer, branch, _ = _fetch_account_context(aid)
    if not account:
        abort(404)
    pdf_buffer = generate_rib_attestation_pdf(account, customer, branch)
    filename = f"AkumaBank_Attestation_RIB_{account.get('AccountNumber', aid)}.pdf"
    as_attachment = request.args.get("download") == "1"
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=as_attachment, download_name=filename)


@documents_bp.route("/documents/account/<int:aid>/statement")
@document_access_required
def download_statement(aid):
    account, customer, branch, _ = _fetch_account_context(aid)
    if not account:
        abort(404)
    conn = get_db()
    transactions = conn.execute(
        "SELECT * FROM TRANSACTIONS WHERE AccountID=? ORDER BY TransactionDate DESC, TransactionID DESC LIMIT 100",
        (aid,),
    ).fetchall()
    conn.close()
    pdf_buffer = generate_statement_pdf(account, customer, branch, [dict(t) for t in transactions])
    filename = f"AkumaBank_Statement_{account.get('AccountNumber', aid)}.pdf"
    as_attachment = request.args.get("download") == "1"
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=as_attachment, download_name=filename)


@documents_bp.route("/documents/account/<int:aid>/solvency-certificate")
@document_access_required
def download_solvency_certificate(aid):
    account, customer, branch, _ = _fetch_account_context(aid)
    if not account:
        abort(404)
    purpose = request.args.get("purpose", "Administrative and Solvency Justification")
    pdf_buffer = generate_solvency_certificate_pdf(account, customer, branch, purpose=purpose)
    filename = f"AkumaBank_Solvency_Certificate_{account.get('AccountNumber', aid)}.pdf"
    as_attachment = request.args.get("download") == "1"
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=as_attachment, download_name=filename)


# ─────────────────────────────────────────────────────────────────────────────
# 2. CUSTOMER "MY DOCUMENTS" PORTAL
# ─────────────────────────────────────────────────────────────────────────────

@documents_bp.route("/my-documents")
@customer_required
def customer_documents():
    """Customer view: table of document requests, status, cancel button, and download link."""
    email = session.get("user", {}).get("email")
    conn = get_db()
    customer = conn.execute(
        "SELECT CustomerID, Name, Email FROM CUSTOMER WHERE lower(Email)=lower(?)",
        (email,),
    ).fetchone()

    if not customer:
        conn.close()
        flash("Customer profile not found.", "danger")
        return redirect(url_for("customer_portal.home"))

    cid = customer["CustomerID"]

    # Customer accounts for the request modal
    accounts = conn.execute(
        "SELECT AccountID, AccountNumber, AccountType, CardTier, Status FROM ACCOUNT WHERE CustomerID=? ORDER BY AccountID",
        (cid,),
    ).fetchall()

    # Customer document requests table
    requests = conn.execute("""
        SELECT r.*, a.AccountNumber, a.CardTier, u.Username AS ProcessedByUsername
        FROM DOCUMENT_REQUEST r
        LEFT JOIN ACCOUNT a ON a.AccountID = r.AccountID
        LEFT JOIN USERS u ON u.UserID = r.ProcessedBy
        WHERE r.CustomerID=?
        ORDER BY r.RequestedAt DESC, r.RequestID DESC
    """, (cid,)).fetchall()

    conn.close()

    # The closure certificate (Quittus) exists only for accounts already closed.
    has_closed_account = any(a["Status"] == "Closed" for a in accounts)
    available_document_types = {
        key: info
        for key, info in DOCUMENT_TYPES.items()
        if key != "CLOSURE_CERTIFICATE" or has_closed_account
    }

    return render_template(
        "customer_documents.html",
        customer=customer,
        accounts=accounts,
        requests=requests,
        document_types=available_document_types,
    )


@documents_bp.post("/my-documents/request")
@customer_required
def submit_document_request():
    """Customer submits an official document request."""
    email = session.get("user", {}).get("email")
    doc_type = (request.form.get("document_type") or request.form.get("doc_type") or "").strip()
    account_id = request.form.get("account_id", "").strip()
    purpose = request.form.get("purpose", "").strip()

    if doc_type not in DOCUMENT_TYPES:
        flash("Please select a valid document type.", "danger")
        return redirect(url_for("documents.customer_documents"))

    conn = get_db()
    customer = conn.execute("SELECT CustomerID FROM CUSTOMER WHERE lower(Email)=lower(?)", (email,)).fetchone()
    if not customer:
        conn.close()
        flash("Customer profile not found.", "danger")
        return redirect(url_for("customer_portal.home"))

    cid = customer["CustomerID"]
    aid = int(account_id) if account_id.isdigit() else None

    # Verify account belongs to customer if provided
    if aid:
        acct = conn.execute("SELECT Status FROM ACCOUNT WHERE AccountID=? AND CustomerID=?", (aid, cid)).fetchone()
        if not acct:
            conn.close()
            flash("Invalid account selected.", "danger")
            return redirect(url_for("documents.customer_documents"))

    # A closure certificate can only be requested for an account that is closed.
    if doc_type == "CLOSURE_CERTIFICATE":
        closed = (
            conn.execute(
                "SELECT 1 FROM ACCOUNT WHERE AccountID=? AND CustomerID=? AND Status='Closed'",
                (aid, cid),
            ).fetchone()
            if aid
            else None
        )
        if not closed:
            conn.close()
            flash(
                "A closure certificate (Quittus) can only be requested for an account that is already closed.",
                "danger",
            )
            return redirect(url_for("documents.customer_documents"))

    doc_info = DOCUMENT_TYPES[doc_type]
    conn.execute("""
        INSERT INTO DOCUMENT_REQUEST (CustomerID, AccountID, DocumentType, DocumentTitle, Purpose, Status)
        VALUES (?, ?, ?, ?, ?, 'Pending')
    """, (cid, aid, doc_type, doc_info["title"], purpose or "Administrative requirement"))
    conn.commit()
    conn.close()

    flash(f"Your request for '{doc_info['title']}' has been submitted. Bank officers will prepare, sign, and certify your document.", "success")
    return redirect(url_for("documents.customer_documents"))


@documents_bp.post("/my-documents/cancel/<int:rid>")
@customer_required
def cancel_document_request(rid):
    """Customer cancels a pending document request."""
    email = session.get("user", {}).get("email")
    conn = get_db()
    customer = conn.execute("SELECT CustomerID FROM CUSTOMER WHERE lower(Email)=lower(?)", (email,)).fetchone()
    if not customer:
        conn.close()
        flash("Customer profile not found.", "danger")
        return redirect(url_for("customer_portal.home"))

    # Only cancel if still Pending
    cur = conn.cursor()
    cur.execute("""
        UPDATE DOCUMENT_REQUEST
        SET Status='Cancelled'
        WHERE RequestID=? AND CustomerID=? AND Status='Pending'
    """, (rid, customer["CustomerID"]))
    conn.commit()
    changed = cur.rowcount
    conn.close()

    if changed:
        flash("Document request cancelled successfully.", "info")
    else:
        flash("Could not cancel that request (it may have already been approved or processed).", "warning")

    return redirect(url_for("documents.customer_documents"))


@documents_bp.route("/my-documents/download/<int:rid>")
def download_approved_document(rid):
    """
    Download or view an approved/signed document.
    Accessible by the requesting customer or any staff member.
    """
    if "user" not in session:
        return redirect(url_for("auth.login"))

    conn = get_db()
    req = conn.execute("SELECT * FROM DOCUMENT_REQUEST WHERE RequestID=?", (rid,)).fetchone()
    if not req:
        conn.close()
        abort(404, description="Document request not found")

    user = session["user"]
    if user.get("role") == "Customer":
        cust = conn.execute("SELECT CustomerID FROM CUSTOMER WHERE lower(Email)=lower(?)", (user.get("email"),)).fetchone()
        if not cust or req["CustomerID"] != cust["CustomerID"]:
            conn.close()
            abort(403, description="Unauthorized to access this document")

    if req["Status"] != "Approved":
        conn.close()
        flash("This document has not been approved or signed yet.", "warning")
        return redirect(url_for("documents.customer_documents"))

    # If staff uploaded a signed physical/custom PDF file
    signed_filename = req["SignedPdfFile"]
    if signed_filename:
        file_path = os.path.join(SIGNED_DOCS_DIR, signed_filename)
        if os.path.exists(file_path):
            conn.close()
            as_attachment = request.args.get("download") == "1"
            return send_file(file_path, mimetype="application/pdf", as_attachment=as_attachment, download_name=signed_filename)

    # Otherwise auto-generate the certified official PDF
    conn.close()
    aid = req["AccountID"]
    if not aid:
        abort(404, description="No account linked to generate document")

    account, customer, branch, tier = _fetch_account_context(aid)
    pdf_buffer = _generate_pdf_for_doc_type(req["DocumentType"], account, customer, branch, tier, purpose=req["Purpose"])
    doc_slug = req["DocumentType"].lower()
    filename = f"AkumaBank_{doc_slug}_{account.get('AccountNumber', aid)}_signed.pdf"
    as_attachment = request.args.get("download") == "1"
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=as_attachment, download_name=filename)


# ─────────────────────────────────────────────────────────────────────────────
# 3. BANK STAFF WORKFLOW: PREVIEW DRAFT, SIGN / UPLOAD, APPROVE & REJECT
# ─────────────────────────────────────────────────────────────────────────────

@documents_bp.route("/documents/requests/<int:rid>/preview")
@staff_required
def staff_preview_request_pdf(rid):
    """Staff preview: instantly compiles the draft PDF for the requested document."""
    conn = get_db()
    req = conn.execute("SELECT * FROM DOCUMENT_REQUEST WHERE RequestID=?", (rid,)).fetchone()
    conn.close()
    if not req or not req["AccountID"]:
        abort(404)

    account, customer, branch, tier = _fetch_account_context(req["AccountID"])
    if _closed_only(req["DocumentType"], account):
        flash("A closure certificate can only be issued for a closed account.", "warning")
        return redirect(request.referrer or url_for("accounts.requests_center", tab="documents"))
    pdf_buffer = _generate_pdf_for_doc_type(req["DocumentType"], account, customer, branch, tier, purpose=req["Purpose"])
    filename = f"Draft_{req['DocumentType']}_{account.get('AccountNumber', '')}.pdf"
    as_attachment = request.args.get("download") == "1"
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=as_attachment, download_name=filename)


@documents_bp.post("/documents/requests/<int:rid>/approve")
@staff_required
def staff_approve_request(rid):
    """
    Staff approves document request:
    Can either upload a signed PDF file or apply instant digital certification.
    """
    user_id = session["user"]["id"]
    admin_note = request.form.get("admin_note", "Certified and signed by bank operations").strip()
    signed_upload = request.files.get("signed_pdf")

    signed_filename = None
    if signed_upload and signed_upload.filename:
        os.makedirs(SIGNED_DOCS_DIR, exist_ok=True)
        ext = os.path.splitext(signed_upload.filename)[1].lower()
        if ext != ".pdf":
            flash("Please upload a valid PDF document.", "danger")
            return redirect(request.referrer or url_for("accounts.accounts"))

        signed_filename = f"doc_{rid}_{uuid.uuid4().hex[:10]}.pdf"
        dest_path = os.path.join(SIGNED_DOCS_DIR, signed_filename)
        signed_upload.save(dest_path)

    conn = get_db()
    conn.execute("""
        UPDATE DOCUMENT_REQUEST
        SET Status='Approved', ProcessedAt=datetime('now'), ProcessedBy=?, AdminNote=?, SignedPdfFile=?
        WHERE RequestID=?
    """, (user_id, admin_note, signed_filename, rid))
    conn.commit()
    conn.close()

    flash(f"Document request #{rid} approved and marked ready for customer download.", "success")
    return redirect(request.referrer or url_for("accounts.accounts"))


@documents_bp.post("/documents/requests/<int:rid>/reject")
@staff_required
def staff_reject_request(rid):
    """Staff rejects document request with a justification note."""
    user_id = session["user"]["id"]
    admin_note = request.form.get("admin_note", "Rejected by branch administration").strip()

    conn = get_db()
    conn.execute("""
        UPDATE DOCUMENT_REQUEST
        SET Status='Rejected', ProcessedAt=datetime('now'), ProcessedBy=?, AdminNote=?
        WHERE RequestID=?
    """, (user_id, admin_note, rid))
    conn.commit()
    conn.close()

    flash(f"Document request #{rid} has been rejected.", "info")
    return redirect(request.referrer or url_for("accounts.accounts"))
