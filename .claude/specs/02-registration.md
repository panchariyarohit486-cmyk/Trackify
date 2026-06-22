# Spec: Registration

## Overview
This step wires up the registration form so new users can create an account. The `GET /register` route and `register.html` template already exist; this step adds the `POST /register` handler that validates the submitted form, checks for duplicate emails, hashes the password with werkzeug, inserts the new user into the `users` table, and redirects to the login page on success. It also sets `app.secret_key` so Flask can use flash messages to carry a success notice across the redirect.

## Depends on
- Step 01 — Database setup (`get_db`, `init_db`, `seed_db` must be working and the `users` table must exist)

## Routes
- `POST /register` — process registration form, create user, redirect to `/login` — public

## Database changes
No database changes. The `users` table (`id`, `name`, `email`, `password_hash`, `created_at`) already exists from Step 01.

## Templates
- **Create:** none
- **Modify:**
  - `templates/register.html` — already renders `{{ error }}`; add `value="{{ name }}"` and `value="{{ email }}"` to inputs so field values are preserved when the form is re-rendered after a validation error
  - `templates/login.html` — add a `{% if success %}` block at the top of the form card to display the flash-style success message passed via query string or template variable after successful registration

## Files to change
- `app.py` — add `secret_key`; import `request`, `redirect`, `url_for`, `flash`, `get_flashed_messages` from flask; import `generate_password_hash` from `werkzeug.security`; add `POST` method to the `/register` route and implement the handler logic

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- `app.secret_key` must be set before any `flash()` call; use a hard-coded dev string (e.g. `"dev-secret-key"`) — a future step will move it to an env var
- Validation order: (1) all fields present, (2) password ≥ 8 characters, (3) email not already registered
- On any validation failure, re-render `register.html` with `error=<message>`, `name=<submitted name>`, and `email=<submitted email>` so the user does not have to retype everything
- On success, flash a message ("Account created — please sign in.") and `redirect(url_for('login'))`
- Catch `sqlite3.IntegrityError` as the duplicate-email guard (UNIQUE constraint), not a manual SELECT-then-INSERT

## Definition of done
- [ ] Submitting the form with all fields blank shows an error message on the page without redirecting
- [ ] Submitting with a password shorter than 8 characters shows a validation error
- [ ] Submitting a duplicate email shows "Email already registered" (or similar) without a 500 error
- [ ] Submitting valid unique details creates a new row in the `users` table (verifiable via SQLite browser or `sqlite3 database/trackify.db "SELECT * FROM users;"`)
- [ ] After successful registration the browser redirects to `/login`
- [ ] A success message is visible on the login page after redirect
- [ ] The registration form preserves the submitted name and email values when re-shown after a validation error
- [ ] The app starts and all existing routes still work (no import errors)
