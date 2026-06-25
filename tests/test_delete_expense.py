"""
Tests for Step 9: Delete Expense Feature.

Routes under test:
  POST /expenses/<id>/delete

Query helpers under test (database/queries.py):
  delete_expense(expense_id, user_id)

The app uses a file-based SQLite DB (database/trackify.db).  Each test creates
its own isolated test user(s) and cleans up after itself via FK CASCADE so the
seed data (demo user id=1, 8 expenses) is never touched.
"""

import sqlite3
import pytest
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database.db import DB_PATH, init_db, seed_db
from database.queries import delete_expense


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
    email="deleteexpense_test@trackify.test",
    password="testpass123",
    name="Delete Test User",
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
    """Return the raw expense row (sqlite3.Row) or None for direct DB assertions."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    conn.close()
    return row


def _count_expenses(user_id):
    """Return the total number of expense rows belonging to the given user."""
    conn = _get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    conn.close()
    return count


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
        email="deleteexpense_other@trackify.test",
        name="Other Delete User",
    )
    yield user_id
    _delete_test_user(user_id)


# ================================================================== #
# UNIT TESTS — database/queries.py :: delete_expense                 #
# ================================================================== #

class TestDeleteExpenseQuery:
    """Unit tests for delete_expense(expense_id, user_id)."""

    def test_delete_expense_removes_row(self):
        """delete_expense with the correct user_id removes the row from the DB."""
        user_id, _e, _p = _create_test_user(email="del_owner@trackify.test")
        try:
            expense_id = _insert_expense(user_id, amount=35.0, category="Food",
                                         date="2026-06-01", description="Lunch")
            # Confirm row exists before deletion
            assert _fetch_expense(expense_id) is not None, (
                "Expense row must exist before calling delete_expense"
            )
            delete_expense(expense_id, user_id)
            row = _fetch_expense(expense_id)
            assert row is None, (
                f"Expected expense row {expense_id} to be gone after delete_expense "
                f"with the correct user_id, but row still exists"
            )
        finally:
            _delete_test_user(user_id)

    def test_delete_expense_wrong_user_leaves_row(self):
        """delete_expense with a wrong user_id leaves the row intact and raises no error."""
        user_a_id, _e, _p = _create_test_user(email="del_owner2@trackify.test")
        user_b_id, _e2, _p2 = _create_test_user(
            email="del_other2@trackify.test", name="Other B"
        )
        try:
            expense_id = _insert_expense(user_a_id, amount=20.0, category="Transport",
                                         date="2026-06-10", description="Bus fare")
            # Calling with user B's id must silently do nothing
            delete_expense(expense_id, user_b_id)
            row = _fetch_expense(expense_id)
            assert row is not None, (
                "Expense row must still exist after delete_expense called with wrong user_id"
            )
            assert float(row["amount"]) == pytest.approx(20.0), (
                f"Expense amount must be unchanged after delete attempt with wrong user_id, "
                f"got {row['amount']}"
            )
            assert row["category"] == "Transport", (
                "Expense category must be unchanged after delete attempt with wrong user_id"
            )
        finally:
            _delete_test_user(user_a_id)
            _delete_test_user(user_b_id)

    def test_delete_expense_nonexistent_id_no_error(self):
        """delete_expense with a non-existent expense_id raises no exception and leaves DB unchanged."""
        user_id, _e, _p = _create_test_user(email="del_noexp@trackify.test")
        try:
            # Insert one real expense so we can verify the table count stays the same
            expense_id = _insert_expense(user_id, amount=10.0)
            count_before = _count_expenses(user_id)

            # Should complete without raising any exception
            try:
                delete_expense(999999999, user_id)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(
                    f"delete_expense raised an unexpected exception for a "
                    f"non-existent expense_id: {exc}"
                )

            count_after = _count_expenses(user_id)
            assert count_after == count_before, (
                f"Expected expense count to remain {count_before} after delete on "
                f"non-existent id, but got {count_after}"
            )
        finally:
            _delete_test_user(user_id)


# ================================================================== #
# ROUTE TESTS — POST /expenses/<id>/delete — auth guard              #
# ================================================================== #

class TestDeleteExpenseAuthGuard:
    """Unauthenticated requests to POST /expenses/<id>/delete."""

    def test_delete_unauthenticated_redirects_to_login(self, client):
        """Unauthenticated POST must return 302 pointing to /login."""
        resp = client.post("/expenses/1/delete", follow_redirects=False)
        assert resp.status_code == 302, (
            f"Expected 302 redirect for unauthenticated POST /expenses/1/delete, "
            f"got {resp.status_code}"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect Location must contain /login for unauthenticated POST to delete route"
        )


# ================================================================== #
# ROUTE TESTS — POST /expenses/<id>/delete — happy path              #
# ================================================================== #

class TestDeleteExpenseHappyPath:
    """Authenticated POST /expenses/<id>/delete for the owner's own expense."""

    def test_delete_own_expense_redirects_to_profile(self, auth_client):
        """Authenticated POST for own expense must redirect (302) to /profile."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=45.0, category="Bills",
                                     date="2026-06-05", description="Electric bill")
        resp = client.post(
            f"/expenses/{expense_id}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            f"Expected 302 redirect after deleting own expense (id={expense_id}), "
            f"got {resp.status_code}"
        )
        assert "/profile" in resp.headers["Location"], (
            "Redirect Location must contain /profile after successful expense deletion"
        )

    def test_delete_own_expense_removes_from_db(self, auth_client):
        """Authenticated POST for own expense must remove the row from the DB."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=60.0, category="Health",
                                     date="2026-06-08", description="Pharmacy")
        # Confirm the row exists before the delete request
        assert _fetch_expense(expense_id) is not None, (
            "Expense row must exist in DB before issuing the delete POST"
        )
        client.post(f"/expenses/{expense_id}/delete", follow_redirects=False)
        row = _fetch_expense(expense_id)
        assert row is None, (
            f"Expected expense row {expense_id} to be gone from the DB after "
            f"a successful delete POST, but row still exists"
        )

    def test_delete_own_expense_sets_flash_message(self, auth_client):
        """After a successful delete the flash message 'Expense deleted.' must appear on /profile."""
        client, user_id = auth_client
        expense_id = _insert_expense(user_id, amount=25.0, category="Food",
                                     date="2026-06-12", description="Coffee")
        resp = client.post(
            f"/expenses/{expense_id}/delete",
            follow_redirects=True,
        )
        assert resp.status_code == 200, (
            "Expected 200 on the profile page after following the delete redirect"
        )
        body = resp.data.decode("utf-8")
        assert "Expense deleted." in body, (
            "Expected flash message 'Expense deleted.' to appear on the profile page "
            "after a successful delete"
        )


# ================================================================== #
# ROUTE TESTS — POST /expenses/<id>/delete — ownership & not found   #
# ================================================================== #

class TestDeleteExpenseOwnershipAndNotFound:
    """Authenticated POST targeting other users' expenses and non-existent ids."""

    def test_delete_other_users_expense_returns_404(self, auth_client, other_user):
        """Authenticated POST for an expense owned by another user must return 404."""
        client, _own_user_id = auth_client
        other_expense_id = _insert_expense(other_user, amount=30.0, category="Shopping",
                                           date="2026-06-03", description="Books")
        resp = client.post(
            f"/expenses/{other_expense_id}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 404, (
            f"Expected 404 when POST targets expense (id={other_expense_id}) "
            f"owned by a different user, got {resp.status_code}"
        )

    def test_delete_other_users_expense_row_intact(self, auth_client, other_user):
        """The row must still exist in the DB after a blocked cross-user delete."""
        client, _own_user_id = auth_client
        other_expense_id = _insert_expense(other_user, amount=30.0, category="Shopping",
                                           date="2026-06-03", description="Books")
        client.post(
            f"/expenses/{other_expense_id}/delete",
            follow_redirects=False,
        )
        row = _fetch_expense(other_expense_id)
        assert row is not None, (
            "The other user's expense row must still exist in the DB after a "
            "blocked cross-user delete attempt"
        )
        assert float(row["amount"]) == pytest.approx(30.0), (
            "The other user's expense amount must be unchanged after a blocked delete"
        )

    def test_delete_nonexistent_expense_returns_404(self, auth_client):
        """Authenticated POST for a non-existent expense id must return 404."""
        client, _user_id = auth_client
        resp = client.post(
            "/expenses/999999999/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 404, (
            "Expected 404 for a POST targeting a non-existent expense id, "
            f"got {resp.status_code}"
        )


# ================================================================== #
# ROUTE TESTS — HTTP method guard                                     #
# ================================================================== #

class TestDeleteExpenseMethodGuard:
    """HTTP method restrictions on /expenses/<id>/delete."""

    def test_delete_via_get_returns_405(self, client):
        """GET to the delete URL must return 405 Method Not Allowed."""
        resp = client.get("/expenses/1/delete")
        assert resp.status_code == 405, (
            f"Expected 405 Method Not Allowed for GET /expenses/1/delete, "
            f"got {resp.status_code}"
        )


# ================================================================== #
# EDGE CASES                                                          #
# ================================================================== #

class TestDeleteExpenseEdgeCases:
    """Boundary and isolation edge cases for delete."""

    def test_delete_does_not_affect_other_expenses_of_same_user(self, auth_client):
        """Deleting one expense must leave the user's other expenses untouched."""
        client, user_id = auth_client
        expense_to_delete = _insert_expense(user_id, amount=10.0, category="Food",
                                            date="2026-06-01", description="To be deleted")
        expense_to_keep = _insert_expense(user_id, amount=99.0, category="Bills",
                                          date="2026-06-02", description="To keep")
        client.post(f"/expenses/{expense_to_delete}/delete", follow_redirects=False)

        # Deleted row must be gone
        assert _fetch_expense(expense_to_delete) is None, (
            "The targeted expense must be removed from the DB after deletion"
        )
        # Sibling row must still exist
        kept_row = _fetch_expense(expense_to_keep)
        assert kept_row is not None, (
            "A sibling expense of the same user must NOT be removed when only "
            "one specific expense is deleted"
        )
        assert float(kept_row["amount"]) == pytest.approx(99.0), (
            "The kept expense amount must be unchanged after deleting a different expense"
        )

    def test_delete_does_not_affect_other_users_expenses(self, auth_client, other_user):
        """A successful delete for user A must leave user B's expenses completely untouched."""
        client, user_id = auth_client
        own_expense_id = _insert_expense(user_id, amount=15.0, category="Food",
                                         date="2026-06-01", description="Mine")
        other_expense_id = _insert_expense(other_user, amount=75.0, category="Health",
                                           date="2026-06-05", description="Theirs")
        client.post(f"/expenses/{own_expense_id}/delete", follow_redirects=False)

        other_row = _fetch_expense(other_expense_id)
        assert other_row is not None, (
            "The other user's expense must still exist after the logged-in user "
            "deletes their own expense"
        )
        assert float(other_row["amount"]) == pytest.approx(75.0), (
            "The other user's expense amount must be unchanged after deleting own expense"
        )

    @pytest.mark.parametrize("expense_id_str", ["0", "-1", "abc"])
    def test_delete_invalid_id_format_returns_404_or_405(self, auth_client, expense_id_str):
        """
        Non-integer or out-of-range id segments in the URL must not reach the handler.
        Flask's int converter returns 404 for non-integer path segments;
        negative or zero integer values reach the handler and produce 404 from the DB check.
        """
        client, _user_id = auth_client
        resp = client.post(
            f"/expenses/{expense_id_str}/delete",
            follow_redirects=False,
        )
        assert resp.status_code in (404, 405), (
            f"Expected 404 or 405 for delete URL with invalid id segment "
            f"'{expense_id_str}', got {resp.status_code}"
        )
