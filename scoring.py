from assessment import SECTIONS, SECTION_KEYS

GAP_THRESHOLD = 80
CRITICAL_THRESHOLD = 50


def severity_for_score(score):
    """Traffic-light severity for one area's score:
    "red"    (< 50)  -- tackle these first
    "yellow" (50-79) -- a real gap, approaching risk (deadlines, funding
                        eligibility, etc.), but not the most urgent
    "green"  (80+)   -- good to go, little improvement needed
    """
    if score < CRITICAL_THRESHOLD:
        return "red"
    if score < GAP_THRESHOLD:
        return "yellow"
    return "green"


def compute_score_breakdown(answers):
    """Weighted readiness score out of 100, plus a per-area breakdown.

    Financial readiness and compliance basics carry roughly double the
    weight of governance, volunteer management, and project planning.
    """
    breakdown = []
    weighted_sum = 0
    weight_total = 0

    for key in SECTION_KEYS:
        section = SECTIONS[key]
        section_answers = answers.get(key, {})
        values = list(section_answers.values())
        average = sum(values) / len(values) if values else 0
        section_score = round((average / 5) * 100)
        weight = section["weight"]

        weighted_sum += section_score * weight
        weight_total += weight

        breakdown.append({
            "key": key,
            "title": section["title"],
            "weight": weight,
            "score": section_score,
        })

    overall_score = round(weighted_sum / weight_total) if weight_total else 0
    gaps = [b for b in breakdown if b["score"] < GAP_THRESHOLD]
    return overall_score, breakdown, gaps


def build_gap_view(breakdown, gap_titles, action_plan):
    """Shared enrichment for both the results page and the results email,
    so the two always agree: folds each area's score and traffic-light
    severity into its own action-plan entry (sorted red-first, so
    "tackle these first" is the actual reading order), and splits out
    the non-gap "strong" areas with their own (always green) severity
    tag. Works on copies -- never mutates the caller's breakdown/plan.

    Returns (enriched_action_plan, strong_areas).
    """
    score_by_area = {area["title"]: area["score"] for area in breakdown}

    enriched_plan = [dict(plan) for plan in (action_plan or [])]
    for plan in enriched_plan:
        plan["area_score"] = score_by_area.get(plan["area"])
        plan["severity"] = severity_for_score(plan["area_score"]) if plan["area_score"] is not None else None
    severity_order = {"red": 0, "yellow": 1, "green": 2, None: 3}
    enriched_plan.sort(key=lambda p: severity_order.get(p["severity"], 3))

    strong_areas = [dict(area) for area in breakdown if area["title"] not in gap_titles]
    for area in strong_areas:
        area["severity"] = severity_for_score(area["score"])

    return enriched_plan, strong_areas
