from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..assessments_bank import FIELDS
from ..errors import ApiError, not_found
from ..repositories import parse_ts
from .auth import clean_text
from .submissions import evidence_dto, score_dto

PAGE_SIZE = 10


class SearchService:
    def __init__(self, ctx):
        self.c = ctx

    def _summaries(self, rid=None):
        """One summary per visible candidate; the headline ProofScore is their best current exhibit."""
        by = {}
        for r in self.c.scores.visible_scored_rows():
            cur = by.get(r["candidate_id"])
            r["exhibits"] = 1
            if not cur:
                by[r["candidate_id"]] = r
            else:
                n = cur["exhibits"] + 1
                if r["overall_score"] > cur["overall_score"]:
                    r["exhibits"], cur = n, r
                    by[r["candidate_id"]] = r
                else:
                    cur["exhibits"] = n
        short = self.c.shortlists.ids_for(rid) if rid else set()
        out = []
        for cid, r in by.items():
            st = self.c.assessments.required_status(cid)
            out.append({
                "candidate_id": cid, "name": r["name"], "field": r["field"], "skills": r["skills"], "bio": r["bio"],
                "top_exhibit": {"id": r["submission_id"], "title": r["title"], "skill_area": r["skill_area"], "out_of_10": round(r["overall_score"] / 10, 1)},
                "score": r["overall_score"], "exhibit_count": r["exhibits"],
                "assessment": {"status": st["status"], "verified": st["verified"], "valid_until": st["valid_until"]},
                "provisional": not st["verified"], "shortlisted": cid in short,
            })
        return out

    def find_candidates(self, rid, skill=None, field=None, min_score=0.0, verified_only=False, page=0):
        rows = self._summaries(rid)
        if field:
            rows = [r for r in rows if r["field"] == field or r["top_exhibit"]["skill_area"] == field]
        if skill:
            terms = [t.strip().lower() for t in skill.split(",") if t.strip()]
            def hit(r):
                hay = [s.lower() for s in r["skills"]] + [r["top_exhibit"]["title"].lower(), r["field"].lower()]
                return all(any(t in h for h in hay) for t in terms)
            rows = [r for r in rows if hit(r)]
        rows = [r for r in rows if r["score"] >= min_score * 10]
        if verified_only:
            rows = [r for r in rows if not r["provisional"]]
        rows.sort(key=lambda r: -r["score"])
        total = len(rows)
        if skill or field or min_score or verified_only:
            self.c.recruiters.record_search(rid, {"skill": skill or "", "field": field or "", "min_score": min_score, "verified_only": bool(verified_only)})
        return {"items": rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], "total": total, "page": page, "page_size": PAGE_SIZE}

    def visible_profile(self, rid, cid):
        cand = self.c.candidates.find(cid)
        if not cand or cand["user_status"] != "ACTIVE":
            raise not_found("Candidate")
        self.c.contacts.add_view(rid, cid)
        exhibits = []
        for s in self.c.subs.list_by_candidate(cid):
            if s["status"] != "SCORED":
                continue
            latest = self.c.scores.latest(s["id"])
            dto = score_dto(latest)
            dto.pop("recommendations")  # improvement advice is for the candidate; recruiters see the breakdown and gaps
            dto["gaps"] = [x["label"] for x in latest["recommendations"] if x["dimension"] != "evidence"][:4]
            exhibits.append({"id": s["id"], "title": s["title"], "skill_area": s["skill_area"], "moderation": s["moderation"],
                             "attempts": s["resubmission_count"] + 1, "score": dto,
                             "evidence": [evidence_dto(e) for e in self.c.subs.evidence_for(s["id"])]})
        if not exhibits:
            raise not_found("Candidate")
        st = self.c.assessments.required_status(cid)
        return {"candidate_id": cid, "name": cand["name"], "field": cand["field"], "bio": cand["bio"], "skills": cand["skills"],
                "portfolio_links": cand["portfolio_links"], "exhibits": sorted(exhibits, key=lambda e: -e["score"]["overall"]),
                "assessment": {"status": st["status"], "verified": st["verified"], "valid_until": st["valid_until"]},
                "provisional": not st["verified"], "shortlisted": self.c.shortlists.exists(rid, cid),
                "last_contacted": self.c.contacts.last_sent(rid, cid)}


class ShortlistService:
    def __init__(self, ctx):
        self.c = ctx

    def add(self, rid, cid):
        if not self.c.candidates.find(cid):
            raise not_found("Candidate")
        if not self.c.subs.exists_scored(cid):
            raise ApiError("CANDIDATE_NOT_SCORED", "You can shortlist a candidate once their evidence has been scored.", 409)
        if not self.c.shortlists.exists(rid, cid):
            self.c.shortlists.add(rid, cid)
        return {"shortlisted": True}

    def remove(self, rid, cid):
        self.c.shortlists.remove(rid, cid)
        return {"shortlisted": False}

    def list(self, rid):
        mine = {r["candidate_id"]: r["created_at"] for r in self.c.shortlists.list_for(rid)}
        items = [dict(s, shortlisted_at=mine[s["candidate_id"]]) for s in self.c.search._summaries(rid) if s["candidate_id"] in mine]
        items.sort(key=lambda s: s["shortlisted_at"], reverse=True)
        return {"items": items, "unavailable": len(mine) - len(items)}

    def contact(self, rid, cid, message):
        if not self.c.candidates.find(cid):
            raise not_found("Candidate")
        if not self.c.subs.exists_scored(cid):
            raise ApiError("CANDIDATE_NOT_SCORED", "You can contact a candidate once their evidence has been scored.", 409)
        message = clean_text(message, "message", 10, 1000)
        last = self.c.contacts.last_sent(rid, cid)
        if last and datetime.now(timezone.utc) - parse_ts(last) < timedelta(hours=1):
            raise ApiError("CONTACT_RATE_LIMIT", "You contacted this candidate recently. Please wait an hour before sending another message.", 429)
        self.c.contacts.add(rid, cid, message)
        self.c.app.events.emit("contact.sent", self.c, recruiter={"id": rid}, candidate_id=cid)
        return {"sent": True}

    def flag(self, rid, sid, reason):
        s = self.c.subs.find(sid)
        if not s or s["status"] != "SCORED" or s["moderation"] == "REMOVED":
            raise not_found("Exhibit")
        reason = clean_text(reason, "reason", 5, 300)
        self.c.subs.update(sid, moderation="FLAGGED", flag_reason=reason, flagged_by=rid)
        self.c.app.events.emit("submission.flagged", self.c, submission=s, reason=reason)
        return {"flagged": True}


class JobService:
    def __init__(self, ctx):
        self.c = ctx

    def create(self, rid, data):
        rec = self.c.recruiters.find(rid)
        title = clean_text(data.get("title"), "title", 3, 100)
        field = data.get("field")
        if field not in FIELDS:
            raise ApiError("INVALID_FIELD", "Choose one of the listed fields.", 400, {"field": "field"})
        desc = clean_text(data.get("description") or "No description provided.", "description", 3, 2000)
        loc = (data.get("location") or "").strip()[:80]
        skills = [s.strip()[:40] for s in (data.get("skills") or []) if isinstance(s, str) and s.strip()][:12]
        jid = self.c.jobs_repo.create(rid, title, rec["company"], field, loc, desc, skills)
        return {"id": jid}

    def list(self, user, field=None, q=None, mine=False):
        rows = self.c.jobs_repo.list(field=field, q=q, recruiter_id=user["id"] if mine else None)
        mine_skills = set()
        if user["role"] == "CANDIDATE":
            mine_skills = {s.lower() for s in self.c.candidates.find(user["id"])["skills"]}
        for r in rows:
            js = {s.lower() for s in r["skills"]}
            r["match"] = round(100 * len(js & mine_skills) / len(js)) if js and mine_skills else None
        if user["role"] == "CANDIDATE":
            rows.sort(key=lambda r: -(r["match"] or 0))
        return rows
