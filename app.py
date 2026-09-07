import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, abort, session, flash, send_file, send_from_directory, Response
from werkzeug.utils import secure_filename

import action_plan
import db
import document_storage
import email_notify
import needs_assessment_db as ndb
import portal_db
import resource_library as reslib
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
portal_db.init_portal_tables()

ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "txt"}


def _allowed_document(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_DOCUMENT_EXTENSIONS


BOOKING_URL = "https://calendly.com/jjtcinfo/missionos-ai-meeting"

TIER_PRICING = {
    "free": "$0",
    "tier1": "$19.95/mo",
    "tier2": "$49.95/mo",
    "tier3": "$129.95/mo",
}

TIER_FEATURES = {
    "free": [
        "Organizational Health Assessment with results",
        "National Giving & Humanitarian Dates calendar",
    ],
    "tier1": [
        "2026 Grant Tracker template",
        "A 15-minute 1:1 check-in with Lady Emily once a quarter",
    ],
    "tier2": [
        "2026 Grant Tracker template",
        "Grants for Women — Funding Guide",
        "A 30-minute 1:1 check-in with Lady Emily once a quarter",
        "15% off bookkeeping reviews when connected to Wave, QBO, or Relay",
    ],
    "tier3": [
        "2026 Grant Tracker template",
        "Grants for Women — Funding Guide",
        "Grant Budget Template",
        "Church Funding Toolkit",
        "Curated Funding Opportunities, matched to your org",
        "A 30-minute 1:1 check-in with Lady Emily every month",
        "15% off bookkeeping reviews when connected to Wave, QBO, or Relay",
    ],
}

TIER_FOOTNOTE = (
    "All tiers include the option to onboard with Relay for banking. "
    "Upgrade, downgrade, or cancel any time."
)

# National/international giving, humanitarian, and charitable observances,
# grouped by month. A handful of these move every year (GivingTuesday,
# National Volunteer Week) -- noted rather than pinned to a specific date,
# since a wrong specific date is worse than an honest range.
GIVING_DATES = [
    {"month": "January", "observances": [
        {"name": "National Volunteer Blood Donor Month", "when": "All month"},
        {"name": "MLK Day of Service", "when": "3rd Monday in January"},
    ]},
    {"month": "February", "observances": [
        {"name": "Random Acts of Kindness Day", "when": "February 17"},
    ]},
    {"month": "March", "observances": [
        {"name": "Red Cross Month", "when": "All month"},
    ]},
    {"month": "April", "observances": [
        {"name": "National Volunteer Month", "when": "All month"},
        {"name": "National Volunteer Week", "when": "Mid-April (exact week set annually)"},
        {"name": "Global Youth Service Day", "when": "Dates vary"},
    ]},
    {"month": "May", "observances": [
        {"name": "Give Local America", "when": "Dates vary"},
    ]},
    {"month": "August", "observances": [
        {"name": "World Humanitarian Day", "when": "August 19"},
    ]},
    {"month": "September", "observances": [
        {"name": "International Day of Charity", "when": "September 5"},
        {"name": "International Literacy Day", "when": "September 8"},
    ]},
    {"month": "October", "observances": [
        {"name": "National Community Service Day", "when": "Dates vary"},
    ]},
    {"month": "November", "observances": [
        {"name": "National Philanthropy Day", "when": "November 15"},
        {"name": "GivingTuesday", "when": "Tuesday after U.S. Thanksgiving"},
    ]},
    {"month": "December", "observances": [
        {"name": "International Day of Persons with Disabilities", "when": "December 3"},
        {"name": "International Volunteer Day", "when": "December 5"},
        {"name": "Human Rights Day", "when": "December 10"},
        {"name": "International Human Solidarity Day", "when": "December 20"},
    ]},
]


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/giving-calendar")
def giving_calendar():
    return render_template("giving_calendar.html", giving_dates=GIVING_DATES)


@app.route("/tiers")
def tiers_page():
    return render_template(
        "tiers.html",
        tier_order=tiers.TIER_ORDER,
        tier_labels=tiers.TIER_LABELS,
        tier_pricing=TIER_PRICING,
        tier_features=TIER_FEATURES,
        tier_footnote=TIER_FOOTNOTE,
        booking_url=BOOKING_URL,
    )


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

    results_url = url_for("assessment_results", submission_id=submission_id, _external=True)

    try:
        email_notify.send_results_email(submission, results_url)
    except Exception as e:
        app.logger.error("Failed to send results email to submitter: %s", e)

    try:
        email_notify.send_admin_notification(submission, results_url)
    except Exception as e:
        app.logger.error("Failed to send admin notification email: %s", e)

    session.pop("draft", None)
    return redirect(url_for("assessment_results", submission_id=submission_id, milestone="new"))


@app.route("/assessment/results/<submission_id>")
def assessment_results(submission_id):
    submission = db.get_submission(submission_id)
    if not submission:
        abort(404)
    action_items = db.list_action_items(submission_id)
    return render_template(
        "results.html",
        submission=submission,
        action_items=action_items,
        milestone=request.args.get("milestone"),
        booking_url=BOOKING_URL,
    )


@app.route("/assessment/results/<submission_id>/action-items/<int:item_id>/toggle", methods=["POST"])
def assessment_toggle_action_item(submission_id, item_id):
    if not db.get_submission(submission_id):
        abort(404)

    items_before = db.list_action_items(submission_id)
    total = len(items_before)
    completed_before = sum(1 for item in items_before if item["is_complete"])

    db.toggle_action_item(item_id, submission_id)

    completed_after = sum(
        1 for item in db.list_action_items(submission_id) if item["is_complete"]
    )

    milestone = None
    if total and completed_after > completed_before:
        if completed_after == total:
            milestone = "done"
        elif completed_before < (total / 2) <= completed_after:
            milestone = "half"

    return redirect(url_for("assessment_results", submission_id=submission_id, milestone=milestone))


def _safe_next_url(next_url, default=None):
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return default or url_for("dashboard")


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("dashboard_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def require_client(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("client_org_id"):
            return redirect(url_for("portal_login", next=request.path))
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
    documents = portal_db.list_documents(org_id)
    return render_template(
        "dashboard_org_detail.html",
        org=org, region=region, runs=runs,
        funding_resources=funding_resources,
        funding_tier_ok=tiers.tier_meets(org["tier"], FUNDING_REQUIRED_TIER),
        funding_required_tier_label=tiers.TIER_LABELS[FUNDING_REQUIRED_TIER],
        documents=documents, doc_type_labels=portal_db.DOC_TYPE_LABELS,
        error=None, funding_import_error=None,
    )


@app.route("/dashboard/orgs/<int:org_id>/documents/upload", methods=["POST"])
@require_admin
def dashboard_org_document_upload(org_id):
    org = ndb.get_org(org_id)
    if not org:
        abort(404)

    file = request.files.get("file")
    doc_type = request.form.get("doc_type", "other")
    if doc_type not in portal_db.DOC_TYPES:
        doc_type = "other"

    if not file or not file.filename:
        flash("Choose a file to upload.")
        return redirect(url_for("dashboard_org_detail", org_id=org_id))

    filename = secure_filename(file.filename)
    if not filename or not _allowed_document(filename):
        flash("Unsupported file type.")
        return redirect(url_for("dashboard_org_detail", org_id=org_id))

    storage_path = f"{org_id}/{uuid.uuid4()}-{filename}"
    try:
        document_storage.upload_document(storage_path, file.read(), file.content_type)
    except Exception as e:
        app.logger.error("Document upload failed for org %s: %s", org_id, e)
        flash(f"Upload failed: {e}")
        return redirect(url_for("dashboard_org_detail", org_id=org_id))

    portal_db.create_document(org_id, filename, storage_path, doc_type, session.get("admin_email"))
    flash(f"Uploaded {filename}.")
    return redirect(url_for("dashboard_org_detail", org_id=org_id))


@app.route("/dashboard/orgs/<int:org_id>/documents/<int:doc_id>/download")
@require_admin
def dashboard_org_document_download(org_id, doc_id):
    document = portal_db.get_document(doc_id, org_id)
    if not document:
        abort(404)
    try:
        file_bytes, content_type = document_storage.download_document(document["storage_path"])
    except Exception as e:
        app.logger.error("Document download failed for document %s: %s", doc_id, e)
        abort(500)
    return Response(
        file_bytes,
        mimetype=content_type,
        headers={"Content-Disposition": f'attachment; filename="{document["file_name"]}"'},
    )


@app.route("/dashboard/orgs/<int:org_id>/invite", methods=["POST"])
@require_admin
def dashboard_org_invite(org_id):
    org = ndb.get_org(org_id)
    if not org:
        abort(404)
    if not org.get("contact_email"):
        flash("Add a contact email for this organization before inviting them to the portal.")
        return redirect(url_for("dashboard_org_detail", org_id=org_id))

    redirect_to = url_for("portal_set_password", _external=True)
    try:
        action_link, auth_user_id = supabase_auth.admin_generate_invite_link(org["contact_email"], redirect_to)
    except Exception as e:
        app.logger.error("Portal invite failed for org %s: %s", org_id, e)
        flash(f"Couldn't create the portal invite: {e}")
        return redirect(url_for("dashboard_org_detail", org_id=org_id))

    portal_db.upsert_client_user(org_id, auth_user_id, org["contact_email"])

    documents = portal_db.list_documents(org_id)
    try:
        email_notify.send_portal_invite_email(org, action_link, documents)
    except Exception as e:
        app.logger.error("Failed to send portal invite email for org %s: %s", org_id, e)
        flash(f"Portal access was created, but the invite email failed to send: {e}")
        return redirect(url_for("dashboard_org_detail", org_id=org_id))

    flash(f"Portal invite sent to {org['contact_email']}.")
    return redirect(url_for("dashboard_org_detail", org_id=org_id))


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
        documents = portal_db.list_documents(org_id)
        return render_template(
            "dashboard_org_detail.html",
            org=org, region=region, runs=runs,
            funding_resources=funding_resources,
            funding_tier_ok=tiers.tier_meets(org["tier"], FUNDING_REQUIRED_TIER),
            funding_required_tier_label=tiers.TIER_LABELS[FUNDING_REQUIRED_TIER],
            documents=documents, doc_type_labels=portal_db.DOC_TYPE_LABELS,
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


RESOURCE_LIBRARY_DIR = os.path.join(os.path.dirname(__file__), "resource_library", "files")


@app.route("/dashboard/resource-library")
@require_admin
def dashboard_resource_library():
    return render_template(
        "dashboard_resource_library.html",
        resources=reslib.RESOURCES,
        tier_labels=tiers.TIER_LABELS,
    )


@app.route("/dashboard/resource-library/<resource_id>/download")
@require_admin
def dashboard_resource_library_download(resource_id):
    resource = reslib.get_resource(resource_id)
    if not resource:
        abort(404)
    return send_from_directory(RESOURCE_LIBRARY_DIR, resource["filename"], as_attachment=True)


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


@app.route("/portal/login", methods=["GET", "POST"])
def portal_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        next_url = request.form.get("next", "")

        try:
            authenticated_email = supabase_auth.sign_in_with_password(email, password)
        except Exception as e:
            flash(str(e))
            return redirect(url_for("portal_login", next=next_url))

        membership = portal_db.get_client_membership(authenticated_email)
        if not membership:
            flash("Your account doesn't have portal access for any organization.")
            return redirect(url_for("portal_login", next=next_url))

        if not membership["activated_at"]:
            portal_db.mark_activated(authenticated_email)

        session["client_org_id"] = membership["organization_id"]
        session["client_email"] = authenticated_email
        return redirect(_safe_next_url(next_url, url_for("portal_home")))

    return render_template("portal_login.html", next=request.args.get("next", ""))


@app.route("/portal/logout", methods=["POST"])
def portal_logout():
    session.pop("client_org_id", None)
    session.pop("client_email", None)
    return redirect(url_for("portal_login"))


@app.route("/portal/set-password")
def portal_set_password():
    """Landing page for a Supabase invite/recovery link. The access token
    arrives in the URL fragment (never sent to this server), so the actual
    password-setting call happens client-side against Supabase directly --
    see templates/portal_set_password.html."""
    return render_template(
        "portal_set_password.html",
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY", ""),
    )


@app.route("/portal")
@require_client
def portal_home():
    org = ndb.get_org(session["client_org_id"])
    if not org:
        abort(404)
    documents = portal_db.list_documents(org["id"])
    funding_tier_ok = tiers.tier_meets(org["tier"], FUNDING_REQUIRED_TIER)
    funding_resources = ndb.list_funding_resources(org["id"]) if funding_tier_ok else []
    runs = ndb.list_needs_runs_for_org(org["id"])
    return render_template(
        "portal_home.html",
        org=org,
        documents=documents,
        doc_type_labels=portal_db.DOC_TYPE_LABELS,
        funding_resources=funding_resources,
        funding_tier_ok=funding_tier_ok,
        funding_required_tier_label=tiers.TIER_LABELS[FUNDING_REQUIRED_TIER],
        runs=runs,
        client_email=session.get("client_email"),
    )


@app.route("/portal/documents/<int:doc_id>/download")
@require_client
def portal_document_download(doc_id):
    document = portal_db.get_document(doc_id, session["client_org_id"])
    if not document:
        abort(404)
    try:
        file_bytes, content_type = document_storage.download_document(document["storage_path"])
    except Exception as e:
        app.logger.error("Document download failed for document %s: %s", doc_id, e)
        abort(500)
    return Response(
        file_bytes,
        mimetype=content_type,
        headers={"Content-Disposition": f'attachment; filename="{document["file_name"]}"'},
    )


@app.route("/portal/needs-runs/<int:run_id>/download.xlsx")
@require_client
def portal_needs_run_download(run_id):
    run = ndb.get_needs_run(run_id)
    if not run or run["org_id"] != session["client_org_id"] or run["status"] != "complete" or not run["workbook_json"]:
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

    results_url = url_for("home", _external=True)

    results = {}
    try:
        email_notify.send_results_email(sample, results_url)
        results["submitter_results_email"] = f"sent to {to_email}"
    except Exception as e:
        results["submitter_results_email"] = f"failed: {e}"

    try:
        email_notify.send_admin_notification(sample, results_url)
        results["admin_notification_email"] = f"sent to {email_notify.ADMIN_NOTIFICATION_EMAIL}"
    except Exception as e:
        results["admin_notification_email"] = f"failed: {e}"

    return results


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
