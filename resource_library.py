"""Downloadable resource templates offered to orgs, gated by subscription tier.

This is a fixed catalog (not per-org data like funding_resources), so it's
kept as a plain list rather than a database table. Files live in
resource_library/files/ rather than static/ so the tier check in the
download route in app.py is the only way to reach them -- putting them
under static/ would let anyone fetch the URL directly and skip the gate.
"""

RESOURCES = [
    {
        "id": "grant-tracker-2026",
        "title": "2026 Grant Tracker",
        "description": (
            "Spreadsheet tracker of active IL/WI capital and operations "
            "grants for 2026, with deadlines, partnership requirements, "
            "and follow-up dates."
        ),
        "filename": "2026_Grant_Tracker_Template.xlsx",
        "required_tier": "tier2",
    },
    {
        "id": "grants-for-women-guide",
        "title": "Grants for Women — Funding Guide",
        "description": (
            "Directory of grant programs for women-led organizations and "
            "women-serving programs, with amounts, eligibility, and "
            "deadlines."
        ),
        "filename": "Grants_for_Women_Funding_Guide.pdf",
        "required_tier": "tier2",
    },
    {
        "id": "grant-budget-template",
        "title": "Grant Budget Template",
        "description": (
            "Side-by-side grant budget and budget justification template "
            "for grant applications."
        ),
        "filename": "Grant_Budget_Template.xlsx",
        "required_tier": "tier3",
    },
    {
        "id": "church-funding-toolkit",
        "title": "Church Funding Toolkit",
        "description": (
            "Grant and loan resources, a 30-day funding calendar, project "
            "budget template, and revenue stream worksheet for church "
            "capital projects."
        ),
        "filename": "Church_Funding_Toolkit.xlsx",
        "required_tier": "tier3",
    },
]


def get_resource(resource_id):
    for r in RESOURCES:
        if r["id"] == resource_id:
            return r
    return None
