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
    _add_column_if_missing(cur, "documents", "signed_at", "TIMESTAMP")
    _add_column_if_missing(cur, "documents", "signed_by_name", "TEXT")

    conn.commit()
    cur.close()
    conn.close()


def _add_column_if_missing(cur, table, column, coltype):
    if db.USE_POSTGRES:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}")
        return
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


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
        f"SELECT id, file_name, storage_path, doc_type, uploaded_by, uploaded_at, "
        f"signed_at, signed_by_name "
        f"FROM documents WHERE organization_id = {P} ORDER BY uploaded_at DESC",
        (organization_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [_document_row_to_dict(r) for r in rows]


def get_document(document_id, organization_id):
    """Scoped lookup -- returns None if the doc doesn't belong to this org,
    so a guessed document id from another org's portal can't be fetched."""
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, file_name, storage_path, doc_type, uploaded_by, uploaded_at, "
        f"signed_at, signed_by_name "
        f"FROM documents WHERE id = {P} AND organization_id = {P}",
        (document_id, organization_id),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return _document_row_to_dict(row)


def _document_row_to_dict(row):
    return {
        "id": row[0],
        "file_name": row[1],
        "storage_path": row[2],
        "doc_type": row[3],
        "uploaded_by": row[4],
        "uploaded_at": str(row[5]),
        "signed_at": str(row[6]) if row[6] is not None else None,
        "signed_by_name": row[7],
    }


def sign_document(document_id, organization_id, signed_by_name):
    """Marks a document as signed by the client, scoped to their own org so
    a guessed document id from another org can't be signed. Returns True
    if a row was updated (False if it doesn't belong to this org, or was
    already signed)."""
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE documents SET signed_at = {NOW_SQL}, signed_by_name = {P} "
        f"WHERE id = {P} AND organization_id = {P} AND signed_at IS NULL",
        (signed_by_name, document_id, organization_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    cur.close()
    conn.close()
    return updated


# --- helpers -----------------------------------------------------------

def _insert_returning_id(cur, sql, params):
    if db.USE_POSTGRES:
        cur.execute(sql + " RETURNING id", params)
        return cur.fetchone()[0]
    cur.execute(sql, params)
    return cur.lastrowid
