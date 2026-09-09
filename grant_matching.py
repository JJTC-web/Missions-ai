"""
AI-assisted funding-opportunity matching for a specific org. Uses Claude
with the web search tool to find real, currently open grants relevant to
an org's mission and region, and returns them already shaped as a Guided
Resources JSON import (the same format the admin funding-import textarea
already accepts) so the result can be handed straight to
needs_assessment_db.import_funding_resources() for a human admin to
review and prune, mirroring the existing region_research.py pattern.
"""

import json

import anthropic

MODEL = "claude-opus-5"

MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["id", "label"],
                "additionalProperties": False,
            },
        },
        "resources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "A short, stable slug for this opportunity, e.g. 'usda-community-facilities-2026'"},
                    "title": {"type": "string"},
                    "funder": {"type": "string"},
                    "category": {"type": "string", "description": "Must match one of the categories[].id values"},
                    "region": {"type": "string", "description": "The geography this opportunity actually covers"},
                    "amountRange": {"type": "string"},
                    "applicationWindow": {
                        "type": "object",
                        "properties": {
                            "opens": {"type": "string"},
                            "closes": {"type": "string"},
                            "notes": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                    "status": {"type": "string", "description": "e.g. 'Open', 'Rolling', 'Opens soon'"},
                    "description": {"type": "string"},
                    "sourceUrl": {"type": "string", "description": "A real URL where this opportunity is published"},
                    "eligibilityNote": {"type": "string"},
                },
                "required": ["id", "title", "funder", "category", "description", "sourceUrl"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["categories", "resources"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are a grant researcher finding real, currently relevant funding "
    "opportunities for a specific nonprofit or church, to support real "
    "funding decisions. Use web search to find current, real, citable "
    "grants and funding programs -- never invent a funder, amount, "
    "deadline, or URL, and never guess at a detail you didn't actually "
    "find. Every resource must include a real, working source URL where "
    "the opportunity is actually published. Prefer opportunities that are "
    "currently open or opening soon over ones with passed deadlines. If "
    "you cannot find enough real matches, return fewer results rather "
    "than inventing ones. Group results into a small number of sensible "
    "categories (e.g. 'capital', 'operations', 'program')."
)


def match_funding_opportunities(org, region):
    """Calls Claude with web search to find real funding opportunities
    matching an org's mission and region.

    Returns a dict shaped as a Guided Resources JSON import
    ({"categories": [...], "resources": [...]}), ready to pass to
    needs_assessment_db.import_funding_resources(org_id, data).

    Raises on API/network failure -- callers should catch and surface the
    error, since this depends on an external service and a configured
    ANTHROPIC_API_KEY.
    """
    region_label = f"{region['city']}, {region['state']}" if region else "an unspecified region"
    mission = org.get("mission") or "not specified"

    prompt = (
        f"Find real, currently open (or opening soon) grant and funding "
        f"opportunities for this organization:\n\n"
        f"Organization: {org['name']}\n"
        f"Region: {region_label}\n"
        f"Mission: {mission}\n\n"
        f"Search for grants, foundation funding, or government programs this "
        f"specific organization would actually be eligible to apply for, "
        f"given its mission and location. Include the real amount range, "
        f"application window, and a working source URL for each. Aim for "
        f"5-10 well-matched results; fewer real matches is better than "
        f"padding with irrelevant ones."
    )

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20260209", "name": "web_search"}],
        output_config={"format": {"type": "json_schema", "schema": MATCH_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )

    text_blocks = [block.text for block in response.content if block.type == "text"]
    if not text_blocks:
        raise RuntimeError("Claude returned no text response for funding match")
    return json.loads(text_blocks[-1])
