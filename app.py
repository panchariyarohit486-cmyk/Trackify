import os
import sqlite3
import functools
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, get_flashed_messages, session
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db
from database.queries import get_user_by_id, get_summary_stats, get_recent_transactions, get_category_breakdown

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Auth helper                                                         #
# ------------------------------------------------------------------ #

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            flash("Please sign in to continue.")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get('user_id'):
        return redirect(url_for('profile'))
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not name or not email or not password:
        return render_template("register.html", error="All fields are required.", name=name, email=email)

    if len(password) < 8:
        return render_template("register.html", error="Password must be at least 8 characters.", name=name, email=email)

    password_hash = generate_password_hash(password)

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return render_template("register.html", error="An account with that email already exists.", name=name, email=email)
    finally:
        conn.close()

    flash("Account created — please sign in.")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get('user_id'):
        return redirect(url_for('profile'))
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email or not password:
        return render_template("login.html", error="Invalid email or password.", email=email)

    conn = get_db()
    row = conn.execute(
        "SELECT id, name, password_hash FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()

    if row is None or not check_password_hash(row["password_hash"], password):
        return render_template("login.html", error="Invalid email or password.", email=email)

    session["user_id"] = row["id"]
    session["user_name"] = row["name"]
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
@login_required
def profile():
    uid = session["user_id"]
    user = get_user_by_id(uid)

    today = date.today()
    today_str = today.isoformat()

    # Preset: first day of current month
    preset_this_month_from = today.replace(day=1).isoformat()

    # Preset: first day of 3 months ago
    m3, y3 = today.month - 3, today.year
    if m3 <= 0:
        m3, y3 = m3 + 12, y3 - 1
    preset_3months_from = date(y3, m3, 1).isoformat()

    # Preset: first day of 6 months ago
    m6, y6 = today.month - 6, today.year
    if m6 <= 0:
        m6, y6 = m6 + 12, y6 - 1
    preset_6months_from = date(y6, m6, 1).isoformat()

    # Parse and validate query params
    raw_from = request.args.get('date_from', '').strip()
    raw_to   = request.args.get('date_to',   '').strip()
    date_from = date_to = None
    if raw_from:
        try:
            datetime.strptime(raw_from, '%Y-%m-%d')
            date_from = raw_from
        except ValueError:
            pass
    if raw_to:
        try:
            datetime.strptime(raw_to, '%Y-%m-%d')
            date_to = raw_to
        except ValueError:
            pass

    if bool(date_from) != bool(date_to):
        flash("Please provide both a start and an end date.")
        date_from = date_to = None
    elif date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.")
        date_from = date_to = None

    # Identify which preset is active for button highlighting
    if not date_from and not date_to:
        active_preset = 'all_time'
    elif date_from == preset_this_month_from and date_to == today_str:
        active_preset = 'this_month'
    elif date_from == preset_3months_from and date_to == today_str:
        active_preset = '3_months'
    elif date_from == preset_6months_from and date_to == today_str:
        active_preset = '6_months'
    else:
        active_preset = 'custom'

    stats        = get_summary_stats(uid, date_from=date_from, date_to=date_to)
    transactions = get_recent_transactions(uid, date_from=date_from, date_to=date_to)
    categories   = get_category_breakdown(uid, date_from=date_from, date_to=date_to)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        date_from=date_from,
        date_to=date_to,
        active_preset=active_preset,
        preset_this_month_from=preset_this_month_from,
        preset_this_month_to=today_str,
        preset_3months_from=preset_3months_from,
        preset_3months_to=today_str,
        preset_6months_from=preset_6months_from,
        preset_6months_to=today_str,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


@app.route("/terms-and-conditions")
def terms():
    return render_template("terms.html")


@app.route("/privacy-policy")
def privacy():
    return render_template("privacy.html")


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=5001)
