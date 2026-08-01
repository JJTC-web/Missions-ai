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
            gaps_json TEXT NOT NULL,
            submitted_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def save_submission(submission_id, org_name, contact_name, contact_email, answers, score, gaps, submitted_at):
    conn = get_db()
    conn.execute(
        "INSERT INTO submissions "
        "(id, org_name, contact_name, contact_email, answers_json, score, gaps_json, submitted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            submission_id,
            org_name,
            contact_name,
            contact_email,
            json.dumps(answers),
            score,
            json.dumps(gaps),
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
        "gaps": json.loads(row["gaps_json"]),
        "submitted_at": row["submitted_at"],
    }
