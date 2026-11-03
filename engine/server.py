"""ProofScore Engine - independently deployable scoring service (design: Section 8).

POST /evaluate   evidence bundle -> ProofScore, sub-scores, strengths, recommendations, facts
GET  /health     status + model card (which model, what it was trained on)

Run:  python -m engine.server        (default port 5001)
Env:  ENGINE_KEY, ENGINE_PORT, ENGINE_MODE=live|offline, GITHUB_TOKEN, ENGINE_FIXTURES=1|0
"""
from __future__ import annotations

import hmac
import os

from flask import Flask, jsonify, request

from .features import DIM_MAX, DIMENSIONS, build_raw_features
from .feedback import build_feedback
from .fixtures import FIXTURES
from .model import ensure_model, model_card
from .signals import (CompositeFetcher, FixtureFetcher, GitHubFetcher, OfflineFetcher, PageFetcher,
                      UpstreamUnavailable, collect)

TYPES = {"GITHUB", "PORTFOLIO", "CERTIFICATE"}


def validate_bundle(b):
    if not isinstance(b, dict):
        return "body must be a JSON object"
    ev = b.get("evidence")
    if not isinstance(ev, list) or not 1 <= len(ev) <= 6:
        return "evidence must be a list of 1-6 items"
    for it in ev:
        if not isinstance(it, dict) or it.get("type") not in TYPES:
            return "each evidence item needs a valid type"
        for f in ("url", "description", "file_name"):
            v = it.get(f)
            if v is not None and (not isinstance(v, str) or len(v) > 2000):
                return f"{f} must be a string up to 2000 chars"
    if not isinstance(b.get("skill_area", ""), str) or len(b.get("skill_area", "")) > 80:
        return "skill_area invalid"
    skills = b.get("candidate_skills", [])
    if not isinstance(skills, list) or len(skills) > 50 or any(not isinstance(s, str) for s in skills):
        return "candidate_skills invalid"
    return None


def create_app(model=None, github=None, pages=None, key=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
    key = key or os.environ.get("ENGINE_KEY", "dev-engine-key")
    model = model or ensure_model()
    if github is None:
        if os.environ.get("ENGINE_MODE", "live") == "offline":
            live = OfflineFetcher()
        else:
            live = GitHubFetcher(token=os.environ.get("GITHUB_TOKEN"))
        fixtures = FixtureFetcher(FIXTURES) if os.environ.get("ENGINE_FIXTURES", "1") == "1" else None
        github = CompositeFetcher(fixtures, live)
    pages = pages or PageFetcher()

    def authorised():
        return hmac.compare_digest(request.headers.get("X-Engine-Key", ""), key)

    @app.get("/health")
    def health():
        card = model_card()
        return jsonify({"status": "ok", "model_version": model.version, "trained_on": model.trained_on,
                        "selected_algorithm": card.get("selected"), "cv_results": card.get("cv_results"),
                        "note": card.get("note")})

    @app.post("/evaluate")
    def evaluate():
        if not authorised():
            return jsonify({"error": "unauthorised"}), 401
        bundle = request.get_json(silent=True)
        problem = validate_bundle(bundle)
        if problem:
            return jsonify({"error": "invalid_bundle", "detail": problem}), 400
        try:
            gh, pg = collect(bundle, github, pages)
        except UpstreamUnavailable as e:
            return jsonify({"error": "upstream_unavailable", "detail": str(e)}), 503
        raw, facts, quality, notes = build_raw_features(bundle, gh, pg)
        points = model.predict(raw)
        strengths, recs = build_feedback(points, notes, quality, facts)
        overall10 = sum(points.values())
        return jsonify({
            "model_version": model.version,
            "trained_on": model.trained_on,
            "overall": round(overall10 * 10, 1),
            "sub_scores": {k: {"score": points[k], "max": DIM_MAX[k]} for k, _, _ in DIMENSIONS},
            "strengths": strengths,
            "recommendations": recs,
            "facts": facts,
            "data_quality": quality,
        })

    return app


if __name__ == "__main__":
    port = int(os.environ.get("ENGINE_PORT", "5001"))
    create_app().run(host=os.environ.get("ENGINE_HOST", "127.0.0.1"), port=port, threaded=True)
