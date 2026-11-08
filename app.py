"""AkumaBank Flask application for Moroccan banking management."""

import os
from flask import Flask, render_template, redirect, url_for, session

from database import init_db
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


@app.route("/")
def index():
    """Redirect root to dashboard or login."""
    if "user" in session:
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
