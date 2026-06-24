"""
Tests for Step 8: Edit Expense Feature.

Routes under test:
  GET  /expenses/<id>/edit
  POST /expenses/<id>/edit

Query helpers under test (database/queries.py):
  get_expense_by_id(expense_id, user_id)
  update_expense(expense_id, user_id, amount, category, date, description)

The app uses a file-based SQLite DB (database/trackify.db).  Each test creates
its own isolated test user(s) and cleans up after itself via FK CASCADE so the
seed data (demo user id=1, 8 expenses) is never touched.
"""

import sqlite3
import pytest
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database.db import DB_PATH, init_db, seed_db
from database.queries import get_expense_by_id, update_expense


# ------------------------------------------------------------------ #
# Low-level DB helpers                                                #
# ------------------------------------------------------------------ #

def _get_conn():
    """Return a raw sqlite3 connection to the shared file-based DB."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _create_test_user(
    email="editexpense_test@trackify.test",
    password="testpass123",
    name="Edit Test User",
):
    """Insert a unique test user; remove any leftover with the same email first."""
    conn = _get_conn()
    conn.execute("DELETE FROM users WHERE email = ?", (email,))
    conn.commit()
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash(password)),
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()
    return user_id, email, password


def _delete_test_user(user_id):
    """Remove the test user — ON DELETE CASCADE removes their expenses too."""
    conn = _get_conn()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def _insert_expense(user_id, amount=50.0, category="Food",
                    date="2026-06-01", description="Test meal"):
    """Insert a single expense row for the given user and return its id."""
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date, description),
    )
    expense_id = cur.lastrowid
    conn.commit()
    conn.close()
    return expense_id


def _fetch_expense(expense_id):
    """Return the raw expense row (sqlite3.Row) for direct DB assertions."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    conn.close()
    return row


# ------------------------------------------------------------------ #
# Pytest fixtures                                                     #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def ensure_db():
    """Guarantee that tables and seed data exist before every test."""
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
    Test client with a freshly created user already logged in.
    Yields (client, user_id).  The user (and their expenses) is removed after
    the test via FK CASCADE.
    """
    user_id, email, password = _create_test_user()
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


@pytest.fixture
def other_user():
    """
    A second, distinct user who does NOT own the primary test user's expenses.
    Yields user_id.  Removed after the test.
    """
    user_id, _email, _pw = _create_test_user(
        email="editexpense_other@trackify.test",
        name="Other User",
    )
    yield user_id
    _delete_test_user(user_id)


# ================================================================== #
# UNIT TESTS — database/queries.py                                    #
# ================================================================== #

class TestGetExpenseById:
    """Unit tests for get_expense_by_id(expense_id, user_id)."""

    def test_valid_id_correct_user_returns_row(self):
        """Valid expense_id owned by the given user_id returns a dict-like row."""
        user_id, _e, _p = _create_test_user(email="gei_owner@trackify.test")
        try:
            expense_id = _insert_expense(user_id, amount=42.0, category="Health",
                                         date="2026-05-15", description="Checkup")
            result = get_expense_by_id(expense_id, user_id)
            assert result is not None, (
                "Expected a row back for a valid expense_id + correct user_id"
            )
            assert result["id"] == expense_id, (
                f"Expected row id {expense_id}, got {result['id']}"
            )
            assert float(result["amount"]) == pytest.approx(42.0), (
                f"Expected amount 42.0, got {result['amount']}"
            )
            assert result["category"] == "Health", (
                f"Expected category 'Health', got {result['category']}"
            )
            assert result["date"] == "2026-05-15", (
                f"Expected date '2026-05-15', got {result['date']}"
            )
            assert result["description"] == "Checkup", (
                f"Expected description 'Checkup', got {result['description']}"
            )
        finally:
            _delete_test_user(user_id)

    def test_valid_id_wrong_user_returns_none(self):
        """Valid expense_id belonging to user A returns None when queried with user B's id."""
        user_a_id, _e, _p = _create_test_user(email="gei_usera@trackify.test")
        user_b_id, _e2, _p2 = _create_test_user(email="gei_userb@trackify.test",
                                                  name="User B")
        try:
            expense_id = _insert_expense(user_a_id)
            result = get_expense_by_id(expense_id, user_b_id)
            assert result is None, (
                "Expected None when querying an expense with a different user's id"
            )
        finally:
            _delete_test_user(user_a_id)
            _delete_test_user(user_b_id)

    def test_nonexistent_id_returns_none(self):
        """A completely made-up expense_id returns None regardless of user_id."""
        user_id, _e, _p = _create_test_user(email="gei_noexp@trackify.test")
        try:
            result = get_expense_by_id(999999999, user_id)
            assert result is None, (
                "Expected None for a non-existent expense_id"
            )
        finally:
            _delete_test_user(user_id)


class TestUpdateExpense:
    """Unit tests for update_expense(expense_id, user_id, amount, category, date, description)."""

    def test_valid_update_reflects_new_amount_in_db(self):
        """update_expense with correct user_id changes the amount row in the DB."""
        user_id, _e, _p = _create_test_user(email="upd_owner@trackify.test")
        try:
            expense_id = _insert_expense(user_id, amount=10.0, category="Food",
                                         date="2026-06-01", description="Original")
            update_expense(expense_id, user_id, 99.0, "Transport", "2026-06-10", "Updated")
            row = _fetch_expense(expense_id)
            assert row is not None, "Expense row must still exist after update"
            assert float(row["amount"]) == pytest.approx(99.0), (
                f"Expected updated amount 99.0, got {row['amount']}"
            )
            assert row["category"] == "Transport", (
                f"Expected updated category 'Transport', got {row['category']}"
            )
            assert row["date"] == "2026-06-10", (
                f"Expected updated date '2026-06-10', got {row['date']}"
            )
            assert row["description"] == "Updated", (
                f"Expected updated description 'Updated', got {row['description']}"
            )
        finally:
            _delete_test_user(user_id)

    def test_wrong_user_leaves_row_unchanged_no_error(self):
        """update_expense with a wrong user_id must not mutate the row and must not raise."""
        user_a_id, _e, _p = _create_test_user(email="upd_owner2@trackify.test")
        user_b_id, _e2, _p2 = _create_test_user(email="upd_other2@trackify.test",
                                                  name="Other B")
        try:
            expense_id = _insert_expense(user_a_id, amount=25.0, category="Bills",
                                         date="2026-06-05", description="Power bill")
            # Should silently do nothing — no exception expected
            update_expense(expense_id, user_b_id, 999.0, "Shopping", "2026-01-01", "Hijacked")
            row = _fetch_expense(expense_id)
            assert float(row["amount"]) == pytest.approx(25.0), (
                "Row amount must be unchanged when update targets wrong user_id"
            )
            assert row["category"] == "Bills", (
                "Row category must be unchanged when update targets wrong user_id"
            )
            assert row["date"] == "2026-06-05", (
                "Row date must be unchanged when update targets wrong user_id"
            )
        finally:
            _delete_test_user(user_a_id)
            _delete_test_user(user_b_id)


# ================================================================== #
# ROUTE TESTS — GET /expenses/<id>/edit                               #
# ================================================================== #

class TestGetEditExpenseAuthGuard:
    """Unauthenticated requests to GET /expenses/<id>/edit."""

    def test_unauthenticated_get_redirects_to_login(self, client):
        """Unauthenticated GET must return 302 pointing to /login."""
        resp = client.get("/expenses/1/edit")
        assert resp.status_code == 302, (
            "Expected 302 redirect for unauthenticated GET /expenses/1/edit"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect Location must contain /login for unauthenticated GET"
        )


class TestGetEditExpenseHappyPath:
    """Authenticated GET /expenses/<id>/edit for the owner's expense."""

    def test_own_expense_returns_200(self, auth_client):
        """Authenticated GET for own expense returns 200."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=30.0, category="Food",
                                     date="2026-06-01", description="Dinner")
        resp = client.get(f"/expenses/{expense_id}/edit")
        assert resp.status_code == 200, (
            f"Expected 200 for GET /expenses/{expense_id}/edit with authenticated owner"
        )

    def test_own_expense_form_prefilled_with_amount(self, auth_client):
        """Form amount field must be pre-filled with the expense's current amount."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=75.5, category="Food",
                                     date="2026-06-01", description="Dinner")
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert "75.5" in body, (
            "Expected the expense amount '75.5' to be pre-filled in the edit form"
        )

    def test_own_expense_form_prefilled_with_date(self, auth_client):
        """Form date field must be pre-filled with the expense's current date."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=30.0, category="Food",
                                     date="2026-06-15", description="Dinner")
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert "2026-06-15" in body, (
            "Expected the expense date '2026-06-15' to be pre-filled in the edit form"
        )

    def test_own_expense_form_prefilled_with_description(self, auth_client):
        """Form description field must be pre-filled with the expense's current description."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=30.0, category="Food",
                                     date="2026-06-01", description="Friday lunch")
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert "Friday lunch" in body, (
            "Expected the expense description 'Friday lunch' to be pre-filled in the edit form"
        )

    def test_own_expense_form_has_category_select(self, auth_client):
        """Form must contain a <select> with name='category'."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert 'name="category"' in body, (
            "Expected a <select> with name='category' in the edit form"
        )

    def test_own_expense_correct_category_is_preselected(self, auth_client):
        """The category matching the stored expense must carry the 'selected' attribute."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, category="Entertainment")
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")
        # The template emits: <option value="Entertainment" selected>Entertainment</option>
        assert "Entertainment" in body, (
            "Expected 'Entertainment' to appear in the edit form category options"
        )
        # Verify that the selected marker appears alongside the correct value
        assert 'value="Entertainment"' in body and "selected" in body, (
            "Expected 'Entertainment' option to be marked as selected in the form"
        )

    @pytest.mark.parametrize("category", [
        "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"
    ])
    def test_own_expense_all_category_options_present(self, auth_client, category):
        """All 7 valid categories must be rendered as options in the select."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert category in body, (
            f"Expected category option '{category}' to be present in the edit form"
        )

    def test_own_expense_form_contains_amount_input(self, auth_client):
        """Form must contain an input with name='amount'."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert 'name="amount"' in body, (
            "Expected an input with name='amount' in the edit form"
        )

    def test_own_expense_form_contains_date_input(self, auth_client):
        """Form must contain an input with name='date'."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert 'name="date"' in body, (
            "Expected an input with name='date' in the edit form"
        )

    def test_own_expense_form_contains_description_field(self, auth_client):
        """Form must contain a field with name='description'."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert 'name="description"' in body, (
            "Expected a field with name='description' in the edit form"
        )

    def test_own_expense_form_has_save_changes_button(self, auth_client):
        """The form submit button must say 'Save Changes'."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.get(f"/expenses/{expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert "Save Changes" in body, (
            "Expected a 'Save Changes' submit button in the edit form"
        )


class TestGetEditExpenseOwnershipAndNotFound:
    """GET /expenses/<id>/edit for other users' expenses and non-existent ids."""

    def test_other_users_expense_returns_404(self, auth_client, other_user):
        """Authenticated GET for an expense owned by another user must return 404."""
        client, _own_user_id = auth_client
        # Insert expense belonging to the OTHER user, not the logged-in one
        other_expense_id = _insert_expense(other_user, amount=20.0)
        resp = client.get(f"/expenses/{other_expense_id}/edit")
        assert resp.status_code == 404, (
            f"Expected 404 when accessing another user's expense "
            f"(expense_id={other_expense_id})"
        )

    def test_nonexistent_expense_id_returns_404(self, auth_client):
        """Authenticated GET for a non-existent expense id must return 404."""
        client, _user_id = auth_client
        resp = client.get("/expenses/999999999/edit")
        assert resp.status_code == 404, (
            "Expected 404 for a GET request targeting a non-existent expense id"
        )


# ================================================================== #
# ROUTE TESTS — POST /expenses/<id>/edit                              #
# ================================================================== #

class TestPostEditExpenseAuthGuard:
    """Unauthenticated requests to POST /expenses/<id>/edit."""

    def test_unauthenticated_post_redirects_to_login(self, client):
        """Unauthenticated POST must return 302 pointing to /login."""
        resp = client.post(
            "/expenses/1/edit",
            data={
                "amount": "20.00",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 302, (
            "Expected 302 redirect for unauthenticated POST /expenses/1/edit"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect Location must contain /login for unauthenticated POST"
        )


class TestPostEditExpenseHappyPath:
    """POST /expenses/<id>/edit with valid data."""

    def test_valid_update_redirects_to_profile(self, auth_client):
        """A valid POST must redirect (302) to /profile."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=10.0, category="Food",
                                     date="2026-06-01", description="Original")
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "55.00",
                "category": "Transport",
                "date": "2026-06-20",
                "description": "Bus pass",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "Expected 302 redirect after a valid expense update"
        )
        assert "/profile" in resp.headers["Location"], (
            "Expected redirect Location to contain /profile after a valid update"
        )

    def test_valid_update_reflects_amount_in_db(self, auth_client):
        """After a valid POST the amount column in the DB must hold the new value."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=10.0, category="Food",
                                     date="2026-06-01", description="Original")
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "88.50",
                "category": "Shopping",
                "date": "2026-06-22",
                "description": "New shoes",
            },
        )
        row = _fetch_expense(expense_id)
        assert float(row["amount"]) == pytest.approx(88.50), (
            f"Expected DB amount 88.50 after update, got {row['amount']}"
        )

    def test_valid_update_reflects_category_in_db(self, auth_client):
        """After a valid POST the category column must hold the new value."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, category="Food")
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "20.00",
                "category": "Bills",
                "date": "2026-06-10",
                "description": "Electric",
            },
        )
        row = _fetch_expense(expense_id)
        assert row["category"] == "Bills", (
            f"Expected DB category 'Bills' after update, got {row['category']}"
        )

    def test_valid_update_reflects_date_in_db(self, auth_client):
        """After a valid POST the date column must hold the new value."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, date="2026-06-01")
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "15.00",
                "category": "Food",
                "date": "2026-07-04",
                "description": "",
            },
        )
        row = _fetch_expense(expense_id)
        assert row["date"] == "2026-07-04", (
            f"Expected DB date '2026-07-04' after update, got {row['date']}"
        )

    def test_valid_update_reflects_description_in_db(self, auth_client):
        """After a valid POST the description column must hold the new value."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, description="Old note")
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "20.00",
                "category": "Food",
                "date": "2026-06-10",
                "description": "New note",
            },
        )
        row = _fetch_expense(expense_id)
        assert row["description"] == "New note", (
            f"Expected DB description 'New note' after update, got {row['description']}"
        )

    def test_no_description_saves_null_in_db(self, auth_client):
        """When description is submitted empty the DB must store NULL, and route must redirect."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, description="Has a note")
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "12.00",
                "category": "Other",
                "date": "2026-06-01",
                "description": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "Expected 302 redirect when updating with an empty description"
        )
        assert "/profile" in resp.headers["Location"], (
            "Expected redirect to /profile when updating with an empty description"
        )
        row = _fetch_expense(expense_id)
        assert row["description"] is None, (
            f"Expected description to be NULL in DB when submitted empty, "
            f"got {row['description']!r}"
        )

    def test_whitespace_only_description_saves_null_in_db(self, auth_client):
        """A whitespace-only description must be stripped and stored as NULL."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, description="Note")
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "12.00",
                "category": "Other",
                "date": "2026-06-01",
                "description": "    ",
            },
        )
        row = _fetch_expense(expense_id)
        assert row["description"] is None, (
            "Expected whitespace-only description to be stored as NULL after update"
        )

    def test_valid_update_flash_message_appears(self, auth_client):
        """After a successful update the flash message 'Expense updated.' must appear."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "30.00",
                "category": "Health",
                "date": "2026-06-15",
                "description": "Doctor",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, (
            "Expected 200 on the profile page after following the redirect"
        )
        body = resp.data.decode("utf-8")
        assert "Expense updated." in body, (
            "Expected flash message 'Expense updated.' to appear on the profile page"
        )


class TestPostEditExpenseOwnershipAndNotFound:
    """POST /expenses/<id>/edit targeting other users' expenses and non-existent ids."""

    def test_other_users_expense_returns_404(self, auth_client, other_user):
        """POST targeting an expense owned by another user must return 404."""
        client, _own_user_id = auth_client
        other_expense_id = _insert_expense(other_user, amount=15.0)
        resp = client.post(
            f"/expenses/{other_expense_id}/edit",
            data={
                "amount": "99.00",
                "category": "Shopping",
                "date": "2026-06-01",
                "description": "Hijack attempt",
            },
        )
        assert resp.status_code == 404, (
            "Expected 404 when POST targets an expense owned by a different user"
        )

    def test_other_users_expense_post_does_not_mutate_db(self, auth_client, other_user):
        """A 404'd cross-user POST must leave the original expense row intact."""
        client, _own_user_id = auth_client
        other_expense_id = _insert_expense(other_user, amount=15.0, category="Food")
        client.post(
            f"/expenses/{other_expense_id}/edit",
            data={
                "amount": "999.00",
                "category": "Shopping",
                "date": "2026-01-01",
                "description": "Hijack",
            },
        )
        row = _fetch_expense(other_expense_id)
        assert float(row["amount"]) == pytest.approx(15.0), (
            "The other user's expense must remain unchanged after a blocked cross-user POST"
        )

    def test_nonexistent_expense_id_returns_404(self, auth_client):
        """POST for a non-existent expense id must return 404."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/999999999/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Ghost",
            },
        )
        assert resp.status_code == 404, (
            "Expected 404 for a POST targeting a non-existent expense id"
        )


# ================================================================== #
# ROUTE TESTS — POST validation errors                                #
# ================================================================== #

class TestPostEditExpenseValidationErrors:
    """POST /expenses/<id>/edit with invalid form data."""

    def test_missing_amount_returns_200_with_error(self, auth_client):
        """Submitting without an amount field must re-render the form (200) with an error."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200, (
            "Expected 200 (form re-render) when amount is missing"
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "positive" in body.lower(), (
            "Expected an error message when amount is missing"
        )

    def test_zero_amount_returns_200_with_error(self, auth_client):
        """Submitting amount=0 must re-render the form (200) with an error."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200, (
            "Expected 200 (form re-render) when amount=0"
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "positive" in body.lower(), (
            "Expected an error message for amount=0"
        )

    def test_nonnumeric_amount_returns_200_with_error(self, auth_client):
        """Submitting a non-numeric amount must re-render the form (200) with an error."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "abc",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200, (
            "Expected 200 (form re-render) when amount is non-numeric"
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "positive" in body.lower(), (
            "Expected an error message for non-numeric amount"
        )

    def test_invalid_category_returns_200_with_error(self, auth_client):
        """Submitting a category not in the allowed list must re-render the form with an error."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "10.00",
                "category": "Hacking",
                "date": "2026-06-01",
                "description": "Evil plan",
            },
        )
        assert resp.status_code == 200, (
            "Expected 200 (form re-render) for an invalid category value"
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "valid category" in body.lower() or "category" in body.lower(), (
            "Expected an error message for an invalid category"
        )

    def test_invalid_date_string_returns_200_with_error(self, auth_client):
        """Submitting an unparseable date must re-render the form (200) with an error."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "not-a-date",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200, (
            "Expected 200 (form re-render) for an invalid date string"
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "valid date" in body.lower() or "date" in body.lower(), (
            "Expected an error message for an unparseable date string"
        )

    @pytest.mark.parametrize("amount,label", [
        ("",    "empty"),
        ("0",   "zero"),
        ("-5",  "negative"),
        ("abc", "non-numeric"),
    ])
    def test_invalid_amount_does_not_mutate_db(self, auth_client, amount, label):
        """Parametrized: a validation error on amount must not change the stored row."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=77.0, category="Health",
                                     date="2026-05-01", description="Original")
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": amount,
                "category": "Shopping",
                "date": "2026-07-01",
                "description": "Should not be saved",
            },
        )
        row = _fetch_expense(expense_id)
        assert float(row["amount"]) == pytest.approx(77.0), (
            f"Expected DB amount unchanged (77.0) after {label} amount validation "
            f"error, got {row['amount']}"
        )
        assert row["category"] == "Health", (
            f"Expected DB category unchanged ('Health') after {label} amount error"
        )

    def test_invalid_category_does_not_mutate_db(self, auth_client):
        """A validation error on category must not change the stored row."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=50.0, category="Food",
                                     date="2026-06-01", description="Lunch")
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "InvalidCategory",
                "date": "2026-06-01",
                "description": "Should not be saved",
            },
        )
        row = _fetch_expense(expense_id)
        assert row["category"] == "Food", (
            "Expected DB category unchanged ('Food') after invalid category error"
        )

    def test_invalid_date_does_not_mutate_db(self, auth_client):
        """A validation error on date must not change the stored row."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=50.0, category="Food",
                                     date="2026-06-01", description="Lunch")
        client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "50.00",
                "category": "Food",
                "date": "32-13-9999",
                "description": "Should not be saved",
            },
        )
        row = _fetch_expense(expense_id)
        assert row["date"] == "2026-06-01", (
            "Expected DB date unchanged ('2026-06-01') after invalid date error"
        )


# ================================================================== #
# ROUTE TESTS — POST field preservation on validation error           #
# ================================================================== #

class TestPostEditExpenseFieldPreservation:
    """When POST validation fails, the re-rendered form must show submitted values."""

    def test_invalid_amount_preserves_submitted_category(self, auth_client):
        """Re-rendered form must contain the submitted category when amount is invalid."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, category="Food")
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "bad",
                "category": "Transport",
                "date": "2026-06-10",
                "description": "Commute",
            },
        )
        body = resp.data.decode("utf-8")
        assert "Transport" in body, (
            "Expected submitted category 'Transport' preserved in re-rendered form "
            "when amount is invalid"
        )

    def test_invalid_amount_preserves_submitted_date(self, auth_client):
        """Re-rendered form must contain the submitted date when amount is invalid."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "bad",
                "category": "Food",
                "date": "2026-07-15",
                "description": "Dinner",
            },
        )
        body = resp.data.decode("utf-8")
        assert "2026-07-15" in body, (
            "Expected submitted date '2026-07-15' preserved in re-rendered form "
            "when amount is invalid"
        )

    def test_invalid_amount_preserves_submitted_description(self, auth_client):
        """Re-rendered form must contain the submitted description when amount is invalid."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "bad",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Special dinner",
            },
        )
        body = resp.data.decode("utf-8")
        assert "Special dinner" in body, (
            "Expected submitted description 'Special dinner' preserved in "
            "re-rendered form when amount is invalid"
        )

    def test_invalid_category_preserves_submitted_amount(self, auth_client):
        """Re-rendered form must contain the submitted amount when category is invalid."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "63.00",
                "category": "Bogus",
                "date": "2026-06-01",
                "description": "Note",
            },
        )
        body = resp.data.decode("utf-8")
        assert "63" in body, (
            "Expected submitted amount '63.00' preserved in re-rendered form "
            "when category is invalid"
        )

    def test_invalid_date_preserves_submitted_amount(self, auth_client):
        """Re-rendered form must contain the submitted amount when date is invalid."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "44.44",
                "category": "Shopping",
                "date": "not-a-date",
                "description": "Shoes",
            },
        )
        body = resp.data.decode("utf-8")
        assert "44" in body, (
            "Expected submitted amount '44.44' preserved in re-rendered form "
            "when date is invalid"
        )

    def test_invalid_date_preserves_submitted_description(self, auth_client):
        """Re-rendered form must contain the submitted description when date is invalid."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "20.00",
                "category": "Food",
                "date": "totally-wrong",
                "description": "Weekend brunch",
            },
        )
        body = resp.data.decode("utf-8")
        assert "Weekend brunch" in body, (
            "Expected submitted description 'Weekend brunch' preserved in "
            "re-rendered form when date is invalid"
        )


# ================================================================== #
# EDGE CASES                                                          #
# ================================================================== #

class TestPostEditExpenseEdgeCases:
    """Boundary and security edge cases."""

    def test_sql_injection_in_description_is_stored_literally(self, auth_client):
        """SQL injection in the description must be stored as a literal string, not executed."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, description="Clean")
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "5.00",
                "category": "Other",
                "date": "2026-06-01",
                "description": "'; DROP TABLE expenses; --",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "Expected 302 redirect even when description contains a SQL injection attempt"
        )
        row = _fetch_expense(expense_id)
        assert row is not None, (
            "Expense row must still exist after update with injection attempt in description"
        )
        assert row["description"] == "'; DROP TABLE expenses; --", (
            "Description must be stored verbatim — parameterized queries must neutralise injection"
        )

    def test_negative_amount_returns_200_with_error(self, auth_client):
        """A negative amount must re-render the form with an error."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "-10.00",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Negative",
            },
        )
        assert resp.status_code == 200, (
            "Expected 200 (form re-render) for a negative amount"
        )
        body = resp.data.decode("utf-8")
        assert "error" in body.lower() or "positive" in body.lower(), (
            "Expected an error message for a negative amount"
        )

    def test_update_does_not_affect_other_user_expenses(self, auth_client, other_user):
        """
        A successful update for user A must leave user B's expenses completely untouched.
        """
        client, user_id = auth_client
        own_expense_id = _insert_expense(user_id, amount=20.0, category="Food",
                                         date="2026-06-01", description="Mine")
        other_expense_id = _insert_expense(other_user, amount=50.0, category="Bills",
                                           date="2026-06-05", description="Theirs")
        client.post(
            f"/expenses/{own_expense_id}/edit",
            data={
                "amount": "30.00",
                "category": "Transport",
                "date": "2026-06-10",
                "description": "Updated mine",
            },
        )
        other_row = _fetch_expense(other_expense_id)
        assert float(other_row["amount"]) == pytest.approx(50.0), (
            "The other user's expense amount must be unchanged after updating the logged-in "
            "user's own expense"
        )
        assert other_row["category"] == "Bills", (
            "The other user's expense category must be unchanged after updating own expense"
        )

    def test_large_valid_amount_is_accepted(self, auth_client):
        """A very large but valid positive amount should be accepted and saved."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=1.0)
        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "9999999.99",
                "category": "Bills",
                "date": "2026-06-01",
                "description": "Huge bill",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "Expected 302 redirect for a very large but valid amount"
        )
        row = _fetch_expense(expense_id)
        assert float(row["amount"]) == pytest.approx(9999999.99), (
            "Expected large amount 9999999.99 to be stored correctly after update"
        )
