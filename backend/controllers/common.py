from __future__ import annotations

import json

from flask import Blueprint, current_app, g, jsonify, request, send_file

from ..access_control import require_auth
from ..assessments_bank import FIELDS, ROLE_GROUPS
from ..errors import ApiError

bp = Blueprint("common", __name__, url_prefix="/api")


def body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("INVALID_JSON", "Send a JSON object.", 400)
    return data


@bp.get("/meta")
def meta():
    cfg = current_app.extensions["proofhire"].config
    return jsonify({"fields": FIELDS, "role_groups": {k: v["roles"] for k, v in ROLE_GROUPS.items()}, "demo": cfg.seed_demo, "max_upload_mb": cfg.max_upload_mb,
                    "evidence_types": ["GITHUB", "PORTFOLIO", "CERTIFICATE"]})


@bp.post("/auth/register")
def register():
    d = body()
    return jsonify(g.svc.auth.register(d.get("name"), d.get("email"), d.get("password"), d.get("role"), d.get("company"), d.get("field"))), 201


@bp.post("/auth/login")
def login():
    d = body()
    return jsonify(g.svc.auth.login(d.get("email"), d.get("password"), request.remote_addr or "?"))


@bp.post("/auth/social")
def social():
    d = body()
    return jsonify(g.svc.auth.social_login(d.get("provider"), d.get("email"), d.get("name"), d.get("role"), d.get("company"), d.get("field")))


@bp.post("/auth/demo")
def demo():
    return jsonify(g.svc.auth.demo_login(body().get("role")))


@bp.get("/auth/me")
@require_auth()
def me():
    from ..services.auth import public_user
    return jsonify({"user": public_user(g.user)})


@bp.get("/notifications")
@require_auth()
def notifications():
    return jsonify(g.svc.notifications.list(g.user["id"]))


@bp.post("/notifications/read")
@require_auth()
def notifications_read():
    ids = request.get_json(silent=True, force=True) or {}
    g.svc.notifications.mark_read(g.user["id"], ids.get("ids") if isinstance(ids, dict) else None)
    return jsonify({"ok": True})


@bp.get("/jobs")
@require_auth()
def jobs():
    mine = request.args.get("mine") == "1" and g.user["role"] == "RECRUITER"
    return jsonify(g.svc.jobs.list(g.user, request.args.get("field") or None, request.args.get("q") or None, mine))


@bp.post("/jobs")
@require_auth("RECRUITER")
def create_job():
    return jsonify(g.svc.jobs.create(g.user["id"], body())), 201


@bp.get("/evidence/<eid>/file-url")
@require_auth()
def file_url(eid):
    return jsonify(g.svc.submissions.file_url(g.user, eid))


@bp.get("/files/<token>")
def serve_file(token):
    claims = current_app.extensions["proofhire"].tokens.verify(token, typ="file")
    path = g.svc.files.path(claims["ref"])
    resp = send_file(path, as_attachment=True, download_name=claims.get("name") or "certificate")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, no-store"
    return resp
