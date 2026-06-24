# Step 7 — Add Expense Feature (Trackify)

> **Type:** Feature implementation  
> **Scope:** Route handler + HTML template  
> **Risk:** Low — no schema changes, no new dependencies  
> **Depends on:** Steps 1, 2, 3, 5

---

## What This Step Does

Replaces the placeholder `/expenses/add` route with a fully working form flow.  
A logged-in user can submit a new expense → it gets saved to the database → they're redirected to their profile where the new entry immediately appears.

---

## User Journey

```
User (logged in)
  │
  ▼
GET /expenses/add
  │  → renders empty form with today's date pre-filled
  ▼
User fills in: Amount, Category, Date, Description (optional)
  │
  ▼
POST /expenses/add
  ├── INVALID input?
  │     └── re-render form with error + keep user's entered values
  │
  └── VALID input?
        └── INSERT into expenses table
              └── flash("Expense added.")
                    └── redirect → /profile
```

---

## Routes

| Method | URL | Auth | Action |
|--------|-----|------|--------|
| `GET` | `/expenses/add` | ✅ Required | Render empty form |
| `POST` | `/expenses/add` | ✅ Required | Validate → Insert → Redirect |

> Unauthenticated requests on both routes must redirect to `/login`.

---

## Files Overview

### Files to **modify**

#### `app.py`

Replace the existing stub route with this full handler:

```python
from datetime import date
from datetime import datetime

VALID_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]

@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "GET":
        return render_template(
            "expenses/add.html",
            today=date.today().isoformat()
        )

    # --- Read form data ---
    raw_amount      = request.form.get("amount", "")
    raw_category    = request.form.get("category", "")
    raw_date        = request.form.get("date", "")
    raw_description = request.form.get("description", "").strip()

    # --- Validate amount ---
    try:
        amount = float(raw_amount)
        if amount <= 0:
            raise ValueError
    except ValueError:
        return render_template("expenses/add.html",
            error="Amount must be a positive number.",
            form=request.form)

    # --- Validate category ---
    if raw_category not in VALID_CATEGORIES:
        return render_template("expenses/add.html",
            error="Please select a valid category.",
            form=request.form)

    # --- Validate date ---
    try:
        datetime.strptime(raw_date, "%Y-%m-%d")
    except ValueError:
        return render_template("expenses/add.html",
            error="Please enter a valid date (YYYY-MM-DD).",
            form=request.form)

    # --- Sanitise description ---
    description = raw_description if raw_description else None

    # --- Insert ---
    db = get_db()
    db.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (session["user_id"], amount, raw_category, raw_date, description)
    )
    db.commit()

    flash("Expense added.")
    return redirect(url_for("profile"))
```

---

### Files to **create**

#### `templates/expenses/add.html`

```html
{% extends "base.html" %}

{% block title %}Add Expense{% endblock %}

{% block content %}
<h1>Add Expense</h1>

{% if error %}
  <p class="error">{{ error }}</p>
{% endif %}

<form method="POST">

  <label for="amount">Amount</label>
  <input
    type="number"
    id="amount"
    name="amount"
    step="0.01"
    min="0.01"
    value="{{ form.amount if form else '' }}"
    required
  >

  <label for="category">Category</label>
  <select id="category" name="category" required>
    {% for cat in ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"] %}
      <option value="{{ cat }}"
        {% if form and form.category == cat %}selected{% endif %}>
        {{ cat }}
      </option>
    {% endfor %}
  </select>

  <label for="date">Date</label>
  <input
    type="date"
    id="date"
    name="date"
    value="{{ form.date if form else today }}"
    required
  >

  <label for="description">Description <span>(optional)</span></label>
  <input
    type="text"
    id="description"
    name="description"
    value="{{ form.description if form else '' }}"
  >

  <button type="submit">Add Expense</button>

</form>

<a href="{{ url_for('profile') }}">← Back to profile</a>

{% endblock %}
```

---

## Validation Rules

| Field | Rule | Error Condition |
|-------|------|----------------|
| `amount` | Must parse as `float` and be `> 0` | Non-numeric string, `0`, or negative |
| `category` | Must be one of the 7 allowed values | Any value not in `VALID_CATEGORIES` |
| `date` | Must match `YYYY-MM-DD` format | Unparseable string |
| `description` | Optional | Store `None` if blank after `.strip()` |

> ⚠️ **Security note:** `user_id` always comes from `session["user_id"]` — never from the submitted form data.

---

## Security & Implementation Rules

| Rule | Why |
|------|-----|
| Raw `sqlite3` only via `get_db()` — no ORMs | Project convention |
| `?` placeholders in all queries | Prevents SQL injection |
| Server-side category validation | Never trust client-submitted values |
| `float()` inside `try/except ValueError` | Never assume form input is numeric |
| `datetime.strptime()` inside `try/except ValueError` | Never assume date format |
| CSS variables only — no hardcoded hex | Theme consistency |
| No inline styles | Project convention |
| All templates extend `base.html` | Project convention |

---

## Database

No schema changes required. The `expenses` table already has all needed columns:

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-assigned |
| `user_id` | INTEGER FK | From `session["user_id"]` |
| `amount` | REAL | Positive float |
| `category` | TEXT | One of 7 fixed values |
| `date` | TEXT | ISO format `YYYY-MM-DD` |
| `description` | TEXT | Nullable |
| `created_at` | TIMESTAMP | Auto-assigned by DB |

---

## Definition of Done

- [ ] `GET /expenses/add` while **logged out** → redirects to `/login`
- [ ] `GET /expenses/add` while **logged in** → renders form with all 4 fields
- [ ] Date field defaults to **today's date** on page load
- [ ] Valid form submission → row inserted → redirect to `/profile`
- [ ] New expense **appears immediately** on profile page after redirect
- [ ] Non-numeric amount (e.g. `"abc"`) → error shown, other fields preserved
- [ ] Amount `0` or negative → error shown
- [ ] Invalid date string → error shown
- [ ] Category not in allowed list → error shown
- [ ] Empty description → saved as `NULL` in database
- [ ] "Back to profile" link works without errors

---

## Quick Reference

```
Trackify/
├── app.py                      ← modify: replace stub route
└── templates/
    └── expenses.html ← create: new template
```

---

*Step 7 of Trackify · No new dependencies · No schema changes*