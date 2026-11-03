from __future__ import annotations

import json

from flask import Blueprint, g, jsonify, request

from ..access_control import require_auth
from ..errors import ApiError
from .common import body

bp = Blueprint("candidate", __name__, url_prefix="/api/candidate")


def submission_request():
    """JSON body, or multipart/form-data with a JSON 'payload' field plus certificate files."""
    if request.mimetype == "multipart/form-data":
        try:
            payload = json.loads(request.form.get("payload", "{}"))
        except ValueError:
            raise ApiError("INVALID_JSON", "The submission payload is malformed.", 400)
        return payload, dict(request.files)
    return (request.get_json(silent=True) or {}), {}


@bp.get("/profile")
@require_auth("CANDIDATE")
def profile():
    return jsonify(g.svc.profile.get(g.user["id"]))


@bp.put("/profile")
@require_auth("CANDIDATE")
def update_profile():
    return jsonify(g.svc.profile.update(g.user["id"], body()))


@bp.get("/submissions")
@require_auth("CANDIDATE")
def list_submissions():
    return jsonify(g.svc.submissions.list_for_candidate(g.user["id"]))


@bp.post("/submissions")
@require_auth("CANDIDATE")
def create_submission():
    p, files = submission_request()
    return jsonify(g.svc.submissions.submit_evidence(g.user["id"], p.get("title"), p.get("skill_area"), p.get("items"), files)), 201


@bp.get("/submissions/<sid>")
@require_auth("CANDIDATE")
def get_submission(sid):
    return jsonify(g.svc.submissions.get_owned(g.user["id"], sid))


@bp.post("/submissions/<sid>/resubmit")
@require_auth("CANDIDATE")
def resubmit(sid):
    p, files = submission_request()
    return jsonify(g.svc.submissions.resubmit(g.user["id"], sid, p.get("items"), files))


@bp.get("/assessments")
@require_auth("CANDIDATE")
def assessments():
    return jsonify(g.svc.assessments.overview(g.user["id"]))


@bp.post("/assessments/<field>/start")
@require_auth("CANDIDATE")
def start_assessment(field):
    return jsonify(g.svc.assessments.start(g.user["id"], field))


@bp.post("/assessments/<field>/submit")
@require_auth("CANDIDATE")
def submit_assessment(field):
    return jsonify(g.svc.assessments.submit(g.user["id"], field, body().get("answers")))


@bp.get("/contact-requests")
@require_auth("CANDIDATE")
def contact_requests():
    return jsonify(g.svc.contacts.for_candidate(g.user["id"]))


@bp.get("/stats")
@require_auth("CANDIDATE")
def stats():
    return jsonify({"views_today": g.svc.contacts.views_today(g.user["id"]), "messages": len(g.svc.contacts.for_candidate(g.user["id"]))})
