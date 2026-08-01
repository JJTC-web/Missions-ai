import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, abort, session

import db
from assessment import SECTIONS, SECTION_KEYS, SCALE_LABELS

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

db.init_db()


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
    score, gaps = placeholder_score(draft["answers"])

    db.save_submission(
        submission_id=submission_id,
        org_name=draft["org_name"],
        contact_name=draft["contact_name"],
        contact_email=draft["contact_email"],
        answers=draft["answers"],
        score=score,
        gaps=gaps,
        submitted_at=datetime.now(timezone.utc),
    )

    session.pop("draft", None)
    return redirect(url_for("assessment_results", submission_id=submission_id))


@app.route("/assessment/results/<submission_id>")
def assessment_results(submission_id):
    submission = db.get_submission(submission_id)
    if not submission:
        abort(404)
    return render_template("results.html", submission=submission)


def placeholder_score(answers):
    """Naive average-based placeholder score and gap list.

    Stands in until the real scoring engine and AI action plan generator are wired up.
    """
    section_averages = {}
    for section_key, section_answers in answers.items():
        values = list(section_answers.values())
        section_averages[section_key] = sum(values) / len(values) if values else 0

    overall_avg = sum(section_averages.values()) / len(section_averages) if section_averages else 0
    score = round((overall_avg / 5) * 100)

    gaps = [
        SECTIONS[section_key]["title"]
        for section_key, avg in sorted(section_averages.items(), key=lambda item: item[1])
        if avg < 4
    ]
    return score, gaps


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
