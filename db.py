import json
import os
import sqlite3

DB_PATH = os.environ.get("DATABASE_PATH", "missionos.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            org_name TEXT NOT NULL,
            contact_name TEXT,
            contact_email TEXT,
            answers_json TEXT NOT NULL,
            score INTEGER NOT NULL,
            breakdown_json TEXT NOT NULL,
            gaps_json TEXT NOT NULL,
            action_plan_json TEXT,
            action_plan_error TEXT,
            submitted_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def save_submission(
    submission_id,
    org_name,
    contact_name,
    contact_email,
    answers,
    score,
    breakdown,
    gaps,
    action_plan,
    action_plan_error,
    submitted_at,
):
    conn = get_db()
    conn.execute(
        "INSERT INTO submissions "
        "(id, org_name, contact_name, contact_email, answers_json, score, breakdown_json, "
        "gaps_json, action_plan_json, action_plan_error, submitted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            submission_id,
            org_name,
            contact_name,
            contact_email,
            json.dumps(answers),
            score,
            json.dumps(breakdown),
            json.dumps(gaps),
            json.dumps(action_plan) if action_plan is not None else None,
            action_plan_error,
            submitted_at.isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_submission(submission_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "org_name": row["org_name"],
        "contact_name": row["contact_name"],
        "contact_email": row["contact_email"],
        "answers": json.loads(row["answers_json"]),
        "score": row["score"],
        "breakdown": json.loads(row["breakdown_json"]),
        "gaps": json.loads(row["gaps_json"]),
        "action_plan": json.loads(row["action_plan_json"]) if row["action_plan_json"] else None,
        "action_plan_error": row["action_plan_error"],
        "submitted_at": row["submitted_at"],
    }
