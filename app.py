import os
import uuid
from datetime import datetime, timezone
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, abort, session, flash

import action_plan
import db
import email_notify
import needs_assessment_db as ndb
import supabase_auth
from assessment import SECTIONS, SECTION_KEYS, SCALE_LABELS
from scoring import compute_score_breakdown

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

db.init_db()
ndb.init_needs_assessment_tables()


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/assessment/start", methods=["GET", "POST"])
def assessment_start():
    if request.method == "POST":
        org_name = request.form.get("org_name", "").strip()
        contact_name = request.form.get("contact_name", "").strip()
        contact_email = request.form.get("contact_email", "").strip()

        if not org_name:
            return render_template(
                "assessment_start.html",
                error="Organization name is required.",
                form=request.form,
            )

        session["draft"] = {
            "org_name": org_name,
            "contact_name": contact_name,
            "contact_email": contact_email,
            "answers": {},
        }
        return redirect(url_for("assessment_section", section_key=SECTION_KEYS[0]))

    return render_template("assessment_start.html", error=None, form={})


@app.route("/assessment/<section_key>", methods=["GET", "POST"])
def assessment_section(section_key):
    if "draft" not in session:
        return redirect(url_for("assessment_start"))
    if section_key not in SECTIONS:
        abort(404)

    section = SECTIONS[section_key]
    section_index = SECTION_KEYS.index(section_key)

    if request.method == "POST":
        section_answers = {}
        missing = False
        for question in section["questions"]:
            value = request.form.get(question["id"])
            if not value:
                missing = True
                continue
            section_answers[question["id"]] = int(value)

        if missing:
            return render_template(
                "assessment_section.html",
                section=section,
                section_index=section_index,
                total_sections=len(SECTION_KEYS),
                scale_labels=SCALE_LABELS,
                error="Please answer every question before continuing.",
                answers=section_answers,
            )

        session["draft"]["answers"][section_key] = section_answers
        session.modified = True

        next_index = section_index + 1
        if next_index < len(SECTION_KEYS):
            return redirect(url_for("assessment_section", section_key=SECTION_KEYS[next_index]))
        return redirect(url_for("assessment_submit"))

    saved_answers = session["draft"]["answers"].get(section_key, {})
    return render_template(
        "assessment_section.html",
        section=section,
        section_index=section_index,
        total_sections=len(SECTION_KEYS),
        scale_labels=SCALE_LABELS,
        error=None,
        answers=saved_answers,
    )


@app.route("/assessment/submit")
def assessment_submit():
    draft = session.get("draft")
    if not draft or len(draft["answers"]) < len(SECTION_KEYS):
        return redirect(url_for("assessment_start"))

    submission_id = str(uuid.uuid4())
    score, breakdown, gaps = compute_score_breakdown(draft["answers"])

    plan = None
    plan_error = None
    try:
        plan = action_plan.generate_action_plan(draft["org_name"], gaps, draft["answers"])
    except Exception as e:
        app.logger.error("Action plan generation failed: %s", e)
        plan_error = str(e)

    gap_titles = [gap["title"] for gap in gaps]

    db.save_submission(
        submission_id=submission_id,
        org_name=draft["org_name"],
        contact_name=draft["contact_name"],
        contact_email=draft["contact_email"],
        answers=draft["answers"],
        score=score,
        breakdown=breakdown,
        gaps=gap_titles,
        action_plan=plan,
        action_plan_error=plan_error,
        submitted_at=datetime.now(timezone.utc),
    )

    submission = {
        "org_name": draft["org_name"],
        "contact_email": draft["contact_email"],
        "score": score,
        "breakdown": breakdown,
        "gaps": gap_titles,
        "action_plan": plan,
        "action_plan_error": plan_error,
    }

    try:
        email_notify.send_results_email(submission)
    except Exception as e:
        app.logger.error("Failed to send results email to submitter: %s", e)

    try:
        results_url = url_for("assessment_results", submission_id=submission_id, _external=True)
        email_notify.send_admin_notification(submission, results_url)
    except Exception as e:
        app.logger.error("Failed to send admin notification email: %s", e)

    session.pop("draft", None)
    return redirect(url_for("assessment_results", submission_id=submission_id))


@app.route("/assessment/results/<submission_id>")
def assessment_results(submission_id):
    submission = db.get_submission(submission_id)
    if not submission:
        abort(404)
    return render_template("results.html", submission=submission)


def _safe_next_url(next_url):
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return url_for("dashboard")


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("dashboard_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/dashboard/login", methods=["GET", "POST"])
def dashboard_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        next_url = request.form.get("next", "")

        try:
            authenticated_email = supabase_auth.sign_in_with_password(email, password)
        except Exception as e:
            flash(str(e))
            return redirect(url_for("dashboard_login", next=next_url))

        try:
            if not supabase_auth.is_admin(authenticated_email):
                flash("Your account doesn't have dashboard access.")
                return redirect(url_for("dashboard_login", next=next_url))
        except Exception as e:
            flash(f"Couldn't verify dashboard access: {e}")
            return redirect(url_for("dashboard_login", next=next_url))

        session["is_admin"] = True
        session["admin_email"] = authenticated_email
        return redirect(_safe_next_url(next_url))

    return render_template("dashboard_login.html", next=request.args.get("next", ""))


@app.route("/dashboard/logout", methods=["POST"])
def dashboard_logout():
    session.pop("is_admin", None)
    session.pop("admin_email", None)
    return redirect(url_for("dashboard_login"))


@app.route("/dashboard")
@require_admin
def dashboard():
    submissions = db.list_submissions()
    return render_template("dashboard.html", submissions=submissions, admin_email=session.get("admin_email"))


_SAMPLE_SUBMISSION = {
    "org_name": "Sample Org (Test Send)",
    "score": 62,
    "breakdown": [
        {"key": "governance", "title": "Governance", "weight": 1, "score": 75},
        {"key": "financial_readiness", "title": "Financial Readiness", "weight": 2, "score": 50},
        {"key": "volunteer_management", "title": "Volunteer Management", "weight": 1, "score": 75},
        {"key": "project_planning", "title": "Project Planning", "weight": 1, "score": 50},
        {"key": "compliance_basics", "title": "Compliance Basics", "weight": 2, "score": 50},
    ],
    "gaps": ["Financial Readiness", "Project Planning", "Compliance Basics"],
    "action_plan": [
        {
            "area": "Financial Readiness",
            "action_steps": [
                "Draft a board-approved annual budget for the current fiscal year.",
                "Set up a recurring monthly financial review meeting with the treasurer.",
            ],
            "timeline": "Within 30 days",
            "resources_needed": ["Treasurer or bookkeeper time", "A simple budget template"],
        },
        {
            "area": "Project Planning",
            "action_steps": [
                "Define success metrics for your current top program.",
                "Build a basic project timeline for the next program launch.",
            ],
            "timeline": "Next quarter",
            "resources_needed": ["Program lead time", "A project planning template"],
        },
        {
            "area": "Compliance Basics",
            "action_steps": [
                "Confirm your Form 990 filing status and due date.",
                "Check charitable registration status in every state you solicit in.",
            ],
            "timeline": "Within 30 days",
            "resources_needed": ["An hour with your accountant or a compliance checklist"],
        },
    ],
    "action_plan_error": None,
}


@app.route("/test-email")
def test_email():
    """Trigger a real send of both submission emails for manual verification.

    Protected by TEST_EMAIL_TOKEN so it can't be used as an open email relay.
    Usage: /test-email?token=<TEST_EMAIL_TOKEN>&to=<email-to-receive-the-results-email>
    """
    expected_token = os.environ.get("TEST_EMAIL_TOKEN")
    if not expected_token or request.args.get("token") != expected_token:
        abort(404)

    to_email = request.args.get("to") or email_notify.ADMIN_NOTIFICATION_EMAIL
    sample = dict(_SAMPLE_SUBMISSION, contact_email=to_email)

    results = {}
    try:
        email_notify.send_results_email(sample)
        results["submitter_results_email"] = f"sent to {to_email}"
    except Exception as e:
        results["submitter_results_email"] = f"failed: {e}"

    try:
        results_url = url_for("home", _external=True)
        email_notify.send_admin_notification(sample, results_url)
        results["admin_notification_email"] = f"sent to {email_notify.ADMIN_NOTIFICATION_EMAIL}"
    except Exception as e:
        results["admin_notification_email"] = f"failed: {e}"

    return results


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
