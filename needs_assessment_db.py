"""
Needs Assessment Workbook data model: orgs, regions, region-level stats,
a directory of existing community resources, and generated workbook runs.

Reuses db.py's connection handling (same Postgres/SQLite dual support).
"""

import json

import db

ID_TYPE = "SERIAL PRIMARY KEY" if db.USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
TIMESTAMP_DEFAULT = "TIMESTAMP DEFAULT NOW()" if db.USE_POSTGRES else "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
P = db.PLACEHOLDER


def init_needs_assessment_tables():
    conn = db.get_db()
    cur = conn.cursor()

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS regions (
            id {ID_TYPE},
            city TEXT NOT NULL,
            county TEXT,
            state TEXT NOT NULL,
            coc_region TEXT
        )
        """
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS orgs (
            id {ID_TYPE},
            name TEXT NOT NULL,
            region_id INTEGER REFERENCES regions(id),
            contact_name TEXT,
            contact_email TEXT,
            mission TEXT,
            created_at {TIMESTAMP_DEFAULT}
        )
        """
    )
    _add_column_if_missing(cur, "orgs", "tier", "TEXT DEFAULT 'free'")

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS region_stats (
            id {ID_TYPE},
            region_id INTEGER REFERENCES regions(id),
            metric_name TEXT NOT NULL,
            value TEXT NOT NULL,
            geography_level TEXT,
            source TEXT,
            as_of_date DATE
        )
        """
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS resource_directory (
            id {ID_TYPE},
            org_id INTEGER REFERENCES orgs(id),
            region_id INTEGER REFERENCES regions(id),
            name TEXT NOT NULL,
            address TEXT,
            services TEXT,
            population_served TEXT,
            phone TEXT
        )
        """
    )
    _add_column_if_missing(cur, "resource_directory", "source", "TEXT")

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS needs_runs (
            id {ID_TYPE},
            org_id INTEGER REFERENCES orgs(id),
            region_id INTEGER REFERENCES regions(id),
            created_at {TIMESTAMP_DEFAULT},
            workbook_url TEXT,
            workbook_json TEXT,
            status TEXT DEFAULT 'pending'
        )
        """
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS region_research_drafts (
            id {ID_TYPE},
            region_id INTEGER REFERENCES regions(id),
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at {TIMESTAMP_DEFAULT}
        )
        """
    )

    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS funding_resources (
            id {ID_TYPE},
            org_id INTEGER REFERENCES orgs(id),
            external_id TEXT,
            title TEXT NOT NULL,
            funder TEXT,
            category TEXT,
            category_label TEXT,
            region TEXT,
            amount_range TEXT,
            window_opens DATE,
            window_closes DATE,
            window_notes TEXT,
            funding_pillars_json TEXT,
            status TEXT,
            description TEXT,
            draft_file TEXT,
            source_url TEXT,
            placeholders_json TEXT,
            eligibility_note TEXT,
            required_tier TEXT,
            created_at {TIMESTAMP_DEFAULT}
        )
        """
    )

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


# --- regions ---------------------------------------------------------------

def create_region(city, county, state, coc_region=None):
    conn = db.get_db()
    cur = conn.cursor()
    region_id = _insert_returning_id(
        cur,
        f"INSERT INTO regions (city, county, state, coc_region) VALUES ({P}, {P}, {P}, {P})",
        (city, county, state, coc_region),
    )
    conn.commit()
    cur.close()
    conn.close()
    return region_id


def list_regions():
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, city, county, state, coc_region FROM regions ORDER BY city")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": r[0], "city": r[1], "county": r[2], "state": r[3], "coc_region": r[4]}
        for r in rows
    ]


def get_region(region_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, city, county, state, coc_region FROM regions WHERE id = {P}",
        (region_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "city": row[1], "county": row[2], "state": row[3], "coc_region": row[4]}


# --- orgs --------------------------------------------------------------

def create_org(name, region_id, contact_name=None, contact_email=None, mission=None):
    conn = db.get_db()
    cur = conn.cursor()
    org_id = _insert_returning_id(
        cur,
        f"INSERT INTO orgs (name, region_id, contact_name, contact_email, mission) "
        f"VALUES ({P}, {P}, {P}, {P}, {P})",
        (name, region_id, contact_name, contact_email, mission),
    )
    conn.commit()
    cur.close()
    conn.close()
    return org_id


def list_orgs():
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, region_id, contact_name, contact_email, mission, tier FROM orgs ORDER BY name"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": r[0],
            "name": r[1],
            "region_id": r[2],
            "contact_name": r[3],
            "contact_email": r[4],
            "mission": r[5],
            "tier": r[6] or "free",
        }
        for r in rows
    ]


def get_org(org_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, name, region_id, contact_name, contact_email, mission, tier FROM orgs WHERE id = {P}",
        (org_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "region_id": row[2],
        "contact_name": row[3],
        "contact_email": row[4],
        "mission": row[5],
        "tier": row[6] or "free",
    }


VALID_TIERS = ("free", "tier1", "tier2", "tier3")


def set_org_tier(org_id, tier):
    if tier not in VALID_TIERS:
        raise ValueError(f"Invalid tier: {tier}")
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(f"UPDATE orgs SET tier = {P} WHERE id = {P}", (tier, org_id))
    conn.commit()
    cur.close()
    conn.close()


# --- region_stats --------------------------------------------------------

def add_region_stat(region_id, metric_name, value, geography_level=None, source=None, as_of_date=None):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO region_stats (region_id, metric_name, value, geography_level, source, as_of_date) "
        f"VALUES ({P}, {P}, {P}, {P}, {P}, {P})",
        (region_id, metric_name, value, geography_level, source, as_of_date),
    )
    conn.commit()
    cur.close()
    conn.close()


def list_region_stats(region_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, metric_name, value, geography_level, source, as_of_date "
        f"FROM region_stats WHERE region_id = {P} ORDER BY metric_name",
        (region_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": r[0],
            "metric_name": r[1],
            "value": r[2],
            "geography_level": r[3],
            "source": r[4],
            "as_of_date": str(r[5]) if r[5] is not None else None,
        }
        for r in rows
    ]


# --- resource_directory ---------------------------------------------------

def add_resource_directory_entry(region_id, name, address=None, services=None, population_served=None, phone=None, org_id=None, source=None):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO resource_directory (org_id, region_id, name, address, services, population_served, phone, source) "
        f"VALUES ({P}, {P}, {P}, {P}, {P}, {P}, {P}, {P})",
        (org_id, region_id, name, address, services, population_served, phone, source),
    )
    conn.commit()
    cur.close()
    conn.close()


def list_resource_directory(region_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, org_id, name, address, services, population_served, phone, source "
        f"FROM resource_directory WHERE region_id = {P} ORDER BY name",
        (region_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": r[0],
            "org_id": r[1],
            "name": r[2],
            "address": r[3],
            "services": r[4],
            "population_served": r[5],
            "phone": r[6],
            "source": r[7],
        }
        for r in rows
    ]


# --- needs_runs ------------------------------------------------------------

def create_needs_run(org_id, region_id):
    conn = db.get_db()
    cur = conn.cursor()
    run_id = _insert_returning_id(
        cur,
        f"INSERT INTO needs_runs (org_id, region_id, status) VALUES ({P}, {P}, 'pending')",
        (org_id, region_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return run_id


def complete_needs_run(run_id, workbook_json, workbook_url=None):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE needs_runs SET status = 'complete', workbook_json = {P}, workbook_url = {P} WHERE id = {P}",
        (json.dumps(workbook_json), workbook_url, run_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def fail_needs_run(run_id, error_message):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE needs_runs SET status = {P} WHERE id = {P}",
        (f"failed: {error_message}", run_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_needs_run(run_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, org_id, region_id, created_at, workbook_url, workbook_json, status "
        f"FROM needs_runs WHERE id = {P}",
        (run_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "org_id": row[1],
        "region_id": row[2],
        "created_at": str(row[3]),
        "workbook_url": row[4],
        "workbook_json": json.loads(row[5]) if row[5] else None,
        "status": row[6],
    }


def list_needs_runs_for_org(org_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, created_at, status FROM needs_runs WHERE org_id = {P} ORDER BY created_at DESC",
        (org_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "created_at": str(r[1]), "status": r[2]} for r in rows]


# --- region_research_drafts -------------------------------------------

def create_research_draft(region_id, kind, payload):
    conn = db.get_db()
    cur = conn.cursor()
    draft_id = _insert_returning_id(
        cur,
        f"INSERT INTO region_research_drafts (region_id, kind, payload_json) VALUES ({P}, {P}, {P})",
        (region_id, kind, json.dumps(payload)),
    )
    conn.commit()
    cur.close()
    conn.close()
    return draft_id


def list_research_drafts(region_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, kind, payload_json FROM region_research_drafts "
        f"WHERE region_id = {P} ORDER BY id",
        (region_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "kind": r[1], "payload": json.loads(r[2])} for r in rows]


def get_research_draft(draft_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, region_id, kind, payload_json FROM region_research_drafts WHERE id = {P}",
        (draft_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "region_id": row[1], "kind": row[2], "payload": json.loads(row[3])}


def delete_research_draft(draft_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM region_research_drafts WHERE id = {P}", (draft_id,))
    conn.commit()
    cur.close()
    conn.close()


# --- funding_resources -------------------------------------------------

def import_funding_resources(org_id, data):
    """Upserts a Guided Resources JSON export's resources for one org, keyed
    by (org_id, external_id). Returns (created_count, updated_count).
    """
    category_labels = {c["id"]: c.get("label", c["id"]) for c in data.get("categories", [])}

    conn = db.get_db()
    cur = conn.cursor()
    created = 0
    updated = 0
    for r in data.get("resources", []):
        external_id = r["id"]
        window = r.get("applicationWindow") or {}
        fields = (
            r.get("title"),
            r.get("funder"),
            r.get("category"),
            category_labels.get(r.get("category"), r.get("category")),
            r.get("region"),
            r.get("amountRange"),
            window.get("opens"),
            window.get("closes"),
            window.get("notes"),
            json.dumps(r.get("fundingPillars", [])),
            r.get("status"),
            r.get("description"),
            r.get("draftFile"),
            r.get("sourceUrl"),
            json.dumps(r.get("placeholders", [])),
            r.get("eligibilityNote"),
            r.get("requiredTier"),
        )

        cur.execute(
            f"SELECT id FROM funding_resources WHERE org_id = {P} AND external_id = {P}",
            (org_id, external_id),
        )
        existing = cur.fetchone()

        if existing:
            cur.execute(
                f"""
                UPDATE funding_resources SET
                    title = {P}, funder = {P}, category = {P}, category_label = {P},
                    region = {P}, amount_range = {P}, window_opens = {P}, window_closes = {P},
                    window_notes = {P}, funding_pillars_json = {P}, status = {P}, description = {P},
                    draft_file = {P}, source_url = {P}, placeholders_json = {P}, eligibility_note = {P},
                    required_tier = {P}
                WHERE id = {P}
                """,
                fields + (existing[0],),
            )
            updated += 1
        else:
            cur.execute(
                f"""
                INSERT INTO funding_resources (
                    org_id, external_id, title, funder, category, category_label,
                    region, amount_range, window_opens, window_closes, window_notes,
                    funding_pillars_json, status, description, draft_file, source_url,
                    placeholders_json, eligibility_note, required_tier
                ) VALUES ({P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P})
                """,
                (org_id, external_id) + fields,
            )
            created += 1

    conn.commit()
    cur.close()
    conn.close()
    return created, updated


def list_funding_resources(org_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT id, title, funder, category, category_label, region, amount_range,
               window_opens, window_closes, window_notes, funding_pillars_json, status,
               description, draft_file, source_url, placeholders_json, eligibility_note,
               required_tier
        FROM funding_resources WHERE org_id = {P} ORDER BY category_label, title
        """,
        (org_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": r[0],
            "title": r[1],
            "funder": r[2],
            "category": r[3],
            "category_label": r[4],
            "region": r[5],
            "amount_range": r[6],
            "window_opens": r[7],
            "window_closes": r[8],
            "window_notes": r[9],
            "funding_pillars": json.loads(r[10]) if r[10] else [],
            "status": r[11],
            "description": r[12],
            "draft_file": r[13],
            "source_url": r[14],
            "placeholders": json.loads(r[15]) if r[15] else [],
            "eligibility_note": r[16],
            "required_tier": r[17],
        }
        for r in rows
    ]


def delete_funding_resource(resource_id, org_id):
    conn = db.get_db()
    cur = conn.cursor()
    cur.execute(
        f"DELETE FROM funding_resources WHERE id = {P} AND org_id = {P}",
        (resource_id, org_id),
    )
    conn.commit()
    deleted = cur.rowcount > 0
    cur.close()
    conn.close()
    return deleted


# --- helpers -----------------------------------------------------------

def _insert_returning_id(cur, sql, params):
    if db.USE_POSTGRES:
        cur.execute(sql + " RETURNING id", params)
        return cur.fetchone()[0]
    cur.execute(sql, params)
    return cur.lastrowid
