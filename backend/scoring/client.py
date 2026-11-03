"""ProofScoreClient interface (Strategy pattern): the web back end only knows this interface.

* HttpProofScoreClient - calls the independently deployed ProofScore Engine
* MockProofScoreClient - deterministic stand-in for development/tests (no engine needed)
"""
from __future__ import annotations

import hashlib

import requests

DIMENSIONS = [
    ("relevance", "Relevance to the job", 2.0),
    ("technical_quality", "Technical quality", 2.0),
    ("complexity", "Complexity / problem-solving", 1.5),
    ("code_quality", "Code quality & maintainability", 1.5),
    ("documentation", "Documentation", 1.0),
    ("testing", "Testing & reliability", 1.0),
    ("impact", "Evidence of real-world impact", 1.0),
]


class EngineUnavailable(Exception):
    """Timeout / connection error / 5xx: the submission is queued and retried with back-off."""


class EngineError(Exception):
    """The engine answered but rejected or returned something unusable: retrying will not help."""


def validate_result(r: dict) -> dict:
    try:
        overall = float(r["overall"])
        subs = {}
        for key, _label, mx in DIMENSIONS:
            s = float(r["sub_scores"][key]["score"])
            if not 0 <= s <= mx + 1e-6:
                raise ValueError(f"{key} out of range")
            subs[key] = {"score": round(s, 2), "max": mx}
        if not 0 <= overall <= 100:
            raise ValueError("overall out of range")
        return {
            "overall": round(overall, 1), "sub_scores": subs,
            "strengths": [str(x) for x in r.get("strengths", [])][:10],
            "recommendations": [{"dimension": str(x.get("dimension", "")), "label": str(x.get("label", "")),
                                 "text": str(x["text"]), "potential_gain": float(x.get("potential_gain", 0))}
                                for x in r.get("recommendations", [])][:10],
            "facts": [str(x) for x in r.get("facts", [])][:12],
            "model_version": str(r.get("model_version", "unknown")),
            "data_quality": str(r.get("data_quality", "full")),
        }
    except (KeyError, TypeError, ValueError) as e:
        raise EngineError(f"invalid engine response: {e}") from e


class ProofScoreClient:
    def evaluate(self, bundle: dict) -> dict:  # pragma: no cover - interface
        raise NotImplementedError


class HttpProofScoreClient(ProofScoreClient):
    def __init__(self, url: str, key: str, timeout: float):
        self.url, self.key, self.timeout = url.rstrip("/"), key, timeout

    def evaluate(self, bundle):
        try:
            r = requests.post(f"{self.url}/evaluate", json=bundle, headers={"X-Engine-Key": self.key}, timeout=self.timeout)
        except requests.RequestException as e:
            raise EngineUnavailable(f"engine unreachable ({e.__class__.__name__})") from e
        if r.status_code >= 500:
            raise EngineUnavailable(f"engine error {r.status_code}")
        if r.status_code != 200:
            raise EngineError(f"engine rejected request: {r.status_code} {r.text[:200]}")
        try:
            return validate_result(r.json())
        except ValueError as e:
            raise EngineError("engine returned invalid JSON") from e

    def health(self):
        try:
            r = requests.get(f"{self.url}/health", timeout=3)
            return {**r.json(), "status": "up"} if r.status_code == 200 else {"status": "down"}
        except (requests.RequestException, ValueError):
            return {"status": "down"}


class MockProofScoreClient(ProofScoreClient):
    """Deterministic pseudo-scores derived from the evidence text. Optionally fails the first N calls."""

    def __init__(self, fail_first: int = 0, error: Exception | None = None):
        self.fail_first, self.calls, self.error = fail_first, 0, error

    def evaluate(self, bundle):
        self.calls += 1
        if self.calls <= self.fail_first:
            raise self.error or EngineUnavailable("mock engine down")
        seed = hashlib.sha256(repr([(e["type"], e.get("url"), e.get("description")) for e in bundle["evidence"]]).encode()).digest()
        subs, total = {}, 0.0
        for i, (key, _l, mx) in enumerate(DIMENSIONS):
            frac = 0.35 + 0.6 * (seed[i] / 255)
            subs[key] = {"score": round(frac * mx, 2), "max": mx}
            total += subs[key]["score"]
        recs = [{"dimension": "testing", "label": "Testing & reliability", "text": "Add automated unit tests.", "potential_gain": 0.4}]
        return validate_result({"overall": round(total * 10, 1), "sub_scores": subs, "strengths": ["Mock strength."],
                                "recommendations": recs, "facts": ["Mock engine."], "model_version": "mock-v0", "data_quality": "full"})

    def health(self):
        return {"status": "up", "model_version": "mock-v0", "trained_on": "n/a (mock)"}
