"""
Prompt template for the Needs Assessment Workbook generator. Produces the
four sections that populate the workbook: Target Areas of Support,
Volunteer Needs Plan, Budget Capture, and Success Framework (logic model).

Field names match the JSON shape the workbook writer expects:
    targetAreas:   category, existingCapacity, severity, capacityGap,
                   recommendedAction, framework
    volunteerNeeds: priorityArea, role, skills, hoursPerVolunteer,
                    volunteersNeeded, channel
    budgetItems:   category, lineItem, priorityArea, estCost,
                   fundingSource, notes
    logicModel:    priorityArea, inputs, activities, outputs, outcomes,
                   impact, cadence

severity/capacityGap and Priority Score/Rank/totals/budget percentages are
computed as spreadsheet formulas by the workbook writer, not by the model.
"""

NEEDS_WORKBOOK_SCHEMA = {
    "type": "object",
    "properties": {
        "targetAreas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "A specific need category, e.g. 'Emergency shelter (women & children)'"},
                    "existingCapacity": {"type": "string", "description": "Summary of existing local capacity for this category, referencing specific providers from the resource directory where relevant, e.g. '1 provider (Example Org)' or 'Not itemized in directory — verify local coverage'"},
                    "severity": {"type": "integer", "description": "1-5 scale: how severe/urgent this need is in the region"},
                    "capacityGap": {"type": "integer", "description": "1-5 scale: how large the gap is between need and existing local capacity"},
                    "recommendedAction": {"type": "string", "description": "A concrete, one-sentence recommendation"},
                    "framework": {"type": "string", "description": "The methodology/framework this assessment draws on, e.g. 'HUD CoC Gap Analysis', 'USDA Household Food Security Module', 'Self-Sufficiency Matrix'"},
                },
                "required": ["category", "existingCapacity", "severity", "capacityGap", "recommendedAction", "framework"],
                "additionalProperties": False,
            },
        },
        "volunteerNeeds": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "priorityArea": {"type": "string", "description": "Must match a targetAreas.category value"},
                    "role": {"type": "string", "description": "The volunteer role title"},
                    "skills": {"type": "string", "description": "Skills or certifications needed for this role"},
                    "hoursPerVolunteer": {"type": "number", "description": "Estimated hours per volunteer per month"},
                    "volunteersNeeded": {"type": "integer", "description": "Number of volunteers needed for this role"},
                    "channel": {"type": "string", "description": "Realistic recruitment channel, e.g. 'Faith community, local colleges'"},
                },
                "required": ["priorityArea", "role", "skills", "hoursPerVolunteer", "volunteersNeeded", "channel"],
                "additionalProperties": False,
            },
        },
        "budgetItems": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["Program", "Admin", "Fundraising"], "description": "Used to compute the program-spend percentage — 'Program' is the only category that counts as program spend"},
                    "lineItem": {"type": "string"},
                    "priorityArea": {"type": "string", "description": "Should match a targetAreas.category value, or 'All priority areas' for shared costs"},
                    "estCost": {"type": "number", "description": "Estimated annual cost in whole dollars"},
                    "fundingSource": {"type": "string", "description": "A realistic target funding source, e.g. 'Local government grant', 'Foundation grant', 'Individual donors'"},
                    "notes": {"type": "string"},
                },
                "required": ["category", "lineItem", "priorityArea", "estCost", "fundingSource", "notes"],
                "additionalProperties": False,
            },
        },
        "logicModel": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "priorityArea": {"type": "string", "description": "Should match a targetAreas.category value"},
                    "inputs": {"type": "string", "description": "Resources needed: funding, staff, partners, volunteers"},
                    "activities": {"type": "string", "description": "What actually happens"},
                    "outputs": {"type": "string", "description": "A countable unit of activity, e.g. '# families sheltered / month'"},
                    "outcomes": {"type": "string", "description": "A measurable near-term change, e.g. '% families moved to transitional housing within 60 days'"},
                    "impact": {"type": "string", "description": "The long-term systemic change this contributes to"},
                    "cadence": {"type": "string", "description": "How often this is measured, e.g. 'Monthly', 'Quarterly'"},
                },
                "required": ["priorityArea", "inputs", "activities", "outputs", "outcomes", "impact", "cadence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["targetAreas", "volunteerNeeds", "budgetItems", "logicModel"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are a community needs and program-design analyst for the nonprofit sector. "
    "Given public need data for a region, a directory of existing local service "
    "providers, and a nonprofit's profile, you produce a prioritized needs "
    "assessment grounded in established nonprofit-sector frameworks: HUD Continuum "
    "of Care gap analysis for housing/shelter categories, the USDA Household Food "
    "Security Module for food access, the Self-Sufficiency Matrix for "
    "employment/income support, AmeriCorps/VolunteerMatch benchmarks for volunteer "
    "role design, and the standard 65/35 program-to-overhead budget benchmark "
    "(Charity Navigator / BBB Wise Giving Alliance). "
    "Prioritize by severity x capacity gap: categories with high unmet need and "
    "thin existing local capacity should score highest. Reference specific "
    "providers from the resource directory in existingCapacity so the plan "
    "doesn't recommend duplicating what already exists. Every priorityArea in "
    "volunteerNeeds, budgetItems, and logicModel must correspond to a category in "
    "targetAreas. Keep every recommendation realistic and actionable for a small "
    "or mid-sized nonprofit — no generic filler."
)


def build_user_prompt(org, region, region_stats, resource_directory):
    region_label = f"{region['city']}, {region['state']}" + (
        f" ({region['county']} County)" if region.get("county") else ""
    )

    stats_lines = "\n".join(
        f"- {s['metric_name']}: {s['value']}"
        + (f" ({s['geography_level']})" if s.get("geography_level") else "")
        + (f" — {s['source']}" if s.get("source") else "")
        for s in region_stats
    ) or "No regional statistics on file."

    directory_lines = "\n".join(
        f"- {d['name']}: {d['services'] or 'services not specified'}, "
        f"serving {d['population_served'] or 'population not specified'}"
        for d in resource_directory
    ) or "No existing providers on file for this region."

    mission_line = f"\nOrg mission: {org['mission']}" if org.get("mission") else ""

    return (
        f"Organization: {org['name']}{mission_line}\n\n"
        f"Region: {region_label}\n\n"
        f"Regional need data:\n{stats_lines}\n\n"
        f"Existing local resource directory:\n{directory_lines}\n\n"
        "Produce a Needs Assessment Workbook with target areas of support, a "
        "volunteer needs plan, a budget capture, and a success framework (logic "
        "model), per the schema."
    )
