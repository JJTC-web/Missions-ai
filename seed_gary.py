"""
Seeds the Gary, IN (Lake County) test fixture used to exercise the Needs
Assessment Workbook pipeline end to end. Data pulled from the reference
"MissionOS Community Needs Explorer — Gary, IN" workbook.

Usage:
    python seed_gary.py
"""

import db
import needs_assessment_db as ndb

REGION_STATS = [
    {
        "metric_name": "Poverty rate",
        "value": "33%+",
        "geography_level": "City",
        "source": "City-reported figure; exceeds county/state average",
    },
    {
        "metric_name": "Est. homeless individuals (single night)",
        "value": "272",
        "geography_level": "County",
        "source": "National Alliance to End Homelessness / HUD Point-in-Time count — "
        "not itemized below county level",
    },
    {
        "metric_name": "Food insecurity rate (adults)",
        "value": "42.3%",
        "geography_level": "City",
        "source": "Adults reporting insufficient food or money for food",
    },
    {
        "metric_name": "Regional food insecurity",
        "value": "~1 in 7 residents",
        "geography_level": "County/Region",
        "source": "Broader Lake County & regional estimate",
    },
]

RESOURCE_DIRECTORY = [
    {
        "name": "Calumet Township Multipurpose Center",
        "address": "1900 W. 41st Avenue, Gary, IN",
        "services": "Emergency shelter",
        "population_served": "Men, women, children",
        "phone": "219-981-4020",
    },
    {
        "name": "Lighthouse of Hope",
        "address": "4620 W 7th Ave, Gary, IN 46406",
        "services": "Transitional & emergency shelter",
        "population_served": "Men",
        "phone": "219-883-0361",
    },
    {
        "name": "Brother's Keeper",
        "address": "2120 Broadway, Gary, IN",
        "services": "Emergency shelter",
        "population_served": "Men",
        "phone": "219-882-4459",
    },
    {
        "name": "Gary Commission for Women — The Ark",
        "address": "Gary, IN 46402",
        "services": "Transitional housing",
        "population_served": "Women & children",
        "phone": "219-883-4155",
    },
    {
        "name": "Gary Commission for Women — The Rainbow",
        "address": "Gary, IN 46402",
        "services": "Domestic violence shelter",
        "population_served": "Women & children",
        "phone": "219-883-4155",
    },
]


def find_region(city, state):
    for region in ndb.list_regions():
        if region["city"] == city and region["state"] == state:
            return region
    return None


def find_org(name):
    for org in ndb.list_orgs():
        if org["name"] == name:
            return org
    return None


def seed():
    db.init_db()
    ndb.init_needs_assessment_tables()

    region = find_region("Gary", "IN")
    if region:
        region_id = region["id"]
        print(f"Region already exists (id={region_id}), reusing it.")
    else:
        region_id = ndb.create_region("Gary", "Lake", "IN", coc_region=None)
        print(f"Created region id={region_id}: Gary, Lake County, IN")

        for stat in REGION_STATS:
            ndb.add_region_stat(
                region_id,
                stat["metric_name"],
                stat["value"],
                geography_level=stat["geography_level"],
                source=stat["source"],
            )
        print(f"Added {len(REGION_STATS)} region_stats rows")

        for entry in RESOURCE_DIRECTORY:
            ndb.add_resource_directory_entry(
                region_id,
                entry["name"],
                address=entry["address"],
                services=entry["services"],
                population_served=entry["population_served"],
                phone=entry["phone"],
            )
        print(f"Added {len(RESOURCE_DIRECTORY)} resource_directory rows")

    org_name = "Example Nonprofit (Test)"
    org = find_org(org_name)
    if org:
        org_id = org["id"]
        print(f"Org already exists (id={org_id}), reusing it.")
    else:
        org_id = ndb.create_org(
            org_name,
            region_id,
            contact_name="Test Contact",
            contact_email="test@example.org",
            mission="Test fixture org for exercising the Needs Assessment Workbook pipeline.",
        )
        print(f"Created org id={org_id}: {org_name}")

    return region_id, org_id


if __name__ == "__main__":
    region_id, org_id = seed()
    print(f"\nDone. region_id={region_id}, org_id={org_id}")
