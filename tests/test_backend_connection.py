import pytest
from app import app as flask_app
from database.db import init_db, seed_db
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


@pytest.fixture(autouse=True)
def setup_db():
    with flask_app.app_context():
        init_db()
        seed_db()


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ------------------------------------------------------------------ #
# get_user_by_id                                                      #
# ------------------------------------------------------------------ #

def test_get_user_by_id_valid():
    user = get_user_by_id(1)
    assert user is not None
    assert user["name"] == "Demo User"
    assert "demo@" in user["email"]
    assert user["initials"] == "DU"
    assert user["member_since"]  # non-empty formatted date


def test_get_user_by_id_not_found():
    assert get_user_by_id(9999) is None


# ------------------------------------------------------------------ #
# get_summary_stats                                                   #
# ------------------------------------------------------------------ #

def test_get_summary_stats_with_expenses():
    stats = get_summary_stats(1)
    assert stats["transaction_count"] == 8
    assert stats["total_spent"].startswith("₹")
    assert float(stats["total_spent"][1:]) > 0
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_no_expenses():
    stats = get_summary_stats(9999)
    assert stats["total_spent"] == "₹0.00"
    assert stats["transaction_count"] == 0
    assert stats["top_category"] == "—"


# ------------------------------------------------------------------ #
# get_recent_transactions                                             #
# ------------------------------------------------------------------ #

def test_get_recent_transactions_with_expenses():
    txs = get_recent_transactions(1)
    assert len(txs) == 8
    for tx in txs:
        assert "date" in tx
        assert "description" in tx
        assert "category" in tx
        assert tx["amount"].startswith("₹")
    # newest first: Jun 20 should be first
    assert txs[0]["date"] == "Jun 20"
    assert txs[-1]["date"] == "Jun 1"


def test_get_recent_transactions_no_expenses():
    assert get_recent_transactions(9999) == []


# ------------------------------------------------------------------ #
# get_category_breakdown                                              #
# ------------------------------------------------------------------ #

def test_get_category_breakdown_with_expenses():
    cats = get_category_breakdown(1)
    assert len(cats) == 7
    assert cats[0]["name"] == "Bills"
    for cat in cats:
        assert cat["amount"].startswith("₹")
        assert isinstance(cat["pct"], int)
    assert sum(c["pct"] for c in cats) == 100


def test_get_category_breakdown_no_expenses():
    assert get_category_breakdown(9999) == []


# ------------------------------------------------------------------ #
# Route tests                                                         #
# ------------------------------------------------------------------ #

def test_profile_unauthenticated_redirects(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_profile_authenticated(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_name"] = "Demo User"
    resp = client.get("/profile")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Demo User" in body
    assert "₹" in body
    assert "Bills" in body
