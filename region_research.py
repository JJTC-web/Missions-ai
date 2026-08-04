"""
AI-assisted regional data research. Uses Claude with the web search tool to
find public need statistics and existing service providers for a region.

Results are returned as plain dicts for the caller to store as review
drafts -- this module never writes to region_stats/resource_directory
directly. A human admin approves or rejects each item before it's saved,
since these numbers can inform real funding decisions and must not be
presented as fact without a check.
"""

import json

import anthropic

MODEL = "claude-opus-5"

REGION_RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "stats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "metric_name": {"type": "string", "description": "e.g. 'Poverty rate', 'Est. homeless individuals (single night)', 'Food insecurity rate (adults)'"},
                    "value": {"type": "string"},
                    "geography_level": {"type": "string", "description": "e.g. 'City', 'County', 'County/Region' -- be precise about what geography the figure actually covers"},
                    "source": {"type": "string", "description": "Citation: publisher/report name, and a URL if one was found"},
                },
                "required": ["metric_name", "value", "geography_level", "source"],
                "additionalProperties": False,
            },
        },
        "resources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "address": {"type": "string"},
                    "services": {"type": "string"},
                    "population_served": {"type": "string"},
                    "phone": {"type": "string"},
                    "source": {"type": "string", "description": "Where this listing was found"},
                },
                "required": ["name", "address", "services", "population_served", "phone", "source"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["stats", "resources"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are a research assistant gathering public community-need data and "
    "existing service-provider directories for nonprofits, to support real "
    "funding and program decisions. Use web search to find current, real, "
    "citable figures and organizations -- never invent numbers or "
    "organizations, and never guess at a figure you didn't actually find. "
    "Prefer official/authoritative sources: HUD, U.S. Census Bureau, USDA, "
    "state or county government sites, and established nonprofits like the "
    "National Alliance to End Homelessness. Be precise about what geography "
    "level a figure actually covers -- if you can only find a county-level "
    "number for a city, label it County, not City. For each resource, use "
    "the organization's actual name, address, and phone number as "
    "published; do not fabricate contact details. Every stat and resource "
    "must include a source citation (publisher/report name, and a URL where "
    "available). If you cannot find reliable data for a category, omit it "
    "rather than guessing."
)


def research_region(region):
    """Calls Claude with web search to draft stats + resources for a region.

    Returns {"stats": [...], "resources": [...]}. Raises on API/network
    failure -- callers should catch and surface the error, since this
    depends on an external service and a configured ANTHROPIC_API_KEY.
    """
    region_label = f"{region['city']}, {region['state']}"
    if region.get("county"):
        region_label += f" ({region['county']} County)"

    prompt = (
        f"Research {region_label}.\n\n"
        "1. Find regional need statistics: poverty rate, homelessness counts "
        "(note whether a figure is city- or county-level), food insecurity "
        "rate, and any other clearly relevant community-need metrics you can "
        "find real data for.\n"
        "2. Find existing nonprofit/service-provider organizations serving "
        "this area (shelters, food pantries, housing assistance, etc.) with "
        "their address and phone number if publicly listed.\n\n"
        "Cite a real, specific source for every item."
    )

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20260209", "name": "web_search"}],
        output_config={"format": {"type": "json_schema", "schema": REGION_RESEARCH_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )

    text_blocks = [block.text for block in response.content if block.type == "text"]
    if not text_blocks:
        raise RuntimeError("Claude returned no text response for region research")
    return json.loads(text_blocks[-1])
