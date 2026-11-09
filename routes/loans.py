"""
routes/loans.py - Loan application, approval, and management
"""

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
               ROUND(l.Amount * l.InterestRate / 100, 2) AS annual_interest,
               ROUND(l.Amount * (1 + l.InterestRate / 100), 2) AS total_repayable
        FROM LOAN l
        JOIN CUSTOMER c ON l.CustomerID = c.CustomerID
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
    conn.close()

    return render_template(
        "loans.html",
        loans=rows,
        stats=stats,
        customers=customers,
        search=search,
        status_filter=status,
    )


@loans_bp.route("/loans/apply", methods=["POST"])
@login_required
def apply_loan():
    data = request.form
    cid      = data.get("customer_id")
    ltype    = data.get("loan_type")
    amount   = float(data.get("amount", 0))
    rate     = float(data.get("interest_rate", 0))
    start    = data.get("start_date")

    if not all([cid, ltype, amount, rate, start]):
        flash("All loan fields are required.", "danger")
        return redirect(url_for("loans.loans"))

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO LOAN (CustomerID,LoanType,Amount,InterestRate,StartDate) VALUES (?,?,?,?,?)",
            (cid, ltype, amount, rate, start),
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
        if new_status == "Approved":
            try:
                final_rate = float(request.form.get("interest_rate", ""))
            except ValueError:
                final_rate = 0
            if not 0.1 <= final_rate <= 30:
                flash("Set a final interest rate between 0.1% and 30% before approval.", "danger")
                return redirect(url_for("loans.loans"))
            conn.execute(
                "UPDATE LOAN SET Status=?, InterestRate=? WHERE LoanID=?",
                (new_status, final_rate, lid),
            )
        else:
            conn.execute("UPDATE LOAN SET Status=? WHERE LoanID=?", (new_status, lid))
        conn.commit()
        flash(f"Loan status updated to {new_status}.", "success")
    except Exception as e:
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
