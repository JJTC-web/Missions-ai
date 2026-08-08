"""Subscription tier ordering, shared by any feature that needs to gate
content by an org's tier (e.g. Funding Opportunities requiring Tier 3).

Tiers are tracked manually on orgs.tier (see needs_assessment_db.py) --
there's no billing integration yet. This module only answers "does this
org's tier meet the bar for this feature" for whatever surface ends up
enforcing it (today: an admin-facing preview badge; later: a real
org-facing portal).
"""

TIER_ORDER = ["free", "tier1", "tier2", "tier3"]
TIER_LABELS = {"free": "Free", "tier1": "Tier 1", "tier2": "Tier 2", "tier3": "Tier 3"}


def tier_rank(tier):
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return 0


def tier_meets(org_tier, required_tier):
    """True if org_tier is at or above required_tier."""
    return tier_rank(org_tier) >= tier_rank(required_tier)
