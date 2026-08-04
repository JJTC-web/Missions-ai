import json

import anthropic

from assessment import SECTIONS

MODEL = "claude-opus-5"

ACTION_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "plans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "area": {"type": "string"},
                    "action_steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "description": "A specific, concrete action step"},
                                "due_in_days": {
                                    "type": "integer",
                                    "description": "Realistic number of days from today for a small nonprofit to complete this step, e.g. 14, 30, 90",
                                },
                            },
                            "required": ["text", "due_in_days"],
                            "additionalProperties": False,
                        },
                    },
                    "timeline": {"type": "string"},
                    "resources_needed": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["area", "action_steps", "timeline", "resources_needed"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["plans"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are an organizational development advisor for small nonprofits. "
    "For each gap area you're given, write a detailed, practical action plan: "
    "specific action steps (concrete, not generic advice), a rough timeline "
    "summary (e.g. 'within 30 days', 'next quarter'), and the resources "
    "needed (people, tools, budget, or training). For each individual action "
    "step, also give a realistic due_in_days estimate (an integer number of "
    "days from today) so steps can be shown on a dated checklist -- order "
    "steps chronologically and give earlier steps smaller due_in_days values. "
    "Keep recommendations realistic for a small nonprofit with limited staff "
    "and budget."
)


def generate_action_plan(org_name, gap_sections, answers):
    """Generate a Claude-authored action plan for each gap area.

    Returns a list of plan dicts (empty if there are no gaps). Raises on
    API/network failure — callers should catch and degrade gracefully, since
    this depends on an external service and a configured ANTHROPIC_API_KEY.
    """
    if not gap_sections:
        return []

    gap_details = []
    for gap in gap_sections:
        section_answers = answers.get(gap["key"], {})
        questions = SECTIONS[gap["key"]]["questions"]
        rated_questions = [
            f"- {q['text']} (rated {section_answers.get(q['id'], '?')}/5)"
            for q in questions
        ]
        gap_details.append(
            f"## {gap['title']} (score: {gap['score']}/100)\n" + "\n".join(rated_questions)
        )

    prompt = (
        f"{org_name} completed a nonprofit Organizational Health Assessment. "
        "The following areas scored as gaps (below 80/100). For each one, "
        "produce an action plan.\n\n" + "\n\n".join(gap_details)
    )

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": ACTION_PLAN_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )

    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)["plans"]
