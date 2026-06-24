from datetime import datetime
from database.db import get_db


def _date_filter(user_id, date_from, date_to):
    where  = "WHERE user_id = ?"
    params = [user_id]
    if date_from and date_to:
        where  += " AND date BETWEEN ? AND ?"
        params += [date_from, date_to]
    return where, params


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


def get_summary_stats(user_id, date_from=None, date_to=None):
    conn = get_db()
    try:
        where, params = _date_filter(user_id, date_from, date_to)

        row = conn.execute(
            f"SELECT COUNT(*) as cnt, COALESCE(SUM(amount), 0) as total "
            f"FROM expenses {where}",
            params,
        ).fetchone()
        total = row["total"]
        count = row["cnt"]

        top_row = conn.execute(
            f"SELECT category FROM expenses {where} "
            f"GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            params,
        ).fetchone()
        top_category = top_row["category"] if top_row else "—"

        return {
            "total_spent": f"₹{total:.2f}",
            "transaction_count": count,
            "top_category": top_category,
        }
    finally:
        conn.close()


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    conn = get_db()
    try:
        where, params = _date_filter(user_id, date_from, date_to)

        rows = conn.execute(
            f"SELECT id, date, description, category, amount FROM expenses "
            f"{where} ORDER BY date DESC LIMIT ?",
            params + [limit],
        ).fetchall()

        transactions = []
        for row in rows:
            dt = datetime.strptime(row["date"], "%Y-%m-%d")
            transactions.append({
                "id": row["id"],
                "date": dt.strftime("%b ") + str(dt.day),
                "description": row["description"],
                "category": row["category"],
                "amount": f"₹{row['amount']:.2f}",
            })
        return transactions
    finally:
        conn.close()


def get_expense_by_id(expense_id, user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, amount, category, date, description FROM expenses "
            "WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "amount": row["amount"],
            "category": row["category"],
            "date": row["date"],
            "description": row["description"],
        }
    finally:
        conn.close()


def update_expense(expense_id, user_id, amount, category, date, description):
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE expenses SET amount=?, category=?, date=?, description=? "
            "WHERE id=? AND user_id=?",
            (amount, category, date, description, expense_id, user_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def insert_expense(user_id, amount, category, date, description):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
        )
        conn.commit()
    finally:
        conn.close()


def get_category_breakdown(user_id, date_from=None, date_to=None):
    conn = get_db()
    try:
        where, params = _date_filter(user_id, date_from, date_to)

        rows = conn.execute(
            f"SELECT category as name, SUM(amount) as total "
            f"FROM expenses {where} "
            f"GROUP BY category ORDER BY total DESC",
            params,
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
