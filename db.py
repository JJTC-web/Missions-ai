import json
import os
import sqlite3
from urllib.parse import unquote, urlparse

DATABASE_URL = os.environ.get("DATABASE_URL")
SQLITE_PATH = os.environ.get("DATABASE_PATH", "missionos.db")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    # Pure-Python driver (no compiled libpq dependency) so it can't hit the
    # "libpq.so.5 not found" class of error some minimal container runtimes
    # produce with psycopg2-binary after a multi-stage build.
    import pg8000.dbapi as pg8000

PLACEHOLDER = "%s" if USE_POSTGRES else "?"


def get_db():
    if USE_POSTGRES:
        parsed = urlparse(DATABASE_URL)
        return pg8000.connect(
            user=unquote(parsed.username) if parsed.username else None,
            password=unquote(parsed.password) if parsed.password else None,
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path.lstrip("/"),
        )
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
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
    cur.close()
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
    cur = conn.cursor()
    placeholders = ", ".join([PLACEHOLDER] * 11)
    cur.execute(
        "INSERT INTO submissions "
        "(id, org_name, contact_name, contact_email, answers_json, score, breakdown_json, "
        "gaps_json, action_plan_json, action_plan_error, submitted_at) "
        f"VALUES ({placeholders})",
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
    cur.close()
    conn.close()


def get_submission(submission_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, org_name, contact_name, contact_email, answers_json, score, "
        "breakdown_json, gaps_json, action_plan_json, action_plan_error, submitted_at "
        f"FROM submissions WHERE id = {PLACEHOLDER}",
        (submission_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "org_name": row[1],
        "contact_name": row[2],
        "contact_email": row[3],
        "answers": json.loads(row[4]),
        "score": row[5],
        "breakdown": json.loads(row[6]),
        "gaps": json.loads(row[7]),
        "action_plan": json.loads(row[8]) if row[8] else None,
        "action_plan_error": row[9],
        "submitted_at": row[10],
    }
