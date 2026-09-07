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

import scoring

RESEND_API_BASE = "https://api.resend.com"

ADMIN_NOTIFICATION_EMAIL = os.environ.get("ADMIN_NOTIFICATION_EMAIL", "ladyem34@gmail.com")

# Mirrors the traffic-light colors on the results page (static/style.css:
# .gap-card-red/-yellow, .tier-badge-critical/-warning/-unlocked) -- email
# clients don't load an external stylesheet, so every value here has to be
# inlined into the HTML itself.
SEVERITY_STYLES = {
    "red": {"border": "#b3261e", "badge_bg": "#f5e6e5", "badge_color": "#b3261e", "emoji": "\U0001F534", "label": "Tackle first"},
    "yellow": {"border": "#d4a017", "badge_bg": "#fbf0d9", "badge_color": "#8a5a00", "emoji": "\U0001F7E1", "label": "Warning"},
    "green": {"border": "#2f6f4f", "badge_bg": "#e3f1e9", "badge_color": "#234f39", "emoji": "\U0001F7E2", "label": "Good to go"},
}


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


def _gaps_html(gaps):
    if not gaps:
        return "<p>No gap areas flagged &mdash; every area scored 80 or above.</p>"
    items = "".join(f"<li>{g}</li>" for g in gaps)
    return f"<ul>{items}</ul>"


def _score_badge_html(score, severity):
    style = SEVERITY_STYLES.get(severity, SEVERITY_STYLES["yellow"])
    return (
        f"<span style='display:inline-block;background:{style['badge_bg']};color:{style['badge_color']};"
        "font-weight:600;font-size:13px;padding:3px 10px;border-radius:999px;white-space:nowrap;'>"
        f"{score}/100</span>"
    )


def _gap_card_html(plan):
    severity = plan.get("severity") or "yellow"
    style = SEVERITY_STYLES.get(severity, SEVERITY_STYLES["yellow"])
    badge = _score_badge_html(plan["area_score"], severity) if plan.get("area_score") is not None else ""

    steps = "".join(
        f"<li style='margin-bottom:6px;'>{s['text'] if isinstance(s, dict) else s}</li>"
        for s in (plan.get("action_steps") or [])
    )
    resources = "".join(f"<li style='margin-bottom:4px;'>{r}</li>" for r in (plan.get("resources_needed") or []))
    resources_html = (
        f"<p style='font-weight:600;color:#5b6470;font-size:13px;margin:14px 0 4px;'>Resources Needed</p>"
        f"<ul style='margin:0;padding-left:20px;color:#5b6470;font-size:14px;'>{resources}</ul>"
        if resources else ""
    )

    return f"""
    <div style="background:#ffffff;border:1px solid #e1ddd3;border-left:4px solid {style['border']};
      border-radius:8px;padding:18px 20px;margin:16px 0;">
      <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;"><tr>
        <td style="font-size:17px;font-weight:700;color:#1c2430;">
          {plan['area']} <span style="font-size:13px;font-weight:600;color:#5b6470;">{style['emoji']} {style['label']}</span>
        </td>
        <td style="text-align:right;white-space:nowrap;vertical-align:top;">{badge}</td>
      </tr></table>
      <div style="background:#eef6f0;border:1px solid #cfe8d8;border-radius:8px;padding:14px 18px;margin:12px 0 0;">
        <p style="font-weight:700;font-size:13px;text-transform:uppercase;letter-spacing:0.04em;color:#234f39;margin:0 0 8px;">
          Next Steps
        </p>
        <ul style="margin:0 0 10px;padding-left:20px;">{steps}</ul>
        <p style="margin:0;font-size:14px;"><strong>Timeline:</strong> {plan.get('timeline', '')}</p>
      </div>
      {resources_html}
    </div>
    """


def _strong_area_html(area):
    style = SEVERITY_STYLES["green"]
    return f"""
    <div style="background:#ffffff;border:1px solid #e1ddd3;border-left:4px solid {style['border']};
      border-radius:6px;padding:10px 16px;margin:8px 0;">
      <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;"><tr>
        <td style="font-weight:600;color:#1c2430;">{style['emoji']} {area['title']}</td>
        <td style="text-align:right;">{_score_badge_html(area['score'], 'green')}</td>
      </tr></table>
    </div>
    """


def _gap_section_html(submission):
    if submission.get("action_plan_error"):
        return (
            "<p>We couldn't generate an AI action plan for this submission right now. "
            "Your score and gap list below are still accurate.</p>"
            + _gaps_html(submission["gaps"])
        )
    if not submission["gaps"]:
        return "<p>No gap areas flagged &mdash; every area scored 80 or above. Nice work!</p>"

    action_plan, _ = scoring.build_gap_view(submission["breakdown"], submission["gaps"], submission.get("action_plan"))
    if action_plan:
        return "".join(_gap_card_html(plan) for plan in action_plan)
    return _gaps_html(submission["gaps"])


def _results_email_html(submission, results_url):
    _, strong_areas = scoring.build_gap_view(submission["breakdown"], submission["gaps"], submission.get("action_plan"))
    strong_section = (
        "<h2 style='margin-top:28px;'>Good to Go</h2>" + "".join(_strong_area_html(a) for a in strong_areas)
        if strong_areas else ""
    )

    return f"""
    <h1>{submission['org_name']}&rsquo;s Readiness Snapshot</h1>

    <div style="background:#f7f6f2;border:1px solid #e1ddd3;border-radius:10px;padding:20px;text-align:center;margin:16px 0;">
      <p style="text-transform:uppercase;letter-spacing:0.04em;color:#5b6470;font-size:12px;margin:0;">
        Overall Readiness Score
      </p>
      <p style="font-size:36px;font-weight:700;color:#234f39;margin:6px 0;">
        {submission['score']}<span style="font-size:16px;color:#5b6470;">/100</span>
      </p>
    </div>

    <p style="font-size:13px;color:#5b6470;margin:8px 0 20px;">
      &#128994; Green &mdash; good to go, little improvement needed &nbsp;|&nbsp;
      &#128993; Yellow &mdash; a warning: approaching deadlines, funding risk, or other issues to watch &nbsp;|&nbsp;
      &#128308; Red &mdash; important: tackle these first
    </p>

    <h2>Gap Areas &amp; Next Steps</h2>
    {_gap_section_html(submission)}

    {strong_section}

    <p style="margin-top:24px;">
      <a href="{results_url}" style="display:inline-block;padding:10px 18px;background:#2f6f4f;
        color:#ffffff;text-decoration:none;border-radius:6px;font-weight:600;">
        View &amp; check off your action items
      </a>
    </p>
    <p style="color:#5b6470;font-size:0.85rem;">
      Bookmark that link &mdash; it's how you'll get back to check items off as you
      complete them.
    </p>

    <p style="color:#5b6470;font-size:0.85rem;">
      &mdash; MissionOS AI&trade;, helping nonprofits build stronger organizations
      before they build bigger programs.
    </p>
    """


def send_results_email(submission, results_url):
    """Email the full results (score, breakdown, gaps, action plan) to the submitter."""
    if not submission.get("contact_email"):
        return
    send_email(
        to=submission["contact_email"],
        subject=f"Your MissionOS AI Readiness Snapshot ({submission['score']}/100)",
        html=_results_email_html(submission, results_url),
    )


def _invite_documents_html(documents):
    if not documents:
        return ""
    items = "".join(f"<li>{d['file_name']}</li>" for d in documents)
    return f"<h2>Already waiting for you</h2><ul>{items}</ul>"


def send_portal_invite_email(org, invite_link, documents=None):
    """Invites an org's contact to their Client Portal, where their fund
    development resources and any documents already uploaded for them
    (e.g. a signed engagement letter) are waiting.
    """
    if not org.get("contact_email"):
        return
    html = f"""
    <h1>You're invited to your MissionOS AI Client Portal</h1>
    <p>{org['name']} now has a private portal for fund development resources
    {"and documents" if documents else ""} matched to your organization.</p>
    {_invite_documents_html(documents or [])}
    <p>
      <a href="{invite_link}" style="display:inline-block;padding:10px 18px;background:#2f6f4f;
        color:#ffffff;text-decoration:none;border-radius:6px;font-weight:600;">
        Set your password &amp; sign in
      </a>
    </p>
    <p style="color:#5b6470;font-size:0.85rem;">
      This link is single-use and expires after a while &mdash; if it stops working, ask
      us to resend your invite.
    </p>
    <p style="color:#5b6470;font-size:0.85rem;">
      &mdash; MissionOS AI&trade;, helping nonprofits build stronger organizations
      before they build bigger programs.
    </p>
    """
    send_email(
        to=org["contact_email"],
        subject=f"You're invited: {org['name']}'s MissionOS AI Client Portal",
        html=html,
    )


def send_password_reset_email(to_email, reset_link):
    """Emails a Client Portal password-reset link, requested via the
    portal's "Forgot your password?" flow."""
    html = f"""
    <h1>Reset your MissionOS AI Client Portal password</h1>
    <p>We got a request to reset the password for your Client Portal account.</p>
    <p>
      <a href="{reset_link}" style="display:inline-block;padding:10px 18px;background:#2f6f4f;
        color:#ffffff;text-decoration:none;border-radius:6px;font-weight:600;">
        Set a new password
      </a>
    </p>
    <p style="color:#5b6470;font-size:0.85rem;">
      This link is single-use and expires after a while. If you didn't request this,
      you can safely ignore this email.
    </p>
    <p style="color:#5b6470;font-size:0.85rem;">
      &mdash; MissionOS AI&trade;, helping nonprofits build stronger organizations
      before they build bigger programs.
    </p>
    """
    send_email(
        to=to_email,
        subject="Reset your MissionOS AI Client Portal password",
        html=html,
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
