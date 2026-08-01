from collections import OrderedDict

SCALE_LABELS = {
    1: "Not in place",
    2: "Just starting",
    3: "Partially in place",
    4: "Mostly in place",
    5: "Fully in place",
}

SECTIONS = OrderedDict(
    [
        (
            "governance",
            {
                "title": "Governance",
                "description": "Board structure, oversight, and decision-making.",
                "questions": [
                    {"id": "governance_board_meets", "text": "Our board meets regularly with documented minutes."},
                    {"id": "governance_bylaws", "text": "We have current, board-approved bylaws and a conflict-of-interest policy."},
                    {"id": "governance_roles", "text": "Board and staff roles and responsibilities are clearly defined."},
                    {"id": "governance_succession", "text": "We have a plan for board and leadership succession."},
                ],
            },
        ),
        (
            "financial_readiness",
            {
                "title": "Financial Readiness",
                "description": "Budgeting, controls, and financial oversight.",
                "questions": [
                    {"id": "financial_budget", "text": "We operate against a board-approved annual budget."},
                    {"id": "financial_controls", "text": "We have internal controls (separation of duties, approvals) over spending."},
                    {"id": "financial_reserves", "text": "We maintain an operating reserve."},
                    {"id": "financial_reporting", "text": "Leadership reviews financial reports at least monthly."},
                ],
            },
        ),
        (
            "volunteer_management",
            {
                "title": "Volunteer Management",
                "description": "Recruiting, onboarding, and supporting volunteers.",
                "questions": [
                    {"id": "volunteer_recruiting", "text": "We have a repeatable process for recruiting volunteers."},
                    {"id": "volunteer_onboarding", "text": "New volunteers go through a defined onboarding and training process."},
                    {"id": "volunteer_tracking", "text": "We track volunteer hours and engagement."},
                    {"id": "volunteer_recognition", "text": "We have a system for recognizing and retaining volunteers."},
                ],
            },
        ),
        (
            "project_planning",
            {
                "title": "Project Planning",
                "description": "Program design, timelines, and delivery.",
                "questions": [
                    {"id": "project_goals", "text": "Programs have clearly defined goals and success metrics."},
                    {"id": "project_timeline", "text": "We use project plans and timelines to manage program delivery."},
                    {"id": "project_risk", "text": "We identify and plan for risks before launching new programs."},
                    {"id": "project_evaluation", "text": "We evaluate program outcomes after completion."},
                ],
            },
        ),
        (
            "compliance_basics",
            {
                "title": "Compliance Basics",
                "description": "Legal, tax, and regulatory fundamentals.",
                "questions": [
                    {"id": "compliance_990", "text": "We file our Form 990 (or applicable return) on time each year."},
                    {"id": "compliance_registrations", "text": "Our state charitable registrations are current in every state we solicit in."},
                    {"id": "compliance_policies", "text": "We have written policies for records retention and whistleblower protection."},
                    {"id": "compliance_insurance", "text": "We carry appropriate insurance (general liability, D&O) for our activities."},
                ],
            },
        ),
    ]
)

SECTION_KEYS = list(SECTIONS.keys())
