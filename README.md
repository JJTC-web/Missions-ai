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
