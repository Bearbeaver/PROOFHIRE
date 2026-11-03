from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..access_control import require_auth
from .common import body

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.get("/stats")
@require_auth("ADMIN")
def stats():
    return jsonify(g.svc.admin.stats())


@bp.get("/users")
@require_auth("ADMIN")
def users():
    a = request.args
    return jsonify(g.svc.admin.users(g.user["id"], a.get("q") or None, a.get("role") or None, a.get("status") or None))


@bp.post("/users/<uid>/status")
@require_auth("ADMIN")
def user_status(uid):
    d = body()
    return jsonify(g.svc.admin.set_user_status(g.user["id"], uid, d.get("status"), d.get("reason")))


@bp.get("/submissions")
@require_auth("ADMIN")
def submissions():
    a = request.args
    return jsonify(g.svc.admin.submissions(g.user["id"], a.get("moderation") or None, a.get("status") or None, a.get("q") or None))


@bp.post("/submissions/<sid>/moderate")
@require_auth("ADMIN")
def moderate(sid):
    d = body()
    return jsonify(g.svc.admin.moderate(g.user["id"], sid, d.get("action"), d.get("reason")))


@bp.get("/audit")
@require_auth("ADMIN")
def audit():
    return jsonify(g.svc.admin.audit(g.user["id"]))


@bp.get("/config")
@require_auth("ADMIN")
def get_config():
    return jsonify(g.svc.admin.get_config(g.user["id"]))


@bp.put("/config")
@require_auth("ADMIN")
def put_config():
    return jsonify(g.svc.admin.update_config(g.user["id"], body()))


@bp.post("/queue/requeue")
@require_auth("ADMIN")
def requeue():
    return jsonify(g.svc.admin.requeue(g.user["id"]))
