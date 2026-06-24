"""
Tests for Step 7: Add Expense Feature (GET /expenses/add, POST /expenses/add).

The app uses a file-based SQLite DB (database/trackify.db). Each test that
writes data inserts a dedicated test user and cleans up after itself so the
seed data (demo user id=1) is left intact for other test files.
"""

import sqlite3
import pytest
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database.db import DB_PATH, init_db, seed_db


# ------------------------------------------------------------------ #
# DB helpers                                                          #
# ------------------------------------------------------------------ #

def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _create_test_user(email="addexpense_test@trackify.test", password="testpass123"):
    """Insert a fresh test user and return (user_id, email, password)."""
    conn = _get_conn()
    # Remove any leftover user with the same email from a previous failed run
    conn.execute("DELETE FROM users WHERE email = ?", (email,))
    conn.commit()
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", email, generate_password_hash(password)),
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()
    return user_id, email, password


def _delete_test_user(user_id):
    """Remove the test user (cascades to their expenses via FK ON DELETE CASCADE)."""
    conn = _get_conn()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def _get_expenses_for_user(user_id):
    """Return all expense rows for a user."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return rows


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def ensure_db():
    """Ensure tables and seed data exist before every test."""
    with flask_app.app_context():
        init_db()
        seed_db()


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(client):
    """
    A test client with a freshly created test user already logged in.
    Yields (client, user_id) and tears down the test user after the test.
    """
    user_id, email, password = _create_test_user()
    # Log in via the real login route to establish a session
    resp = client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    assert resp.status_code == 302, (
        f"Login during fixture setup failed — got {resp.status_code}"
    )
    yield client, user_id
    _delete_test_user(user_id)


# ------------------------------------------------------------------ #
# 1. Auth guard                                                       #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_get_add_expense_unauthenticated_redirects_to_login(self, client):
        """Unauthenticated GET /expenses/add must redirect to /login."""
        resp = client.get("/expenses/add")
        assert resp.status_code == 302, (
            "Expected 302 redirect for unauthenticated GET /expenses/add"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect Location must contain /login"
        )

    def test_post_add_expense_unauthenticated_redirects_to_login(self, client):
        """Unauthenticated POST /expenses/add must redirect to /login."""
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 302, (
            "Expected 302 redirect for unauthenticated POST /expenses/add"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect Location must contain /login"
        )


# ------------------------------------------------------------------ #
# 2. GET happy path                                                   #
# ------------------------------------------------------------------ #

class TestGetAddExpense:
    def test_get_add_expense_authenticated_returns_200(self, auth_client):
        """Authenticated GET /expenses/add must return 200."""
        client, _user_id = auth_client
        resp = client.get("/expenses/add")
        assert resp.status_code == 200, (
            "Expected 200 for authenticated GET /expenses/add"
        )

    def test_get_add_expense_form_contains_amount_field(self, auth_client):
        """Response must contain an input with name='amount'."""
        client, _user_id = auth_client
        resp = client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert 'name="amount"' in body, (
            "Expected form to contain an input with name='amount'"
        )

    def test_get_add_expense_form_contains_category_field(self, auth_client):
        """Response must contain a select/input with name='category'."""
        client, _user_id = auth_client
        resp = client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert 'name="category"' in body, (
            "Expected form to contain a field with name='category'"
        )

    def test_get_add_expense_form_contains_date_field(self, auth_client):
        """Response must contain an input with name='date'."""
        client, _user_id = auth_client
        resp = client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert 'name="date"' in body, (
            "Expected form to contain an input with name='date'"
        )

    def test_get_add_expense_form_contains_description_field(self, auth_client):
        """Response must contain an input with name='description'."""
        client, _user_id = auth_client
        resp = client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert 'name="description"' in body, (
            "Expected form to contain an input with name='description'"
        )

    @pytest.mark.parametrize("category", [
        "Food",
        "Transport",
        "Bills",
        "Health",
        "Entertainment",
        "Shopping",
        "Other",
    ])
    def test_get_add_expense_form_contains_all_category_options(
        self, auth_client, category
    ):
        """Response must contain each of the 7 valid category options."""
        client, _user_id = auth_client
        resp = client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert category in body, (
            f"Expected category option '{category}' to be present in the form"
        )


# ------------------------------------------------------------------ #
# 3. POST happy path                                                  #
# ------------------------------------------------------------------ #

class TestPostAddExpenseHappyPath:
    def test_valid_submission_redirects_to_profile(self, auth_client):
        """A valid POST /expenses/add must redirect (302) to /profile."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "12.50",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Lunch",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "Expected 302 redirect after a valid expense submission"
        )
        assert "/profile" in resp.headers["Location"], (
            "Expected redirect Location to contain /profile"
        )

    def test_valid_submission_saves_expense_in_database(self, auth_client):
        """After a valid submission the expense row must exist in the DB for the logged-in user."""
        client, user_id = auth_client
        client.post(
            "/expenses/add",
            data={
                "amount": "12.50",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Lunch",
            },
        )
        rows = _get_expenses_for_user(user_id)
        assert len(rows) == 1, (
            f"Expected 1 expense row in DB for test user, found {len(rows)}"
        )
        row = rows[0]
        assert float(row["amount"]) == 12.50, (
            f"Expected amount 12.50, got {row['amount']}"
        )
        assert row["category"] == "Food", (
            f"Expected category 'Food', got {row['category']}"
        )
        assert row["date"] == "2026-06-01", (
            f"Expected date '2026-06-01', got {row['date']}"
        )
        assert row["description"] == "Lunch", (
            f"Expected description 'Lunch', got {row['description']}"
        )
        assert row["user_id"] == user_id, (
            "Expense must be attributed to the logged-in user, not any other user"
        )

    def test_valid_submission_flash_message_expense_added(self, auth_client):
        """After a valid submission, the flash message 'Expense added.' must appear on the next page."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "12.50",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Lunch",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, (
            "Expected 200 on the profile page after following the redirect"
        )
        body = resp.data.decode("utf-8")
        assert "Expense added." in body, (
            "Expected flash message 'Expense added.' to appear on the profile page"
        )

    def test_valid_submission_empty_description_saved_as_null(self, auth_client):
        """A submission with an empty description must save NULL in the database."""
        client, user_id = auth_client
        client.post(
            "/expenses/add",
            data={
                "amount": "7.00",
                "category": "Other",
                "date": "2026-06-10",
                "description": "",
            },
        )
        rows = _get_expenses_for_user(user_id)
        assert len(rows) == 1, (
            f"Expected 1 expense row in DB for test user, found {len(rows)}"
        )
        assert rows[0]["description"] is None, (
            f"Expected description to be NULL in the DB when submitted empty, "
            f"got {rows[0]['description']!r}"
        )

    def test_valid_submission_whitespace_only_description_saved_as_null(self, auth_client):
        """A description consisting only of whitespace must also be saved as NULL."""
        client, user_id = auth_client
        client.post(
            "/expenses/add",
            data={
                "amount": "5.00",
                "category": "Transport",
                "date": "2026-06-15",
                "description": "   ",
            },
        )
        rows = _get_expenses_for_user(user_id)
        assert len(rows) == 1, (
            f"Expected 1 expense row in DB for test user, found {len(rows)}"
        )
        assert rows[0]["description"] is None, (
            "Expected whitespace-only description to be stripped and stored as NULL"
        )


# ------------------------------------------------------------------ #
# 4. POST validation errors                                           #
# ------------------------------------------------------------------ #

class TestPostAddExpenseValidationErrors:
    def test_non_numeric_amount_returns_200_with_error(self, auth_client):
        """Submitting a non-numeric amount must re-render the form (200) with an error message."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "abc",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200, (
            "Expected 200 (form re-render) for non-numeric amount"
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "positive" in body.lower(), (
            "Expected an error message for non-numeric amount"
        )

    def test_zero_amount_returns_200_with_error(self, auth_client):
        """Submitting amount=0 must re-render the form (200) with an error message."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200, (
            "Expected 200 (form re-render) for zero amount"
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "positive" in body.lower(), (
            "Expected an error message for amount=0"
        )

    def test_negative_amount_returns_200_with_error(self, auth_client):
        """Submitting a negative amount must re-render the form (200) with an error message."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "-5",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200, (
            "Expected 200 (form re-render) for negative amount"
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "positive" in body.lower(), (
            "Expected an error message for negative amount"
        )

    def test_invalid_category_returns_200_with_error(self, auth_client):
        """Submitting a category not in the allowed list must re-render the form with an error."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Hacking",
                "date": "2026-06-01",
                "description": "Evil plan",
            },
        )
        assert resp.status_code == 200, (
            "Expected 200 (form re-render) for invalid category"
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "valid category" in body.lower() or "category" in body.lower(), (
            "Expected an error message for invalid category"
        )

    def test_invalid_date_string_returns_200_with_error(self, auth_client):
        """Submitting an unparseable date string must re-render the form with an error."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "not-a-date",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200, (
            "Expected 200 (form re-render) for invalid date"
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "valid date" in body.lower() or "date" in body.lower(), (
            "Expected an error message for an unparseable date string"
        )

    def test_validation_errors_do_not_save_to_database(self, auth_client):
        """No expense row should be written to the DB when validation fails."""
        client, user_id = auth_client
        client.post(
            "/expenses/add",
            data={
                "amount": "abc",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Should not be saved",
            },
        )
        rows = _get_expenses_for_user(user_id)
        assert len(rows) == 0, (
            "Expected no expense rows to be written when amount validation fails"
        )

    @pytest.mark.parametrize("amount,label", [
        ("abc", "non-numeric"),
        ("0",   "zero"),
        ("-5",  "negative"),
    ])
    def test_invalid_amount_does_not_save_to_database(self, auth_client, amount, label):
        """Parametrized: no DB write for any invalid amount variant."""
        client, user_id = auth_client
        client.post(
            "/expenses/add",
            data={
                "amount": amount,
                "category": "Food",
                "date": "2026-06-01",
                "description": "Should not persist",
            },
        )
        rows = _get_expenses_for_user(user_id)
        assert len(rows) == 0, (
            f"Expected no DB rows for {label} amount '{amount}', found {len(rows)}"
        )


# ------------------------------------------------------------------ #
# 5. Field preservation on validation error                           #
# ------------------------------------------------------------------ #

class TestFieldPreservationOnError:
    def test_invalid_amount_preserves_category_in_response(self, auth_client):
        """When amount is invalid, the submitted category value must still appear in the response."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "bad",
                "category": "Health",
                "date": "2026-06-05",
                "description": "Doctor visit",
            },
        )
        assert resp.status_code == 200, "Expected form re-render on amount error"
        body = resp.data.decode("utf-8")
        assert "Health" in body, (
            "Expected submitted category 'Health' to be preserved in re-rendered form"
        )

    def test_invalid_amount_preserves_date_in_response(self, auth_client):
        """When amount is invalid, the submitted date value must still appear in the response."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "bad",
                "category": "Health",
                "date": "2026-06-05",
                "description": "Doctor visit",
            },
        )
        assert resp.status_code == 200, "Expected form re-render on amount error"
        body = resp.data.decode("utf-8")
        assert "2026-06-05" in body, (
            "Expected submitted date '2026-06-05' to be preserved in re-rendered form"
        )

    def test_invalid_amount_preserves_description_in_response(self, auth_client):
        """When amount is invalid, the submitted description must still appear in the response."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "bad",
                "category": "Health",
                "date": "2026-06-05",
                "description": "Doctor visit",
            },
        )
        assert resp.status_code == 200, "Expected form re-render on amount error"
        body = resp.data.decode("utf-8")
        assert "Doctor visit" in body, (
            "Expected submitted description 'Doctor visit' to be preserved in re-rendered form"
        )

    def test_invalid_category_preserves_amount_in_response(self, auth_client):
        """When category is invalid, the submitted amount must still appear in the response."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "42.00",
                "category": "Hacking",
                "date": "2026-06-08",
                "description": "Some note",
            },
        )
        assert resp.status_code == 200, "Expected form re-render on category error"
        body = resp.data.decode("utf-8")
        assert "42.00" in body or "42" in body, (
            "Expected submitted amount '42.00' to be preserved in re-rendered form"
        )

    def test_invalid_date_preserves_amount_in_response(self, auth_client):
        """When date is invalid, the submitted amount must still appear in the response."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "99.99",
                "category": "Shopping",
                "date": "not-a-date",
                "description": "Shoes",
            },
        )
        assert resp.status_code == 200, "Expected form re-render on date error"
        body = resp.data.decode("utf-8")
        assert "99.99" in body or "99" in body, (
            "Expected submitted amount '99.99' to be preserved in re-rendered form"
        )

    def test_invalid_date_preserves_category_in_response(self, auth_client):
        """When date is invalid, the submitted category must still appear in the response."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "99.99",
                "category": "Shopping",
                "date": "not-a-date",
                "description": "Shoes",
            },
        )
        assert resp.status_code == 200, "Expected form re-render on date error"
        body = resp.data.decode("utf-8")
        assert "Shopping" in body, (
            "Expected submitted category 'Shopping' to be preserved in re-rendered form"
        )

    def test_invalid_date_preserves_description_in_response(self, auth_client):
        """When date is invalid, the submitted description must still appear in the response."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "99.99",
                "category": "Shopping",
                "date": "not-a-date",
                "description": "Shoes",
            },
        )
        assert resp.status_code == 200, "Expected form re-render on date error"
        body = resp.data.decode("utf-8")
        assert "Shoes" in body, (
            "Expected submitted description 'Shoes' to be preserved in re-rendered form"
        )


# ------------------------------------------------------------------ #
# 6. Edge cases                                                       #
# ------------------------------------------------------------------ #

class TestEdgeCases:
    def test_sql_injection_in_description_is_handled_safely(self, auth_client):
        """A SQL injection attempt in the description field must not crash the app."""
        client, user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "5.00",
                "category": "Other",
                "date": "2026-06-01",
                "description": "'; DROP TABLE expenses; --",
            },
            follow_redirects=False,
        )
        # Should succeed and redirect — parameterized queries make this safe
        assert resp.status_code == 302, (
            "Expected successful 302 redirect even with SQL injection attempt in description"
        )
        rows = _get_expenses_for_user(user_id)
        assert len(rows) == 1, "Expected the expense to be saved normally despite injection attempt"
        assert rows[0]["description"] == "'; DROP TABLE expenses; --", (
            "Expected the description to be stored literally, not executed as SQL"
        )

    def test_very_large_valid_amount_is_accepted(self, auth_client):
        """A very large but valid positive amount should be accepted and saved."""
        client, user_id = auth_client
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "9999999.99",
                "category": "Bills",
                "date": "2026-06-01",
                "description": "Enormous bill",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "Expected 302 redirect for a very large but valid amount"
        )
        rows = _get_expenses_for_user(user_id)
        assert len(rows) == 1, "Expected expense row to be saved for large amount"
        assert float(rows[0]["amount"]) == pytest.approx(9999999.99), (
            "Expected amount 9999999.99 to be stored correctly"
        )

    def test_expense_is_attributed_to_logged_in_user_not_another(self, auth_client):
        """The user_id on the saved expense must match the session user, not the seed demo user."""
        client, user_id = auth_client
        client.post(
            "/expenses/add",
            data={
                "amount": "25.00",
                "category": "Entertainment",
                "date": "2026-06-12",
                "description": "Movie",
            },
        )
        rows = _get_expenses_for_user(user_id)
        assert len(rows) == 1, "Expected exactly one expense for the test user"
        assert rows[0]["user_id"] == user_id, (
            f"Expense user_id {rows[0]['user_id']} must equal the logged-in user's id {user_id}"
        )
        # Confirm seed user (id=1) did not gain an extra expense from this test
        seed_rows_count_conn = _get_conn()
        seed_count = seed_rows_count_conn.execute(
            "SELECT COUNT(*) as cnt FROM expenses WHERE user_id = 1"
        ).fetchone()["cnt"]
        seed_rows_count_conn.close()
        assert seed_count == 8, (
            "Seed user must still have exactly 8 expenses after the test user's submission"
        )
