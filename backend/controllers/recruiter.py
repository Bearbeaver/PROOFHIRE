from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..access_control import require_auth
from ..errors import ApiError
from .common import body

bp = Blueprint("recruiter", __name__, url_prefix="/api/recruiter")


@bp.get("/candidates")
@require_auth("RECRUITER")
def candidates():
    try:
        min_score = float(request.args.get("min_score", 0) or 0)
        page = max(0, int(request.args.get("page", 0) or 0))
    except ValueError:
        raise ApiError("INVALID_INPUT", "min_score and page must be numbers.", 400)
    return jsonify(g.svc.search.find_candidates(g.user["id"], request.args.get("skill") or None, request.args.get("field") or None,
                                                min_score, request.args.get("verified") == "1", page))


@bp.get("/candidates/<cid>")
@require_auth("RECRUITER")
def candidate(cid):
    return jsonify(g.svc.search.visible_profile(g.user["id"], cid))


@bp.put("/candidates/<cid>/shortlist")
@require_auth("RECRUITER")
def shortlist_add(cid):
    return jsonify(g.svc.shortlist.add(g.user["id"], cid))


@bp.delete("/candidates/<cid>/shortlist")
@require_auth("RECRUITER")
def shortlist_remove(cid):
    return jsonify(g.svc.shortlist.remove(g.user["id"], cid))


@bp.get("/shortlist")
@require_auth("RECRUITER")
def shortlist():
    return jsonify(g.svc.shortlist.list(g.user["id"]))


@bp.post("/candidates/<cid>/contact")
@require_auth("RECRUITER")
def contact(cid):
    return jsonify(g.svc.shortlist.contact(g.user["id"], cid, body().get("message")))


@bp.post("/submissions/<sid>/flag")
@require_auth("RECRUITER")
def flag(sid):
    return jsonify(g.svc.shortlist.flag(g.user["id"], sid, body().get("reason")))


@bp.get("/search-history")
@require_auth("RECRUITER")
def history():
    return jsonify(g.svc.recruiters.find(g.user["id"])["search_history"])


@bp.get("/messages")
@require_auth("RECRUITER")
def sent_messages():
    return jsonify(g.svc.contacts.sent_by(g.user["id"]))
