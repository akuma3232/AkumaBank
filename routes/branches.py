"""
routes/branches.py - Branch management CRUD
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import get_db
from functools import wraps

branches_bp = Blueprint("branches", __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@branches_bp.route("/branches")
@login_required
def branches():
    """List all branches with account counts."""
    search = request.args.get("q", "").strip()
    conn   = get_db()

    if search:
        rows = conn.execute("""
            SELECT b.*, COUNT(a.AccountID) AS account_count,
                   COALESCE(SUM(a.Balance), 0) AS total_balance
            FROM BRANCH b
            LEFT JOIN ACCOUNT a ON b.BranchID = a.BranchID
            WHERE b.BranchName LIKE ? OR b.City LIKE ? OR b.BranchCode LIKE ?
            GROUP BY b.BranchID
            ORDER BY b.BranchName
        """, (f"%{search}%", f"%{search}%", f"%{search}%")).fetchall()
    else:
        rows = conn.execute("""
            SELECT b.*, COUNT(a.AccountID) AS account_count,
                   COALESCE(SUM(a.Balance), 0) AS total_balance
            FROM BRANCH b
            LEFT JOIN ACCOUNT a ON b.BranchID = a.BranchID
            GROUP BY b.BranchID
            ORDER BY b.BranchName
        """).fetchall()

    conn.close()
    return render_template("branches.html", branches=rows, search=search)


@branches_bp.route("/branches/add", methods=["POST"])
@login_required
def add_branch():
    data = request.form
    name    = data.get("branch_name","").strip()
    branch_code = data.get("branch_code","").strip()
    address = data.get("address","").strip()
    city    = data.get("city","").strip()
    phone   = data.get("phone","").strip()

    if not all([name, branch_code, address, city, phone]):
        flash("All branch fields are required.", "danger")
        return redirect(url_for("branches.branches"))

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO BRANCH (BranchName,BranchCode,Address,City,Phone) VALUES (?,?,?,?,?)",
            (name, branch_code, address, city, phone),
        )
        conn.commit()
        flash(f"Branch '{name}' added successfully.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("branches.branches"))


@branches_bp.route("/branches/edit/<int:bid>", methods=["POST"])
@login_required
def edit_branch(bid):
    data = request.form
    conn = get_db()
    try:
        conn.execute("""
            UPDATE BRANCH SET BranchName=?, BranchCode=?, Address=?, City=?, Phone=?
            WHERE BranchID=?
        """, (data["branch_name"], data["branch_code"], data["address"],
              data["city"], data["phone"], bid))
        conn.commit()
        flash("Branch updated successfully.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("branches.branches"))


@branches_bp.route("/branches/delete/<int:bid>", methods=["POST"])
@login_required
def delete_branch(bid):
    conn = get_db()
    try:
        conn.execute("DELETE FROM BRANCH WHERE BranchID=?", (bid,))
        conn.commit()
        flash("Branch deleted.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("branches.branches"))


@branches_bp.route("/branches/get/<int:bid>")
@login_required
def get_branch(bid):
    conn = get_db()
    row = conn.execute("SELECT * FROM BRANCH WHERE BranchID=?", (bid,)).fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({}), 404
