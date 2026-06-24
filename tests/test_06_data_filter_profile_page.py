"""
Tests for Step 6: Date Filter on the Profile Page (GET /profile).

The DB used by the app is the real file-based SQLite DB at database/trackify.db.
Each test that needs its own data inserts rows directly and removes them in a
teardown so the seed data (demo user id=1) is left intact for other test files.
"""

import sqlite3
import pytest
from datetime import date

from app import app as flask_app
from database.db import DB_PATH, init_db, seed_db


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def ensure_db():
    """Make sure tables and seed data exist before every test."""
    with flask_app.app_context():
        init_db()
        seed_db()


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test"
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(client):
    """Test client with the demo user already logged in via session."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_name"] = "Demo User"
    return client


# ------------------------------------------------------------------ #
# DB helpers                                                          #
# ------------------------------------------------------------------ #

def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_expense(user_id, amount, category, expense_date, description):
    """Insert one expense and return its id."""
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, expense_date, description),
    )
    expense_id = cur.lastrowid
    conn.commit()
    conn.close()
    return expense_id


def _delete_expenses(expense_ids):
    """Remove specific expense rows by id."""
    conn = _get_conn()
    conn.executemany(
        "DELETE FROM expenses WHERE id = ?",
        [(eid,) for eid in expense_ids],
    )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ #
# 1. Auth guard                                                       #
# ------------------------------------------------------------------ #

def test_profile_requires_login(client):
    """Unauthenticated GET /profile must redirect to /login with 302."""
    resp = client.get("/profile")
    assert resp.status_code == 302, "Expected 302 redirect for unauthenticated user"
    assert "/login" in resp.headers["Location"], "Redirect should point to /login"


# ------------------------------------------------------------------ #
# 2. No filter — all expenses shown                                   #
# ------------------------------------------------------------------ #

def test_profile_no_filter_shows_all(auth_client):
    """When no query params are passed, all inserted expenses appear in the response."""
    ids = [
        _insert_expense(1, 10.00, "Food",      "2025-01-05", "Jan breakfast"),
        _insert_expense(1, 20.00, "Transport", "2025-03-15", "Mar bus"),
        _insert_expense(1, 30.00, "Bills",     "2025-09-20", "Sep bill"),
    ]
    try:
        resp = auth_client.get("/profile")
        assert resp.status_code == 200, "Expected 200 on authenticated /profile"
        body = resp.data.decode("utf-8")
        assert "Jan breakfast" in body, "Expected 'Jan breakfast' in unfiltered response"
        assert "Mar bus" in body, "Expected 'Mar bus' in unfiltered response"
        assert "Sep bill" in body, "Expected 'Sep bill' in unfiltered response"
    finally:
        _delete_expenses(ids)


# ------------------------------------------------------------------ #
# 3. Date filter narrows results                                      #
# ------------------------------------------------------------------ #

def test_profile_date_filter_narrows_results(auth_client):
    """Filtering to a specific date range shows only expenses within that range."""
    ids = [
        _insert_expense(1, 10.00, "Food",      "2024-01-10", "Early jan meal"),
        _insert_expense(1, 20.00, "Transport", "2024-06-15", "Mid year trip"),
        _insert_expense(1, 30.00, "Bills",     "2024-12-25", "Xmas bill"),
    ]
    try:
        resp = auth_client.get("/profile?date_from=2024-06-01&date_to=2024-06-30")
        assert resp.status_code == 200, "Expected 200 with valid date filter"
        body = resp.data.decode("utf-8")
        assert "Mid year trip" in body, "Expected the June expense to appear in filtered view"
        assert "Early jan meal" not in body, "Expected January expense to be excluded by filter"
        assert "Xmas bill" not in body, "Expected December expense to be excluded by filter"
    finally:
        _delete_expenses(ids)


# ------------------------------------------------------------------ #
# 4. Filter updates stats (total_spent)                               #
# ------------------------------------------------------------------ #

def test_profile_filter_updates_stats(auth_client):
    """Stats section reflects only the filtered expenses' total."""
    # Insert two expenses in Feb, one in Aug — filter to Feb only
    ids = [
        _insert_expense(1, 50.00, "Food",   "2024-02-10", "Feb lunch A"),
        _insert_expense(1, 50.00, "Health", "2024-02-20", "Feb pharmacy"),
        _insert_expense(1, 99.99, "Other",  "2024-08-05", "Aug misc"),
    ]
    try:
        resp = auth_client.get("/profile?date_from=2024-02-01&date_to=2024-02-28")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # Feb total from our two new expenses = ₹100.00
        # (seed data has no Feb 2024 expenses so we can rely on this value)
        assert "₹100.00" in body, (
            "Expected filtered total ₹100.00 (sum of the two Feb expenses) in stats"
        )
    finally:
        _delete_expenses(ids)


# ------------------------------------------------------------------ #
# 5. Inverted range — flash error message shown                       #
# ------------------------------------------------------------------ #

def test_profile_inverted_range_shows_flash(auth_client):
    """When date_from > date_to the response contains the flash error message."""
    resp = auth_client.get("/profile?date_from=2026-06-20&date_to=2026-06-01")
    assert resp.status_code == 200, "Expected 200 even for inverted range"
    body = resp.data.decode("utf-8")
    assert "Start date must be before end date." in body, (
        "Expected flash error message for inverted date range"
    )


# ------------------------------------------------------------------ #
# 6. Inverted range — falls back to unfiltered                        #
# ------------------------------------------------------------------ #

def test_profile_inverted_range_falls_back_to_unfiltered(auth_client):
    """After an inverted range error the page falls back to unfiltered (shows all expenses)."""
    ids = [
        _insert_expense(1, 15.00, "Food", "2024-03-01", "Fallback test meal"),
    ]
    try:
        resp = auth_client.get("/profile?date_from=2026-06-20&date_to=2026-06-01")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        # The page should fall back to unfiltered, so our inserted expense must appear
        assert "Fallback test meal" in body, (
            "Expected unfiltered data (including newly inserted expense) after inverted-range fallback"
        )
    finally:
        _delete_expenses(ids)


# ------------------------------------------------------------------ #
# 7. Malformed date_from — silently ignored, shows all               #
# ------------------------------------------------------------------ #

def test_profile_malformed_date_from_ignored(auth_client):
    """A malformed date_from is silently ignored; response is 200 and shows all expenses."""
    ids = [
        _insert_expense(1, 11.00, "Food", "2024-04-10", "Malformed from test"),
    ]
    try:
        resp = auth_client.get("/profile?date_from=notadate&date_to=2026-06-30")
        assert resp.status_code == 200, "Expected 200 — malformed date must not crash the app"
        body = resp.data.decode("utf-8")
        assert "Malformed from test" in body, (
            "Expected unfiltered view (all expenses) when date_from is malformed"
        )
    finally:
        _delete_expenses(ids)


# ------------------------------------------------------------------ #
# 8. Malformed date_to — silently ignored, shows all                 #
# ------------------------------------------------------------------ #

def test_profile_malformed_date_to_ignored(auth_client):
    """A malformed date_to is silently ignored; response is 200 and shows all expenses."""
    ids = [
        _insert_expense(1, 22.00, "Transport", "2024-05-05", "Malformed to test"),
    ]
    try:
        resp = auth_client.get("/profile?date_from=2024-01-01&date_to=baddate")
        assert resp.status_code == 200, "Expected 200 — malformed date must not crash the app"
        body = resp.data.decode("utf-8")
        assert "Malformed to test" in body, (
            "Expected unfiltered view (all expenses) when date_to is malformed"
        )
    finally:
        _delete_expenses(ids)


# ------------------------------------------------------------------ #
# 9. Empty range — zero stats, no crash                              #
# ------------------------------------------------------------------ #

def test_profile_empty_range_shows_zeros(auth_client):
    """A valid range with no expenses in it shows ₹0.00 and the empty-table message."""
    # Pick a far-future date range guaranteed to have no data
    resp = auth_client.get("/profile?date_from=2099-01-01&date_to=2099-01-31")
    assert resp.status_code == 200, "Expected 200 for a valid but empty date range"
    body = resp.data.decode("utf-8")
    assert "₹0.00" in body, "Expected ₹0.00 total spent when no expenses exist in the range"
    assert "No transactions match your filter." in body, (
        "Expected empty-table message when no transactions fall in the range"
    )


# ------------------------------------------------------------------ #
# 10. "This Month" preset marks the tab as active                    #
# ------------------------------------------------------------------ #

def test_profile_this_month_preset_active(auth_client):
    """Passing first-of-current-month to today activates the 'This Month' preset tab."""
    today = date.today()
    first_of_month = today.replace(day=1).isoformat()
    today_str = today.isoformat()

    resp = auth_client.get(f"/profile?date_from={first_of_month}&date_to={today_str}")
    assert resp.status_code == 200, "Expected 200 for This Month preset parameters"
    body = resp.data.decode("utf-8")

    # The template renders the active tab as: class="filter-tab active"
    # and the link text "This Month" follows immediately in the same element.
    # We look for both markers together.
    assert "filter-tab active" in body, (
        "Expected 'filter-tab active' CSS class to appear for the active preset"
    )
    assert "This Month" in body, "Expected 'This Month' label in the filter bar"

    # Confirm the active class is specifically on the This Month tab and not,
    # for example, All Time. We check that the active anchor contains "This Month".
    # Find the position of the active tab and assert "This Month" is nearby.
    active_idx = body.find("filter-tab active")
    this_month_idx = body.find("This Month")
    assert abs(active_idx - this_month_idx) < 200, (
        "Expected 'filter-tab active' and 'This Month' to be in close proximity in HTML"
    )
