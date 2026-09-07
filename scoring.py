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
