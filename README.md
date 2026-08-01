# MissionOS AI

Helping nonprofits build stronger organizations before they build bigger programs.

MissionOS AI is a Flask app that walks a nonprofit through a multi-step
Organizational Health Assessment covering:

- Governance
- Financial Readiness
- Volunteer Management
- Project Planning
- Compliance Basics

Each submission is timestamped and stored in SQLite. After submitting, the
org sees a results page with a readiness score and a gap list. The current
scoring is a simple placeholder (a plain average of answers) — it will be
replaced by a real scoring engine and AI-generated action plan next.

## Local development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp env.example .env  # then edit SECRET_KEY if you want
python app.py
```

The app runs at http://localhost:5000.

## Deployment (Railway)

This app is set up to run the same way most Flask apps run on Railway:

- `requirements.txt` — Python dependencies
- `Procfile` — `web: gunicorn app:app --bind 0.0.0.0:$PORT`

Railway detects the Procfile and requirements.txt automatically. Set a
`SECRET_KEY` environment variable in the Railway project settings before
going to production (the app falls back to a dev key otherwise).

The SQLite database file is written to local disk, which is fine for a demo
but is not persistent across Railway redeploys — swap in a hosted database
before this goes to real users.
