# MissionOS AI

Helping nonprofits build stronger organizations before they build bigger programs.

MissionOS AI is a Flask app that walks a nonprofit through a multi-step
Organizational Health Assessment covering:

- Governance
- Financial Readiness (weighted 2x)
- Volunteer Management
- Project Planning
- Compliance Basics (weighted 2x)

Each submission is timestamped and stored in SQLite. After submitting, the org
sees a results page with:

- A weighted readiness score out of 100 (financial readiness and compliance
  basics count roughly double toward the overall score)
- A per-area score breakdown
- A gap list (any area scoring below 80)
- An AI-generated action plan for each gap area — specific action steps, a
  rough timeline, and the resources needed — generated via the Claude API

## Local development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp env.example .env  # then edit SECRET_KEY and add your ANTHROPIC_API_KEY
python app.py
```

The app runs at http://localhost:5000. Without `ANTHROPIC_API_KEY` set, the
assessment still works — the results page just shows a message that the
action plan couldn't be generated instead of erroring.

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

The SQLite database file is written to local disk, which is fine for a demo
but is not persistent across Railway redeploys — swap in a hosted database
before this goes to real users.
