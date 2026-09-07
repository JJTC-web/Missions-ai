"""
Client Portal data model:

- client_users: links a Supabase Auth user to an org for portal login
  (the "client" role -- scoped to exactly one organization_id).
- documents: metadata for files an admin uploads and attaches to an org.
  The actual bytes live in Supabase Storage (see document_storage.py);
  this table just tracks what exists and where.

Reuses db.py's connection handling (same Postgres/SQLite dual support).
"""

import db

ID_TYPE = "SERIAL PRIMARY KEY" if db.USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
TIMESTAMP_DEFAULT = "TIMESTAMP DEFAULT NOW()" if db.USE_POSTGRES else "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
NOW_SQL = "NOW()" if db.USE_POSTGRES else "CURRENT_TIMESTAMP"
P = db.PLACEHOLDER

DOC_TYPES = ("engagement_letter", "rfp_draft", "grant_template", "other")
DOC_TYPE_LABELS = {
    "engagement_letter": "Engagement Letter",
    "rfp_draft": "RFP Draft",
    "grant_template": "Grant Template",
    "other": "Other",
}


def init_portal_tables():
    conn = db.get_db()
    cur = conn.cursor()

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS client_users (
            id {ID_TYPE},
            organization_id INTEGER NOT NULL REFERENCES orgs(id),
            auth_user_id TEXT NOT NULL,
            email TEXT NOT NULL,
            invited_at {TIMESTAMP_DEFAULT},
            activated_at TIMESTAMP
        )
        """
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS documents (
            id {ID_TYPE},
            organization_id INTEGER NOT NULL REFERENCES orgs(id),
            file_name TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            doc_type TEXT NOT NULL DEFAULT 'other',
            uploaded_by TEXT,
            uploaded_at {TIMESTAMP_DEFAULT}
        )
        """
    )

    conn.commit()
    cur.close()
    conn.close()


# --- client_users --------------------------------------------------------

def upsert_client_user(organization_id, auth_user_id, email):
    """Creates or updates the client_users row for this org+email, keyed by
    (organization_id, email) so re-inviting reuses the row instead of
    creating a duplicate."""
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id FROM client_users WHERE organization_id = {P} AND email = {P}",
        (organization_id, email),
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            f"UPDATE client_users SET auth_user_id = {P} WHERE id = {P}",
            (auth_user_id, existing[0]),
        )
    else:
        cur.execute(
            f"INSERT INTO client_users (organization_id, auth_user_id, email) VALUES ({P}, {P}, {P})",
            (organization_id, auth_user_id, email),
        )
    conn.commit()
    cur.close()
    conn.close()


def get_client_membership(email):
    """Returns {organization_id, activated_at} for a client email, or None
    if that email has no portal access. This is the row that scopes a
    logged-in client to exactly one org's data."""
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT organization_id, activated_at FROM client_users WHERE email = {P}",
        (email,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return {"organization_id": row[0], "activated_at": row[1]}


def mark_activated(email):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE client_users SET activated_at = {NOW_SQL} WHERE email = {P} AND activated_at IS NULL",
        (email,),
    )
    conn.commit()
    cur.close()
    conn.close()


# --- documents -------------------------------------------------------------

def create_document(organization_id, file_name, storage_path, doc_type, uploaded_by):
    conn = db.get_db()
    cur = conn.cursor()
    doc_id = _insert_returning_id(
        cur,
        f"INSERT INTO documents (organization_id, file_name, storage_path, doc_type, uploaded_by) "
        f"VALUES ({P}, {P}, {P}, {P}, {P})",
        (organization_id, file_name, storage_path, doc_type, uploaded_by),
    )
    conn.commit()
    cur.close()
    conn.close()
    return doc_id


def list_documents(organization_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, file_name, storage_path, doc_type, uploaded_by, uploaded_at "
        f"FROM documents WHERE organization_id = {P} ORDER BY uploaded_at DESC",
        (organization_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": r[0],
            "file_name": r[1],
            "storage_path": r[2],
            "doc_type": r[3],
            "uploaded_by": r[4],
            "uploaded_at": str(r[5]),
        }
        for r in rows
    ]


def get_document(document_id, organization_id):
    """Scoped lookup -- returns None if the doc doesn't belong to this org,
    so a guessed document id from another org's portal can't be fetched."""
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, file_name, storage_path, doc_type, uploaded_by, uploaded_at "
        f"FROM documents WHERE id = {P} AND organization_id = {P}",
        (document_id, organization_id),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "file_name": row[1],
        "storage_path": row[2],
        "doc_type": row[3],
        "uploaded_by": row[4],
        "uploaded_at": str(row[5]),
    }


# --- helpers -----------------------------------------------------------

def _insert_returning_id(cur, sql, params):
    if db.USE_POSTGRES:
        cur.execute(sql + " RETURNING id", params)
        return cur.fetchone()[0]
    cur.execute(sql, params)
    return cur.lastrowid
