"""ProofHire web back end (Flask).  Run:  python -m backend.app   (serves API + web front end on :5000)."""
from __future__ import annotations

import logging
import os

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .config import Config
from .db import Database
from .errors import ApiError
from .events import EventBus
from .scoring.client import HttpProofScoreClient, MockProofScoreClient
from .scoring.queue import ScoringQueue
from .security import LoginThrottle, TokenService
from .services import AppContext, Services
from .services.notifications import register_handlers

log = logging.getLogger("proofhire")
STATIC = os.path.join(os.path.dirname(__file__), "static")

CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; script-src 'self'; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


def create_app(config: Config | None = None, scorer=None) -> Flask:
    cfg = (config or Config.from_env()).finalize()
    app = Flask(__name__, static_folder=STATIC, static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = (cfg.max_upload_mb * 6 + 1) * 1024 * 1024

    db = Database(cfg.db_path)
    db.init_schema()
    events = EventBus()
    register_handlers(events)
    if scorer is None:
        scorer = MockProofScoreClient() if cfg.scorer == "mock" else HttpProofScoreClient(cfg.engine_url, cfg.engine_key, cfg.engine_timeout_s)
    ctx = AppContext(config=cfg, db=db, events=events, throttle=LoginThrottle(cfg.login_max_failures, cfg.login_window_s),
                     tokens=TokenService(cfg.secret, cfg.token_ttl_min, cfg.file_url_ttl_s), scorer=scorer)

    def handle_job(sid: str):
        with db.session(write=True) as s:
            Services(s, ctx).scoring.process(sid)

    ctx.queue = ScoringQueue(handle_job, start=cfg.start_worker)
    app.extensions["proofhire"] = ctx

    with db.session(write=True) as s:  # defaults + demo data (first start only)
        sv = Services(s, ctx)
        if sv.cfg_repo.get("MAX_RESUBMISSIONS") is None:
            sv.cfg_repo.set("MAX_RESUBMISSIONS", cfg.default_max_resubmissions)
        if cfg.seed_demo and not sv.users.search(limit=1):
            from .seed import seed_demo
            seed_demo(sv)
    if cfg.start_worker:  # durability: re-enqueue everything that was waiting when the process stopped
        with db.session(write=False) as s:
            for r in Services(s, ctx).subs.pending():
                ctx.queue.enqueue(r["id"])

    # ------------------------------------------------------------------ request lifecycle
    @app.before_request
    def open_session():
        if request.path.startswith("/api/"):
            g.session = db.session(write=request.method not in ("GET", "HEAD", "OPTIONS"))
            g.svc = Services(g.session, ctx)

    @app.after_request
    def finish(resp):
        s = getattr(g, "session", None)
        if s is not None and not s.closed:
            try:
                s.commit() if resp.status_code < 400 else s.rollback()
            except Exception:
                log.exception("commit failed")
                s.rollback()
                return _json_error(ApiError("SERVER_ERROR", "Something went wrong. Please try again.", 500))
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Content-Security-Policy", CSP)
        if request.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.teardown_request
    def cleanup(exc):
        s = getattr(g, "session", None)
        if s is not None and not s.closed:
            s.rollback()

    # ------------------------------------------------------------------ errors (one format)
    def _json_error(err: ApiError):
        resp = jsonify(err.to_dict())
        resp.status_code = err.status
        return resp

    @app.errorhandler(ApiError)
    def api_error(err):
        return _json_error(err)

    @app.errorhandler(HTTPException)
    def http_error(err):
        if request.path.startswith("/api/"):
            code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 413: "PAYLOAD_TOO_LARGE"}.get(err.code, "HTTP_ERROR")
            return _json_error(ApiError(code, err.description if err.code != 404 else "Not found.", err.code))
        return err

    @app.errorhandler(Exception)
    def crash(err):
        log.exception("unhandled error")
        return _json_error(ApiError("SERVER_ERROR", "Something went wrong. Please try again.", 500))

    # ------------------------------------------------------------------ routes
    from .controllers import admin, candidate, common, recruiter
    for mod in (common, candidate, recruiter, admin):
        app.register_blueprint(mod.bp)

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    return app


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    app = create_app()
    port = int(os.environ.get("PORT", "5000"))
    print(f"ProofHire running on http://127.0.0.1:{port}")
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, threaded=True)


if __name__ == "__main__":
    main()
