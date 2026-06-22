# Spec: Login and Logout

## Overview
This step makes authentication functional. The `GET /login` route and `login.html` template already exist; this step adds the `POST /login` handler that verifies credentials with werkzeug, writes `session['user_id']` on success, and redirects to the profile page. It also implements `GET /logout` (currently a stub) to clear the session and redirect to the landing page. A `login_required` helper is introduced so future protected routes can be guarded in one line. The navbar in `base.html` is updated to reflect the logged-in/logged-out state.

## Depends on
- Step 01 — Database setup (`get_db`, `users` table must exist with `password_hash` column)
- Step 02 — Registration (a real user account must exist to log in with; flash messages from registration must appear on the login page)

## Routes
- `POST /login` — verify credentials, set session, redirect to `/profile` on success — public
- `GET /logout` — clear session, redirect to `/` — logged-in (safe to call when already logged out; just redirects)

## Database changes
No database changes. The `users` table already has all required columns.

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html` — add `POST` form action; show `{{ error }}` on failed login; show flashed success message from registration (already redirected here with a flash); preserve submitted email on re-render with `value="{{ email }}"`
  - `templates/base.html` — update navbar: when `session.user_id` is set show the user's name and a "Sign out" link (`/logout`); otherwise show "Sign in" (`/login`) and "Get started" (`/register`) links

## Files to change
- `app.py` — import `session`, `check_password_hash` (werkzeug); add `POST` method to `/login` route and implement handler; implement `/logout` route; add a `login_required` helper function

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting in SQL
- Passwords verified with `werkzeug.security.check_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use Flask's built-in `session` (already backed by `app.secret_key = "dev-secret-key"`); do not add Flask-Login
- `login_required` must be a plain decorator that checks `session.get('user_id')`; if not set, flash "Please sign in to continue." and redirect to `url_for('login')`
- Login handler validation order: (1) both fields present, (2) user exists by email (SELECT from users), (3) `check_password_hash` passes — show the same generic error "Invalid email or password." for both steps 2 and 3 to avoid user enumeration
- On successful login, store `session['user_id']` and `session['user_name']`; redirect to `url_for('profile')`
- On failed login, re-render `login.html` with `error=<message>` and `email=<submitted email>` so the user does not retype their address
- `/logout` must call `session.clear()`, then `redirect(url_for('landing'))`
- The navbar conditional must use `session.get('user_id')` — Jinja2 has access to `session` automatically via Flask's template context

## Definition of done
- [ ] `GET /login` renders the login form (unchanged behaviour)
- [ ] Submitting the login form with empty fields shows an inline error without redirecting
- [ ] Submitting with a wrong email or wrong password shows "Invalid email or password." — same message for both cases
- [ ] Submitting valid credentials (`demo@trackify.com` / `demo123`) sets the session and redirects to `/profile`
- [ ] After login, the navbar shows the user's name and a "Sign out" link instead of "Sign in" / "Get started"
- [ ] Visiting `/logout` clears the session and redirects to the landing page
- [ ] After logout, the navbar reverts to "Sign in" / "Get started"
- [ ] Visiting a `login_required` route while logged out redirects to `/login` with a flash message
- [ ] A flash success message from registration ("Account created — please sign in.") is visible on the login page after redirect
- [ ] The app starts and all existing routes still work (no import errors)
