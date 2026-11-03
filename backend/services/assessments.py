"""Standardised assessments. Passing the assessment for the candidate's own field keeps their ProofScore verified."""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from ..assessments_bank import BANK, DURATION_MIN, FIELDS, bank_for
from ..errors import ApiError
from ..repositories import now, parse_ts


class AssessmentService:
    def __init__(self, ctx):
        self.c = ctx

    def pass_mark(self, field):
        return math.ceil(len(bank_for(field)) * self.c.cfg.assessment_pass_ratio)

    def status_for(self, cid, field):
        passed = self.c.assess_repo.latest_passed(cid, field)
        last = self.c.assess_repo.last_attempt(cid, field)
        out = {"field": field, "status": "not_started", "valid_until": None, "days_left": None,
               "last": ({"correct": last["correct"], "total": last["total"], "passed": bool(last["passed"]), "taken_at": last["taken_at"]} if last else None)}
        if passed:
            until = parse_ts(passed["valid_until"])
            days = (until - datetime.now(timezone.utc)).days
            out["valid_until"], out["days_left"] = passed["valid_until"], days
            if until < datetime.now(timezone.utc):
                out["status"] = "expired"
            elif days <= self.c.cfg.assessment_due_soon_days:
                out["status"] = "due_soon"
            else:
                out["status"] = "valid"
        elif last:
            out["status"] = "failed"
        return out

    def required_status(self, cid):
        cand = self.c.candidates.find(cid)
        s = self.status_for(cid, cand["field"])
        s["verified"] = s["status"] in ("valid", "due_soon")
        return s

    def overview(self, cid):
        cand = self.c.candidates.find(cid)
        items = []
        for f in FIELDS:
            st = self.status_for(cid, f)
            st.update({"required": f == cand["field"], "questions": len(bank_for(f)), "duration_min": DURATION_MIN, "pass_mark": self.pass_mark(f)})
            items.append(st)
        items.sort(key=lambda x: not x["required"])
        return items

    def start(self, cid, field):
        if field not in FIELDS:
            raise ApiError("INVALID_FIELD", "Unknown assessment.", 404)
        qs = [{"id": q["id"], "q": q["q"], "options": q["options"]} for q in bank_for(field)]
        random.shuffle(qs)
        return {"field": field, "duration_min": DURATION_MIN, "pass_mark": self.pass_mark(field), "questions": qs}

    def submit(self, cid, field, answers):
        if field not in FIELDS:
            raise ApiError("INVALID_FIELD", "Unknown assessment.", 404)
        if not isinstance(answers, dict):
            raise ApiError("INVALID_INPUT", "Answers must be an object of question id to option index.", 400)
        correct, missed = 0, set()
        for q in bank_for(field):
            if answers.get(q["id"]) == q["answer"]:
                correct += 1
            else:
                missed.add(q["topic"])
        total = len(bank_for(field))
        passed = correct >= self.pass_mark(field)
        until = (datetime.now(timezone.utc) + timedelta(days=self.c.cfg.assessment_valid_days)).isoformat(timespec="seconds") if passed else None
        self.c.assess_repo.add(cid, field, correct, total, passed, until)
        self.c.app.events.emit("assessment.completed", self.c, candidate_id=cid, field=field, passed=passed, correct=correct, total=total)
        return {"field": field, "correct": correct, "total": total, "passed": passed, "pass_mark": self.pass_mark(field),
                "valid_until": until, "topics_to_review": sorted(missed) if not passed or missed else []}
