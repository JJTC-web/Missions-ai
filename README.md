# MissionOS AI

Helping nonprofits build stronger organizations before they build bigger programs.

MissionOS AI is a Flask app that walks a nonprofit through a multi-step
Organizational Health Assessment covering:

- Governance
- Financial Readiness (weighted 2x)
- Volunteer Management
- Project Planning
- Compliance Basics (weighted 2x)

Each submission is timestamped and stored in Postgres (falls back to a local
SQLite file if `DATABASE_URL` isn't set, for easy local development). After
submitting, the org sees a results page with:

- A weighted readiness score out of 100 (financial readiness and compliance
  basics count roughly double toward the overall score)
- A per-area score breakdown
- A gap list (any area scoring below 80)
- An AI-generated action plan for each gap area — specific action steps, a
  rough timeline, and the resources needed — generated via the Claude API

On submit, the app also emails (via Resend):

1. The full results (score, breakdown, gap list, action plan) to the
   submitter's email address
2. A short notification (org name, score, link to results) to
   `ADMIN_NOTIFICATION_EMAIL`

Both email sends are best-effort — if Resend isn't configured or a send
fails, the submission still saves and the results page still renders; the
failure is only logged.

The Organizational Health Assessment itself requires no login — anyone can
take it. A separate `/dashboard` (login required, admin-only) lists every
submission with org name, score, and submission date, linking into each
full results page. See "Admin Dashboard" below for setup.

## Local development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp env.example .env  # then fill in SECRET_KEY, ANTHROPIC_API_KEY, RESEND_API_KEY
python app.py
```

The app runs at http://localhost:5000. Without `ANTHROPIC_API_KEY` set, the
assessment still works — the results page just shows a message that the
action plan couldn't be generated instead of erroring. Same for
`RESEND_API_KEY` — emails are skipped (and logged) rather than blocking the
submission.

## Email (Resend)

Set these to enable submission emails:

- `RESEND_API_KEY` — from your Resend dashboard
- `RESEND_FROM_EMAIL` — defaults to Resend's shared test sender,
  `onboarding@resend.dev`. That sender has deliverability limits (it may
  only reliably deliver to your own account email until you verify a custom
  sending domain in Resend). For real submitter-facing email, verify a
  domain in Resend and set this to something like
  `MissionOS AI <notifications@yourdomain.org>`.
- `ADMIN_NOTIFICATION_EMAIL` — defaults to `ladyem34@gmail.com`

### Testing email delivery

To confirm both emails actually land in real inboxes without submitting a
full assessment, set `TEST_EMAIL_TOKEN` to any secret string (this route is
disabled unless that's set, so it can't be used as an open email relay),
then visit:

```
https://<your-app>/test-email?token=<TEST_EMAIL_TOKEN>&to=<email-to-receive-the-sample-results-email>
```

This sends a sample results email to `to` (or to `ADMIN_NOTIFICATION_EMAIL`
if `to` is omitted) and the admin notification to
`ADMIN_NOTIFICATION_EMAIL`, then returns a small JSON status of both sends.

## Admin Dashboard

`/dashboard` requires a Supabase login **and** admin status — a valid
Supabase account alone isn't enough. Set these:

- `SUPABASE_URL` — your Supabase project URL
- `SUPABASE_ANON_KEY` — used for the sign-in request itself
- `SUPABASE_SERVICE_ROLE_KEY` — used server-side to check the `admins`
  table, bypassing row-level security (never expose this key to the
  browser)

### One-time Supabase setup

1. **Create at least one Auth user** to log in with, if you don't already
   have one: Supabase dashboard → **Authentication** → **Users** → **Add
   user**, and set an email + password directly (skip the confirmation
   email flow for an admin you're creating yourself).
2. **Create the `admins` table** — Supabase dashboard → **SQL Editor**, run:

   ```sql
   create table if not exists admins (
     email text primary key
   );

   alter table admins enable row level security;

   insert into admins (email) values ('ladyem34@gmail.com');
   ```

   Row-level security with no policies means the table is unreachable via
   the public `anon` key — only the server-side `SUPABASE_SERVICE_ROLE_KEY`
   (which bypasses RLS) can read it, which is what `is_admin()` uses. Add
   more admins later with additional `insert` statements.
3. Make sure the email you inserted into `admins` matches the email of the
   Auth user from step 1 exactly.

### Testing that a non-admin is blocked

1. In Supabase, create a **second** Auth user with a different email (or
   temporarily delete your own email's row from `admins` — see below).
2. Go to `/dashboard`, which redirects to `/dashboard/login` since you're
   not signed in.
3. Sign in with the second account's email and password. You should see the
   flash message **"Your account doesn't have dashboard access."** and stay
   on the login page — not land on `/dashboard`.
4. Confirm directly that you were never granted access: reload
   `/dashboard` in the same browser tab — it redirects back to
   `/dashboard/login` rather than showing submissions.

Alternative without creating a second account: in Supabase's SQL Editor,
run `delete from admins where email = 'your-email@example.com';`, try
logging in with your own account (same blocked behavior above), then
`insert into admins (email) values ('your-email@example.com');` to restore
your access.

## Deployment (Railway)

This app is set up to run the same way most Flask apps run on Railway:

- `requirements.txt` — Python dependencies
- `Procfile` — `web: gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120`
  (the longer timeout gives the Claude API call room to finish before
  gunicorn kills the worker)

Railway detects the Procfile and requirements.txt automatically. Set these
environment variables in the Railway project settings before going to
production:

- `SECRET_KEY` — the app falls back to a dev key otherwise
- `ANTHROPIC_API_KEY` — required for AI action plan generation; without it,
  submissions still save and score, but the action plan section shows a
  friendly fallback message
- `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `ADMIN_NOTIFICATION_EMAIL`,
  `TEST_EMAIL_TOKEN` — see the Email (Resend) section above
- `DATABASE_URL` — add a Postgres database in Railway and reference its
  `DATABASE_URL` on this service (`${{Postgres.DATABASE_URL}}`) so
  submissions persist across redeploys. Without it, the app falls back to a
  local SQLite file that's wiped on every redeploy.
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` — see
  the Admin Dashboard section above
