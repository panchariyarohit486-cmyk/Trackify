from datetime import datetime
from database.db import get_db


def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        dt = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        words = row["name"].split()
        initials = "".join(w[0].upper() for w in words[:2])
        return {
            "name": row["name"],
            "email": row["email"],
            "member_since": dt.strftime("%B %Y"),
            "initials": initials,
        }
    finally:
        conn.close()


def get_summary_stats(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(amount), 0) as total "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        total = row["total"]
        count = row["cnt"]

        top_row = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        top_category = top_row["category"] if top_row else "—"

        return {
            "total_spent": f"₹{total:.2f}",
            "transaction_count": count,
            "top_category": top_category,
        }
    finally:
        conn.close()


def get_recent_transactions(user_id, limit=10):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()

        transactions = []
        for row in rows:
            dt = datetime.strptime(row["date"], "%Y-%m-%d")
            transactions.append({
                "date": dt.strftime("%b ") + str(dt.day),
                "description": row["description"],
                "category": row["category"],
                "amount": f"₹{row['amount']:.2f}",
            })
        return transactions
    finally:
        conn.close()


def get_category_breakdown(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category as name, SUM(amount) as total "
            "FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY total DESC",
            (user_id,),
        ).fetchall()

        if not rows:
            return []

        overall_total = sum(row["total"] for row in rows)
        categories = []
        for row in rows:
            categories.append({
                "name": row["name"],
                "amount": f"₹{row['total']:.2f}",
                "pct": round(row["total"] / overall_total * 100),
            })

        remainder = 100 - sum(c["pct"] for c in categories)
        categories[0]["pct"] += remainder

        return categories
    finally:
        conn.close()
