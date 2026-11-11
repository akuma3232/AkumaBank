"""AkumaBank Flask application for Moroccan banking management."""

import os
from flask import Flask, flash, render_template, redirect, request, session, url_for

from database import get_db, init_db
from card_tiers import CARD_TIERS, get_card_tier, list_card_tiers
from morocco_banking import (
    format_moroccan_rib,
    rib_to_iban,
    format_iban,
    format_card_number,
    generate_cvv,
    generate_card_number,
)
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.customers import customers_bp
from routes.accounts import accounts_bp
from routes.transactions import transactions_bp
from routes.loans import loans_bp
from routes.branches import branches_bp
from routes.reports import reports_bp
from routes.database_panel import database_bp
from routes.users import users_bp
from routes.profiles import profiles_bp
from routes.customer_portal import customer_portal_bp
from routes.documents import documents_bp

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET") or os.urandom(32)
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024

# Create the schema for a new database without inserting demo banking records.
init_db(seed_demo_data=False)
# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(customers_bp)
app.register_blueprint(accounts_bp)
app.register_blueprint(transactions_bp)
app.register_blueprint(loans_bp)
app.register_blueprint(branches_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(database_bp)
app.register_blueprint(users_bp)
app.register_blueprint(profiles_bp)
app.register_blueprint(customer_portal_bp)
app.register_blueprint(documents_bp)

# ── Jinja Template Filters for Moroccan Banking & Cards ──────────────────────
@app.template_filter("format_rib")
def filter_format_rib(rib):
    if not rib:
        return ""
    return format_moroccan_rib(rib)

@app.template_filter("rib_to_iban")
def filter_rib_to_iban(rib):
    if not rib:
        return ""
    return rib_to_iban(rib)

@app.template_filter("format_iban")
def filter_format_iban(iban):
    if not iban:
        return ""
    return format_iban(iban)

@app.template_filter("format_card")
def filter_format_card(card, masked=False):
    if not card:
        return ""
    return format_card_number(card, masked=masked)

@app.template_filter("card_cvv")
def filter_card_cvv(card_or_account):
    if not card_or_account:
        return "000"
    return generate_cvv(card_or_account)

@app.template_filter("card_number")
def filter_card_number(account):
    if not account:
        return ""
    try:
        cn = account.get("CardNumber") if hasattr(account, "get") else account["CardNumber"]
        if cn:
            return cn
    except Exception:
        pass
    try:
        acc_no = account.get("AccountNumber") if hasattr(account, "get") else account["AccountNumber"]
        if acc_no:
            return generate_card_number(acc_no)
    except Exception:
        pass
    return generate_card_number(str(account))

@app.template_filter("card_tier_info")
def filter_card_tier_info(tier_id):
    return get_card_tier(tier_id)

@app.context_processor
def inject_card_tiers():
    return {
        "CARD_TIERS": CARD_TIERS,
        "list_card_tiers": list_card_tiers,
        "get_card_tier": get_card_tier,
    }


@app.context_processor
def inject_operations_requests_counts():
    user = session.get("user")
    if not user or user.get("role") == "Customer":
        return {}
    try:
        conn = get_db()
        signups = conn.execute("SELECT COUNT(*) FROM USERS WHERE Role='Customer' AND ApprovalStatus='Pending'").fetchone()[0]
        closures = conn.execute("SELECT COUNT(*) FROM ACCOUNT_CLOSURE_REQUEST WHERE Status='Pending'").fetchone()[0]
        docs = conn.execute("SELECT COUNT(*) FROM DOCUMENT_REQUEST WHERE Status='Pending'").fetchone()[0]
        openings = conn.execute("SELECT COUNT(*) FROM ACCOUNT_OPENING_REQUEST WHERE Status='Pending'").fetchone()[0]
        loans = conn.execute("SELECT COUNT(*) FROM LOAN WHERE Status='Pending'").fetchone()[0]
        passwords = conn.execute("SELECT COUNT(*) FROM PASSWORD_RESET_REQUEST WHERE Status='Pending'").fetchone()[0]
        conn.close()
        total = signups + closures + docs + openings + loans + passwords
        return {
            "total_pending_requests": total,
            "pending_signups_count": signups,
            "pending_closures_count": closures,
            "pending_documents_count": docs,
            "pending_openings_count": openings,
            "pending_loans_count": loans,
            "pending_passwords_count": passwords,
        }
    except Exception:
        return {}


@app.before_request
def restrict_customer_routes():
    """Keep customer logins out of staff banking operations."""
    user = session.get("user")
    endpoint = request.endpoint or ""
    if user:
        conn = get_db()
        account = conn.execute(
            "SELECT MustChangePassword FROM USERS WHERE UserID=?",
            (user.get("id"),),
        ).fetchone()
        conn.close()
        if not account:
            session.clear()
            return redirect(url_for("auth.login"))
        if account["MustChangePassword"] and not user.get("must_change_password"):
            session.clear()
            flash("Your password was reset. Sign in with the temporary password.", "warning")
            return redirect(url_for("auth.login"))
    if user and user.get("must_change_password") and endpoint not in (
        "auth.change_password", "auth.logout", "static"
    ):
        return redirect(url_for("auth.change_password"))
    if user and user.get("role") == "Customer" and not endpoint.startswith(
        ("customer_portal.", "profiles.", "auth.", "static", "documents.")
    ):
        return redirect(url_for("customer_portal.home"))
    return None


@app.route("/")
def index():
    """Redirect root to dashboard or login."""
    if "user" in session:
        if session["user"]["role"] == "Customer":
            return redirect(url_for("customer_portal.home"))
        return redirect(url_for("dashboard.dashboard"))
    return redirect(url_for("auth.login"))


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Page not found"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Internal server error"), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
