import json
import os
import sqlite3
from datetime import timedelta
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
    id_type = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS action_items (
            id {id_type},
            submission_id TEXT NOT NULL REFERENCES submissions(id),
            area TEXT NOT NULL,
            step_text TEXT NOT NULL,
            due_date TEXT,
            is_complete INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    cur.close()
    conn.close()


def create_action_items(submission_id, plan, submitted_at):
    """Flattens an action plan's per-area steps into dated checklist rows.

    due_in_days on each step is an offset from submitted_at; stored as an
    absolute ISO date so it renders as a real calendar date later.
    """
    conn = get_db()
    cur = conn.cursor()
    sort_order = 0
    for area_plan in plan:
        area = area_plan["area"]
        for step in area_plan["action_steps"]:
            due_in_days = step.get("due_in_days")
            due_date = None
            if isinstance(due_in_days, int):
                due_date = (submitted_at + timedelta(days=due_in_days)).date().isoformat()
            cur.execute(
                f"INSERT INTO action_items (submission_id, area, step_text, due_date, is_complete, sort_order) "
                f"VALUES ({PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, {PLACEHOLDER}, 0, {PLACEHOLDER})",
                (submission_id, area, step["text"], due_date, sort_order),
            )
            sort_order += 1
    conn.commit()
    cur.close()
    conn.close()


def list_action_items(submission_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, area, step_text, due_date, is_complete FROM action_items "
        f"WHERE submission_id = {PLACEHOLDER} ORDER BY sort_order",
        (submission_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": row[0],
            "area": row[1],
            "step_text": row[2],
            "due_date": row[3],
            "is_complete": bool(row[4]),
        }
        for row in rows
    ]


def toggle_action_item(item_id, submission_id):
    """Flips is_complete for an item, scoped to submission_id so a stray/guessed
    item id from a different submission can't be toggled. Returns True if a row
    was updated."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT is_complete FROM action_items "
        f"WHERE id = {PLACEHOLDER} AND submission_id = {PLACEHOLDER}",
        (item_id, submission_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return False
    new_value = 0 if row[0] else 1
    cur.execute(
        f"UPDATE action_items SET is_complete = {PLACEHOLDER} WHERE id = {PLACEHOLDER}",
        (new_value, item_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return True


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


def list_submissions():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, org_name, score, submitted_at FROM submissions ORDER BY submitted_at DESC"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": row[0], "org_name": row[1], "score": row[2], "submitted_at": row[3]}
        for row in rows
    ]
