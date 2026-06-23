import sqlite3
import functools
from flask import Flask, render_template, request, redirect, url_for, flash, get_flashed_messages, session
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = "dev-secret-key"

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
    user = {
        "name": session.get("user_name", "Demo User"),
        "email": "demo@trackify.com",
        "member_since": "June 1, 2026",
        "initials": "".join(w[0].upper() for w in session.get("user_name", "D U").split()[:2]),
    }
    stats = {
        "total_spent": "₹330.24",
        "transaction_count": 8,
        "top_category": "Bills",
    }
    transactions = [
        {"date": "Jun 20", "description": "Grocery run",   "category": "Food",          "amount": "₹18.75"},
        {"date": "Jun 18", "description": "Miscellaneous", "category": "Other",         "amount": "₹8.00"},
        {"date": "Jun 15", "description": "New shoes",     "category": "Shopping",      "amount": "₹89.99"},
        {"date": "Jun 12", "description": "Movie tickets", "category": "Entertainment", "amount": "₹25.00"},
        {"date": "Jun 10", "description": "Pharmacy",      "category": "Health",        "amount": "₹30.00"},
        {"date": "Jun 07", "description": "Electricity",   "category": "Bills",         "amount": "₹120.00"},
        {"date": "Jun 05", "description": "Bus pass",      "category": "Transport",     "amount": "₹45.00"},
        {"date": "Jun 01", "description": "Lunch at cafe", "category": "Food",          "amount": "₹12.50"},
    ]
    categories = [
        {"name": "Bills",         "amount": "₹120.00", "pct": 36},
        {"name": "Shopping",      "amount": "₹89.99",  "pct": 27},
        {"name": "Transport",     "amount": "₹45.00",  "pct": 14},
        {"name": "Food",          "amount": "₹31.25",  "pct": 9},
        {"name": "Health",        "amount": "₹30.00",  "pct": 9},
        {"name": "Entertainment", "amount": "₹25.00",  "pct": 8},
        {"name": "Other",         "amount": "₹8.00",   "pct": 2},
    ]
    return render_template("profile.html", user=user, stats=stats,
                           transactions=transactions, categories=categories)


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
    app.run(debug=True, port=5001)
