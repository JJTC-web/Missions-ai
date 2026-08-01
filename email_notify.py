"""
Resend integration for MissionOS AI submission emails.

Docs: https://resend.com/docs/api-reference/emails/send-email
Auth: header "Authorization: Bearer {RESEND_API_KEY}"

Environment variables:
    RESEND_API_KEY
    RESEND_FROM_EMAIL        (defaults to Resend's onboarding@resend.dev test sender)
    ADMIN_NOTIFICATION_EMAIL (defaults to ladyem34@gmail.com)
"""

import os

import requests

RESEND_API_BASE = "https://api.resend.com"

ADMIN_NOTIFICATION_EMAIL = os.environ.get("ADMIN_NOTIFICATION_EMAIL", "ladyem34@gmail.com")


def _headers():
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not set")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def send_email(to, subject, html):
    from_email = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")
    payload = {
        "from": from_email,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    resp = requests.post(f"{RESEND_API_BASE}/emails", json=payload, headers=_headers(), timeout=15)
    if not resp.ok:
        raise RuntimeError(f"Resend API error {resp.status_code}: {resp.text}")
    return resp.json()


def _breakdown_html(breakdown):
    rows = "".join(
        f"<tr>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #e1ddd3;'>{area['title']}</td>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #e1ddd3;color:#5b6470;'>{area['weight']}&times; weight</td>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #e1ddd3;'><strong>{area['score']}/100</strong></td>"
        f"</tr>"
        for area in breakdown
    )
    return f"<table cellspacing='0' cellpadding='0' style='border-collapse:collapse;width:100%;'>{rows}</table>"


def _gaps_html(gaps):
    if not gaps:
        return "<p>No gap areas flagged &mdash; every area scored 80 or above.</p>"
    items = "".join(f"<li>{g}</li>" for g in gaps)
    return f"<ul>{items}</ul>"


def _action_plan_html(submission):
    if submission.get("action_plan_error"):
        return "<p>We couldn't generate an AI action plan for this submission.</p>"
    if not submission.get("action_plan"):
        return "<p>No action plan needed &mdash; no gap areas were flagged.</p>"

    sections = []
    for plan in submission["action_plan"]:
        steps = "".join(f"<li>{s}</li>" for s in plan["action_steps"])
        resources = "".join(f"<li>{r}</li>" for r in plan["resources_needed"])
        sections.append(
            f"<h3 style='margin-bottom:4px;'>{plan['area']}</h3>"
            f"<p><strong>Timeline:</strong> {plan['timeline']}</p>"
            f"<p><strong>Action Steps</strong></p><ul>{steps}</ul>"
            f"<p><strong>Resources Needed</strong></p><ul>{resources}</ul>"
        )
    return "".join(sections)


def _results_email_html(submission):
    return f"""
    <h1>{submission['org_name']}&rsquo;s Readiness Snapshot</h1>
    <p><strong>Overall Readiness Score:</strong> {submission['score']}/100</p>

    <h2>Score Breakdown</h2>
    {_breakdown_html(submission['breakdown'])}

    <h2>Gap Areas</h2>
    {_gaps_html(submission['gaps'])}

    <h2>AI-Generated Action Plan</h2>
    {_action_plan_html(submission)}

    <p style="color:#5b6470;font-size:0.85rem;">
      &mdash; MissionOS AI, helping nonprofits build stronger organizations
      before they build bigger programs.
    </p>
    """


def send_results_email(submission):
    """Email the full results (score, breakdown, gaps, action plan) to the submitter."""
    if not submission.get("contact_email"):
        return
    send_email(
        to=submission["contact_email"],
        subject=f"Your MissionOS AI Readiness Snapshot ({submission['score']}/100)",
        html=_results_email_html(submission),
    )


def send_admin_notification(submission, results_url):
    """Email a short notification about a new submission to the admin address."""
    html = f"""
    <p><strong>{submission['org_name']}</strong> just completed the Organizational Health Assessment.</p>
    <p><strong>Overall score:</strong> {submission['score']}/100</p>
    <p><a href="{results_url}">View full results</a></p>
    """
    send_email(
        to=ADMIN_NOTIFICATION_EMAIL,
        subject=f"New assessment submitted: {submission['org_name']} ({submission['score']}/100)",
        html=html,
    )
