import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, abort, session, flash, send_file

import action_plan
import db
import email_notify
import needs_assessment_db as ndb
import tiers
import needs_workbook_generator as workbook_gen
import region_research
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

    submitted_at = datetime.now(timezone.utc)
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
        submitted_at=submitted_at,
    )

    if plan:
        db.create_action_items(submission_id, plan, submitted_at)

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
    action_items = db.list_action_items(submission_id)
    return render_template("results.html", submission=submission, action_items=action_items)


@app.route("/assessment/results/<submission_id>/action-items/<int:item_id>/toggle", methods=["POST"])
def assessment_toggle_action_item(submission_id, item_id):
    if not db.get_submission(submission_id):
        abort(404)
    db.toggle_action_item(item_id, submission_id)
    return redirect(url_for("assessment_results", submission_id=submission_id))


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


@app.route("/dashboard/regions")
@require_admin
def dashboard_regions():
    regions = ndb.list_regions()
    return render_template("dashboard_regions.html", regions=regions, error=None, form={})


@app.route("/dashboard/seed-gary", methods=["POST"])
@require_admin
def dashboard_seed_gary():
    """One-click seed of the Gary, IN reference fixture (idempotent -- reuses
    existing rows if already seeded), so it's not a manual 9-row re-entry."""
    import seed_gary
    region_id, org_id = seed_gary.seed()
    flash(f"Seeded Gary, IN fixture (region id={region_id}, org id={org_id}).")
    return redirect(url_for("dashboard_org_detail", org_id=org_id))


@app.route("/dashboard/regions/new", methods=["POST"])
@require_admin
def dashboard_regions_new():
    city = request.form.get("city", "").strip()
    county = request.form.get("county", "").strip()
    state = request.form.get("state", "").strip()
    coc_region = request.form.get("coc_region", "").strip()

    if not city or not state:
        regions = ndb.list_regions()
        return render_template(
            "dashboard_regions.html",
            regions=regions,
            error="City and state are required.",
            form=request.form,
        )

    region_id = ndb.create_region(city, county or None, state, coc_region or None)
    return redirect(url_for("dashboard_region_detail", region_id=region_id))


@app.route("/dashboard/regions/<int:region_id>")
@require_admin
def dashboard_region_detail(region_id):
    region = ndb.get_region(region_id)
    if not region:
        abort(404)
    stats = ndb.list_region_stats(region_id)
    directory = ndb.list_resource_directory(region_id)
    drafts = ndb.list_research_drafts(region_id)
    return render_template(
        "dashboard_region_detail.html",
        region=region,
        stats=stats,
        directory=directory,
        drafts=drafts,
        stat_error=None,
        directory_error=None,
    )


@app.route("/dashboard/regions/<int:region_id>/stats", methods=["POST"])
@require_admin
def dashboard_region_add_stat(region_id):
    region = ndb.get_region(region_id)
    if not region:
        abort(404)

    metric_name = request.form.get("metric_name", "").strip()
    value = request.form.get("value", "").strip()
    geography_level = request.form.get("geography_level", "").strip()
    source = request.form.get("source", "").strip()
    as_of_date = request.form.get("as_of_date", "").strip()

    if not metric_name or not value:
        stats = ndb.list_region_stats(region_id)
        directory = ndb.list_resource_directory(region_id)
        drafts = ndb.list_research_drafts(region_id)
        return render_template(
            "dashboard_region_detail.html",
            region=region,
            stats=stats,
            directory=directory,
            drafts=drafts,
            stat_error="Metric name and value are required.",
            directory_error=None,
        )

    ndb.add_region_stat(
        region_id, metric_name, value,
        geography_level=geography_level or None,
        source=source or None,
        as_of_date=as_of_date or None,
    )
    return redirect(url_for("dashboard_region_detail", region_id=region_id))


@app.route("/dashboard/regions/<int:region_id>/resources", methods=["POST"])
@require_admin
def dashboard_region_add_resource(region_id):
    region = ndb.get_region(region_id)
    if not region:
        abort(404)

    name = request.form.get("name", "").strip()
    address = request.form.get("address", "").strip()
    services = request.form.get("services", "").strip()
    population_served = request.form.get("population_served", "").strip()
    phone = request.form.get("phone", "").strip()
    source = request.form.get("source", "").strip()

    if not name:
        stats = ndb.list_region_stats(region_id)
        directory = ndb.list_resource_directory(region_id)
        drafts = ndb.list_research_drafts(region_id)
        return render_template(
            "dashboard_region_detail.html",
            region=region,
            stats=stats,
            directory=directory,
            drafts=drafts,
            stat_error=None,
            directory_error="Organization name is required.",
        )

    ndb.add_resource_directory_entry(
        region_id, name,
        address=address or None,
        services=services or None,
        population_served=population_served or None,
        phone=phone or None,
        source=source or None,
    )
    return redirect(url_for("dashboard_region_detail", region_id=region_id))


@app.route("/dashboard/regions/<int:region_id>/research", methods=["POST"])
@require_admin
def dashboard_region_research(region_id):
    region = ndb.get_region(region_id)
    if not region:
        abort(404)

    try:
        result = region_research.research_region(region)
    except Exception as e:
        app.logger.error("Region research failed for region %s: %s", region_id, e)
        flash(f"AI research failed: {e}")
        return redirect(url_for("dashboard_region_detail", region_id=region_id))

    for stat in result.get("stats", []):
        ndb.create_research_draft(region_id, "stat", stat)
    for resource in result.get("resources", []):
        ndb.create_research_draft(region_id, "resource", resource)

    flash(
        f"AI research drafted {len(result.get('stats', []))} stat(s) and "
        f"{len(result.get('resources', []))} resource(s) for review below."
    )
    return redirect(url_for("dashboard_region_detail", region_id=region_id))


@app.route("/dashboard/regions/<int:region_id>/drafts/<int:draft_id>/approve", methods=["POST"])
@require_admin
def dashboard_region_draft_approve(region_id, draft_id):
    region = ndb.get_region(region_id)
    if not region:
        abort(404)
    draft = ndb.get_research_draft(draft_id)
    if not draft or draft["region_id"] != region_id:
        abort(404)

    payload = draft["payload"]
    if draft["kind"] == "stat":
        ndb.add_region_stat(
            region_id,
            payload.get("metric_name"),
            payload.get("value"),
            geography_level=payload.get("geography_level") or None,
            source=payload.get("source") or None,
        )
    elif draft["kind"] == "resource":
        ndb.add_resource_directory_entry(
            region_id,
            payload.get("name"),
            address=payload.get("address") or None,
            services=payload.get("services") or None,
            population_served=payload.get("population_served") or None,
            phone=payload.get("phone") or None,
            source=payload.get("source") or None,
        )

    ndb.delete_research_draft(draft_id)
    flash("Added to region data.")
    return redirect(url_for("dashboard_region_detail", region_id=region_id))


@app.route("/dashboard/regions/<int:region_id>/drafts/<int:draft_id>/reject", methods=["POST"])
@require_admin
def dashboard_region_draft_reject(region_id, draft_id):
    region = ndb.get_region(region_id)
    if not region:
        abort(404)
    draft = ndb.get_research_draft(draft_id)
    if not draft or draft["region_id"] != region_id:
        abort(404)

    ndb.delete_research_draft(draft_id)
    flash("Draft dismissed.")
    return redirect(url_for("dashboard_region_detail", region_id=region_id))


@app.route("/dashboard/orgs")
@require_admin
def dashboard_orgs():
    orgs = ndb.list_orgs()
    regions = ndb.list_regions()
    return render_template("dashboard_orgs.html", orgs=orgs, regions=regions, error=None, form={})


@app.route("/dashboard/orgs/new", methods=["POST"])
@require_admin
def dashboard_orgs_new():
    name = request.form.get("name", "").strip()
    region_id = request.form.get("region_id", "").strip()
    contact_name = request.form.get("contact_name", "").strip()
    contact_email = request.form.get("contact_email", "").strip()
    mission = request.form.get("mission", "").strip()

    if not name or not region_id:
        orgs = ndb.list_orgs()
        regions = ndb.list_regions()
        return render_template(
            "dashboard_orgs.html",
            orgs=orgs,
            regions=regions,
            error="Organization name and region are required.",
            form=request.form,
        )

    org_id = ndb.create_org(
        name, int(region_id),
        contact_name=contact_name or None,
        contact_email=contact_email or None,
        mission=mission or None,
    )
    return redirect(url_for("dashboard_org_detail", org_id=org_id))


FUNDING_REQUIRED_TIER = "tier3"


@app.route("/dashboard/orgs/<int:org_id>")
@require_admin
def dashboard_org_detail(org_id):
    org = ndb.get_org(org_id)
    if not org:
        abort(404)
    region = ndb.get_region(org["region_id"])
    runs = ndb.list_needs_runs_for_org(org_id)
    funding_resources = ndb.list_funding_resources(org_id)
    return render_template(
        "dashboard_org_detail.html",
        org=org, region=region, runs=runs,
        funding_resources=funding_resources,
        funding_tier_ok=tiers.tier_meets(org["tier"], FUNDING_REQUIRED_TIER),
        funding_required_tier_label=tiers.TIER_LABELS[FUNDING_REQUIRED_TIER],
        error=None, funding_import_error=None,
    )


@app.route("/dashboard/orgs/<int:org_id>/funding/import", methods=["POST"])
@require_admin
def dashboard_org_funding_import(org_id):
    org = ndb.get_org(org_id)
    if not org:
        abort(404)

    raw = request.form.get("resources_json", "").strip()
    try:
        data = json.loads(raw)
        created, updated = ndb.import_funding_resources(org_id, data)
    except Exception as e:
        region = ndb.get_region(org["region_id"])
        runs = ndb.list_needs_runs_for_org(org_id)
        funding_resources = ndb.list_funding_resources(org_id)
        return render_template(
            "dashboard_org_detail.html",
            org=org, region=region, runs=runs,
            funding_resources=funding_resources,
            funding_tier_ok=tiers.tier_meets(org["tier"], FUNDING_REQUIRED_TIER),
            funding_required_tier_label=tiers.TIER_LABELS[FUNDING_REQUIRED_TIER],
            error=None, funding_import_error=f"Could not import: {e}",
        )

    flash(f"Imported funding resources: {created} added, {updated} updated.")
    return redirect(url_for("dashboard_org_detail", org_id=org_id))


@app.route("/dashboard/orgs/<int:org_id>/funding/<int:resource_id>/delete", methods=["POST"])
@require_admin
def dashboard_org_funding_delete(org_id, resource_id):
    org = ndb.get_org(org_id)
    if not org:
        abort(404)
    ndb.delete_funding_resource(resource_id, org_id)
    flash("Funding resource removed.")
    return redirect(url_for("dashboard_org_detail", org_id=org_id))


@app.route("/dashboard/orgs/<int:org_id>/tier", methods=["POST"])
@require_admin
def dashboard_org_set_tier(org_id):
    org = ndb.get_org(org_id)
    if not org:
        abort(404)
    tier = request.form.get("tier", "").strip()
    next_url = _safe_next_url(request.form.get("next", ""))
    try:
        ndb.set_org_tier(org_id, tier)
    except ValueError:
        flash("Invalid tier selected.")
        return redirect(next_url)
    flash(f"{org['name']} tier updated to {tiers.TIER_LABELS.get(tier, tier)}.")
    return redirect(next_url)


@app.route("/dashboard/tiers")
@require_admin
def dashboard_tiers():
    orgs = ndb.list_orgs()
    return render_template("dashboard_tiers.html", orgs=orgs, tier_labels=tiers.TIER_LABELS, tier_order=tiers.TIER_ORDER)


@app.route("/dashboard/orgs/<int:org_id>/generate", methods=["POST"])
@require_admin
def dashboard_org_generate(org_id):
    org = ndb.get_org(org_id)
    if not org:
        abort(404)
    region = ndb.get_region(org["region_id"])
    if not region:
        flash("This org's region no longer exists.")
        return redirect(url_for("dashboard_org_detail", org_id=org_id))

    stats = ndb.list_region_stats(region["id"])
    directory = ndb.list_resource_directory(region["id"])

    run_id = ndb.create_needs_run(org_id, region["id"])
    try:
        content = workbook_gen.generate_workbook_content(org, region, stats, directory)
        ndb.complete_needs_run(
            run_id, content,
            workbook_url=url_for("dashboard_needs_run_download", run_id=run_id),
        )
    except Exception as e:
        app.logger.error("Needs Assessment Workbook generation failed: %s", e)
        ndb.fail_needs_run(run_id, str(e))
        flash(f"Workbook generation failed: {e}")

    return redirect(url_for("dashboard_org_detail", org_id=org_id))


@app.route("/dashboard/needs-runs/<int:run_id>/download.xlsx")
@require_admin
def dashboard_needs_run_download(run_id):
    run = ndb.get_needs_run(run_id)
    if not run or run["status"] != "complete" or not run["workbook_json"]:
        abort(404)

    org = ndb.get_org(run["org_id"])
    region = ndb.get_region(run["region_id"])
    stats = ndb.list_region_stats(run["region_id"])
    directory = ndb.list_resource_directory(run["region_id"])

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, f"needs-assessment-{run_id}.xlsx")
        workbook_gen.build_workbook_xlsx(org, region, stats, directory, run["workbook_json"], output_path)
        return send_file(
            output_path,
            as_attachment=True,
            download_name=f"MissionOS-Needs-Assessment-{region['city']}-{run_id}.xlsx",
        )


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
