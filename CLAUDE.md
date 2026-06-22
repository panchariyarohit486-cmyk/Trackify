# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Trackify** is a Flask-based expense tracker web application. It uses SQLite for persistence, Jinja2 for server-side templates, and vanilla CSS/JS. The project is structured as a step-by-step build — many routes in `app.py` are stubs (returning plain strings) that are meant to be filled in as features are implemented.

## Setup & Running

```bash
# Activate the virtual environment (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the development server (port 5001)
python app.py
```

## Testing

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_auth.py

# Run a single test function
pytest tests/test_auth.py::test_login_success
```

No test files exist yet — `pytest` and `pytest-flask` are installed and ready for use.

## Architecture

### Entry Point

`app.py` is the sole Flask application file. It creates the `app` instance and registers all routes. Routes marked `"coming in Step N"` are intentional stubs.

### Database Layer

`database/db.py` must expose three functions (currently a placeholder):
- `get_db()` — returns a SQLite connection with `row_factory` set and foreign keys enabled
- `init_db()` — creates all tables via `CREATE TABLE IF NOT EXISTS`
- `seed_db()` — inserts sample data for development

`database/__init__.py` is empty. Import from `database.db` directly.

### Templates

All pages extend `templates/base.html`, which provides the navbar (Sign in / Get started links), footer (Terms + Privacy links), and loads `static/css/style.css` and `static/js/main.js`. Use `{% block content %}` for page body and `{% block title %}` for the page title.

### Static Assets

- `static/css/style.css` — all styles; uses Google Fonts (DM Serif Display + DM Sans)
- `static/js/main.js` — vanilla JS; currently only wires up the "How it Works" video modal on the landing page (toggled via `#how-modal`, `#how-it-works-btn`, `#modal-close`)
