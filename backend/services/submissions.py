from __future__ import annotations

import logging
import re

from ..assessments_bank import FIELDS
from ..errors import ApiError, forbidden, not_found
from ..scoring.client import DIMENSIONS, EngineError, EngineUnavailable

log = logging.getLogger("proofhire.scoring")

# Submission state machine (design Figure 6). QUEUED added for NFR5.
TRANSITIONS = {
    "PENDING": {"SCORED", "QUEUED"},
    "QUEUED": {"SCORED", "QUEUED"},
    "SCORED": {"RESUBMITTED"},
    "RESUBMITTED": {"SCORED", "QUEUED"},
}
GITHUB_RE = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?(\.git)?/?$")
URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]{2,500}$")
LABELS = {k: l for k, l, _ in DIMENSIONS}
MAX_ITEMS, MAX_EXHIBITS = 6, 12


def transition(current: str, new: str) -> str:
    if new not in TRANSITIONS.get(current, set()):
        raise ApiError("INVALID_TRANSITION", f"A submission cannot move from {current} to {new}.", 409)
    return new


def score_dto(ps):
    if not ps:
        return None
    return {
        "attempt_no": ps["attempt_no"], "overall": ps["overall_score"], "out_of_10": round(ps["overall_score"] / 10, 1),
        "sub_scores": [{"key": k, "label": LABELS[k], "score": ps["sub_scores"][k]["score"], "max": ps["sub_scores"][k]["max"]}
                       for k, _l, _m in DIMENSIONS if k in ps["sub_scores"]],
        "strengths": ps["strengths"], "recommendations": ps["recommendations"], "facts": ps["facts"],
        "scored_at": ps["scored_at"], "model_version": ps["model_version"], "data_quality": ps["data_quality"],
    }


def evidence_dto(e):
    return {"id": e["id"], "type": e["type"], "url": e["url"], "description": e["description"],
            "file_name": e["file_name"], "has_file": bool(e["file_ref"])}


class EvidenceValidator:
    @staticmethod
    def validate(item, index: int) -> dict:
        where = {"item": index}
        if not isinstance(item, dict):
            raise ApiError("INVALID_EVIDENCE", "Evidence item is malformed.", 400, where)
        t = item.get("type")
        url = (item.get("url") or "").strip() or None
        desc = (item.get("description") or "").strip()
        if len(desc) > 2000:
            raise ApiError("INVALID_EVIDENCE", "Description must be at most 2000 characters.", 400, {**where, "field": "description"})
        if t == "GITHUB":
            if not url or not GITHUB_RE.match(url):
                raise ApiError("INVALID_EVIDENCE", "Enter a GitHub repository link like https://github.com/owner/repo.", 400, {**where, "field": "url"})
        elif t == "PORTFOLIO":
            if not url or not URL_RE.match(url):
                raise ApiError("INVALID_EVIDENCE", "Enter a valid http(s) link to your portfolio.", 400, {**where, "field": "url"})
        elif t == "CERTIFICATE":
            if url and not URL_RE.match(url):
                raise ApiError("INVALID_EVIDENCE", "The credential link must be a valid http(s) URL.", 400, {**where, "field": "url"})
            if not url and not item.get("file_key") and not item.get("file_ref"):
                raise ApiError("INVALID_EVIDENCE", "Attach a certificate file or add a credential link.", 400, {**where, "field": "file"})
        else:
            raise ApiError("INVALID_EVIDENCE", "Choose GitHub, Portfolio or Certificate.", 400, {**where, "field": "type"})
        return {"type": t, "url": url, "description": desc, "file_key": item.get("file_key"), "file_ref": item.get("file_ref"),
                "file_name": item.get("file_name")}


class SubmissionService:
    def __init__(self, ctx):
        self.c = ctx

    # ---------------------------------------------------------------- DTOs
    def exhibit_dto(self, s, detail=False):
        latest = self.c.scores.latest(s["id"])
        remaining = max(0, self.c.max_resubmissions() - s["resubmission_count"])
        out = {
            "id": s["id"], "title": s["title"], "skill_area": s["skill_area"], "status": s["status"],
            "date_submitted": s["date_submitted"], "resubmissions_used": s["resubmission_count"],
            "resubmission_limit": self.c.max_resubmissions(), "resubmissions_remaining": remaining,
            "can_resubmit": s["status"] == "SCORED" and remaining > 0, "moderation": s["moderation"],
            "latest": score_dto(latest),
            "evidence_types": [e["type"] for e in self.c.subs.evidence_for(s["id"])],
        }
        if s["status"] in ("PENDING", "RESUBMITTED"):
            out["message"] = "Scoring... this usually takes a few seconds."
        elif s["status"] == "QUEUED":
            out["message"] = "Your evidence is saved and will be scored shortly."
        if detail:
            out["evidence"] = [evidence_dto(e) for e in self.c.subs.evidence_for(s["id"])]
            out["history"] = [{"attempt_no": h["attempt_no"], "out_of_10": round(h["overall_score"] / 10, 1), "scored_at": h["scored_at"],
                               "sub_scores": {k: v["score"] for k, v in h["sub_scores"].items()}} for h in self.c.scores.history(s["id"])]
        return out

    def list_for_candidate(self, cid):
        return [self.exhibit_dto(s) for s in self.c.subs.list_by_candidate(cid)]

    def get_owned(self, cid, sid, detail=True):
        s = self.c.subs.find(sid)
        if not s or s["candidate_id"] != cid or s["moderation"] == "REMOVED":
            raise not_found("Exhibit")
        return self.exhibit_dto(s, detail)

    # ---------------------------------------------------------------- items + files
    def _prepare_items(self, raw_items, files):
        if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= MAX_ITEMS:
            raise ApiError("EVIDENCE_REQUIRED", f"Add between 1 and {MAX_ITEMS} pieces of evidence.", 400)
        items, uploads = [], []
        for i, raw in enumerate(raw_items):
            it = EvidenceValidator.validate(raw, i)
            key = it.pop("file_key", None)
            if key:
                fs = (files or {}).get(key)
                if not fs:
                    raise ApiError("INVALID_EVIDENCE", "The attached file is missing.", 400, {"item": i, "field": "file"})
                data, safe, ext = self.c.files.read_checked(fs)
                uploads.append((it, data, safe, ext))
            items.append(it)
        for it, data, safe, ext in uploads:           # all items valid: now persist files
            it["file_ref"], it["file_name"] = self.c.files.save(data, ext), safe
        return items

    def _assert_ref_owned(self, items, existing):
        """On resubmit, items may reuse an earlier file by ref - only if it belongs to this submission."""
        own = {e["file_ref"]: e for e in existing if e["file_ref"]}
        for it in items:
            ref = it.get("file_ref")
            if ref and ref not in own:
                raise ApiError("INVALID_EVIDENCE", "Unknown attached file.", 400)
            if ref and not it.get("file_name"):
                it["file_name"] = own[ref]["file_name"]

    # ---------------------------------------------------------------- use cases
    def submit_evidence(self, cid, title, skill_area, raw_items, files=None):
        cand = self.c.candidates.find(cid)
        if not cand or cand["user_status"] != "ACTIVE":
            raise ApiError("ACCOUNT_NOT_ALLOWED", "This account cannot submit evidence.", 403)
        title = (title or "").strip()
        if not 3 <= len(title) <= 100:
            raise ApiError("INVALID_INPUT", "Give the exhibit a title (3-100 characters).", 400, {"field": "title"})
        skill_area = skill_area or cand["field"]
        if skill_area not in FIELDS:
            raise ApiError("INVALID_FIELD", "Choose one of the listed fields.", 400, {"field": "skill_area"})
        if len(self.c.subs.list_by_candidate(cid)) >= MAX_EXHIBITS:
            raise ApiError("EXHIBIT_LIMIT", f"You can keep at most {MAX_EXHIBITS} exhibits.", 409)
        items = self._prepare_items(raw_items, files)
        sid = self.c.subs.create(cid, title, skill_area, "PENDING")
        for it in items:
            self.c.subs.add_evidence(sid, it)
        self.c.session.on_commit(lambda: self.c.app.queue.enqueue(sid))   # asynchronous scoring (NFR1)
        return self.get_owned(cid, sid)

    def resubmit(self, cid, sid, raw_items, files=None):
        s = self.c.subs.find(sid)
        if not s or s["candidate_id"] != cid or s["moderation"] == "REMOVED":
            raise not_found("Exhibit")
        if s["status"] != "SCORED":
            raise ApiError("ONLY_SCORED_CAN_RESUBMIT", "You can resubmit once the current version has been scored.", 409)
        limit = self.c.max_resubmissions()
        if s["resubmission_count"] >= limit:
            raise ApiError("RESUBMISSION_LIMIT_REACHED", f"You have used all {limit} resubmissions for this exhibit.", 409)
        existing = self.c.subs.evidence_for(sid)
        by_id = {e["id"]: e for e in existing}
        for r in raw_items if isinstance(raw_items, list) else []:   # "keep the file I uploaded before"
            if isinstance(r, dict) and r.get("keep_evidence_id"):
                e = by_id.get(r["keep_evidence_id"])
                if not e or not e["file_ref"]:
                    raise ApiError("INVALID_EVIDENCE", "The file you wanted to keep no longer exists.", 400)
                r["file_ref"], r["file_name"] = e["file_ref"], e["file_name"]
        items = self._prepare_items(raw_items, files)
        self._assert_ref_owned(items, existing)
        keep = {it["file_ref"] for it in items if it.get("file_ref")}
        old_refs = [e["file_ref"] for e in existing if e["file_ref"] and e["file_ref"] not in keep]
        self.c.subs.replace_evidence(sid, items)
        self.c.subs.update(sid, status=transition(s["status"], "RESUBMITTED"), resubmission_count=s["resubmission_count"] + 1, attempts=0, last_error=None)
        self.c.session.on_commit(lambda: [self.c.files.delete(r) for r in old_refs])
        self.c.session.on_commit(lambda: self.c.app.queue.enqueue(sid))
        return self.get_owned(cid, sid)

    # ---------------------------------------------------------------- file access
    def file_url(self, user, evidence_id):
        e = self.c.subs.find_evidence(evidence_id)
        if not e or not e["file_ref"]:
            raise not_found("File")
        s = self.c.subs.find(e["submission_id"])
        ok = False
        if user["role"] == "ADMIN":
            ok = True
        elif user["role"] == "CANDIDATE":
            ok = s["candidate_id"] == user["id"]
        elif user["role"] == "RECRUITER":  # only scored, visible exhibits
            owner = self.c.users.find(s["candidate_id"])
            ok = s["status"] == "SCORED" and s["moderation"] != "REMOVED" and owner["status"] == "ACTIVE"
        if not ok:
            raise forbidden()
        return {"url": "/api/files/" + self.c.app.tokens.issue_file_token(e["id"], e["file_ref"], e["file_name"] or "certificate"),
                "expires_in": self.c.cfg.file_url_ttl_s}


class ScoringService:
    """Runs inside the queue worker: sends evidence to the engine and stores the result (FR3, NFR5)."""

    def __init__(self, ctx):
        self.c = ctx

    def build_bundle(self, s):
        cand = self.c.candidates.find(s["candidate_id"])
        return {  # no name / e-mail: the engine scores evidence, not people
            "submission_id": s["id"], "skill_area": s["skill_area"], "title": s["title"],
            "candidate_skills": cand["skills"],
            "evidence": [{"type": e["type"], "url": e["url"], "description": e["description"], "file_name": e["file_name"]}
                         for e in self.c.subs.evidence_for(s["id"])],
        }

    def process(self, sid):
        s = self.c.subs.find(sid)
        if not s or s["moderation"] == "REMOVED" or s["status"] not in ("PENDING", "QUEUED", "RESUBMITTED"):
            return
        cfg = self.c.cfg
        try:
            result = self.c.app.scorer.evaluate(self.build_bundle(s))
        except EngineUnavailable as e:
            attempts = s["attempts"] + 1
            if attempts < cfg.max_retries:
                self.c.subs.update(sid, status=transition(s["status"], "QUEUED"), attempts=attempts, last_error=str(e)[:200])
                delay = cfg.backoff_base_s * (2 ** (attempts - 1))
                self.c.session.on_commit(lambda: self.c.app.queue.enqueue_with_delay(sid, delay))
                if s["status"] != "QUEUED":
                    self.c.app.events.emit("submission.queued", self.c, submission=s)
            else:  # give up retrying automatically; an admin can requeue
                self.c.subs.update(sid, status=transition(s["status"], "QUEUED"), attempts=attempts, last_error=str(e)[:200])
                self.c.app.events.emit("scoring.failing", self.c, submission=s, error=str(e))
            return
        except EngineError as e:
            log.error("engine rejected %s: %s", sid, e)
            self.c.subs.update(sid, status=transition(s["status"], "QUEUED"), attempts=cfg.max_retries, last_error=str(e)[:200])
            self.c.app.events.emit("scoring.failing", self.c, submission=s, error=str(e))
            return
        attempt_no = s["resubmission_count"] + 1
        self.c.scores.save(sid, result["overall"], result["sub_scores"], result["recommendations"], result["strengths"],
                           result["facts"], attempt_no, result["model_version"], result["data_quality"])
        self.c.subs.update(sid, status=transition(s["status"], "SCORED"), attempts=0, last_error=None)
        self.c.app.events.emit("submission.scored", self.c, submission=s, overall=result["overall"])
