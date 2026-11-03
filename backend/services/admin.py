from __future__ import annotations

from ..errors import ApiError, forbidden, not_found
from ..scoring.client import EngineUnavailable  # noqa: F401  (re-exported for type clarity)
from .auth import clean_text


class AdminService:
    PERMS = ["MANAGE_ACCOUNTS", "MODERATE", "VIEW_AUDIT", "MANAGE_CONFIG"]

    def __init__(self, ctx):
        self.c = ctx

    def need(self, admin_id, perm):
        if perm not in self.c.admins.permissions(admin_id):
            raise forbidden(f"Your administrator role lacks the {perm} permission.")

    # ---------------------------------------------------------------- stats (FR9)
    def stats(self):
        users = {"CANDIDATE": 0, "RECRUITER": 0, "ADMIN": 0, "suspended": 0}
        for r in self.c.users.counts():
            if r["status"] == "ACTIVE":
                users[r["role"]] += r["n"]
            elif r["status"] == "SUSPENDED":
                users["suspended"] += r["n"]
        by_status = {r["status"]: r["n"] for r in self.c.subs.counts_by_status()}
        health = self.c.app.scorer.health() if hasattr(self.c.app.scorer, "health") else {"status": "unknown"}
        failing = self.c.conn.execute("SELECT COUNT(*) FROM submission WHERE status='QUEUED' AND attempts>=? AND moderation!='REMOVED'",
                                      (self.c.cfg.max_retries,)).fetchone()[0]
        flagged = self.c.conn.execute("SELECT COUNT(*) FROM submission WHERE moderation='FLAGGED'").fetchone()[0]
        return {"active_users": users, "submissions_by_status": by_status, "submissions_total": sum(by_status.values()),
                "per_day": self.c.subs.per_day(7), "queue_length": self.c.app.queue.size() if self.c.app.queue else 0,
                "unscored": sum(by_status.get(k, 0) for k in ("PENDING", "QUEUED", "RESUBMITTED")), "failing": failing,
                "flagged": flagged, "engine": health}

    # ---------------------------------------------------------------- accounts (FR8)
    def users(self, admin_id, q=None, role=None, status=None):
        self.need(admin_id, "MANAGE_ACCOUNTS")
        return self.c.users.search(q, role, status)

    def set_user_status(self, admin_id, target_id, status, reason):
        self.need(admin_id, "MANAGE_ACCOUNTS")
        if status not in ("ACTIVE", "SUSPENDED", "REMOVED"):
            raise ApiError("INVALID_INPUT", "Status must be ACTIVE, SUSPENDED or REMOVED.", 400)
        u = self.c.users.find(target_id)
        if not u:
            raise not_found("User")
        if u["id"] == admin_id or u["role"] == "ADMIN":
            raise ApiError("FORBIDDEN_TARGET", "Administrator accounts cannot be changed here.", 403)
        if status != "ACTIVE":
            reason = clean_text(reason, "reason", 3, 300)
        action = {"SUSPENDED": "SUSPEND_USER", "REMOVED": "REMOVE_USER", "ACTIVE": "RESTORE_USER"}[status]
        self.c.users.set_status(target_id, status)                       # same transaction as the audit entry
        self.c.audit_repo.record(admin_id, action, "USER", target_id, reason or "")
        return {"id": target_id, "status": status}

    # ---------------------------------------------------------------- moderation (FR8)
    def submissions(self, admin_id, moderation=None, status=None, q=None):
        self.need(admin_id, "MODERATE")
        return self.c.subs.list_admin(moderation, status, q)

    def moderate(self, admin_id, sid, action, reason):
        self.need(admin_id, "MODERATE")
        s = self.c.subs.find(sid)
        if not s:
            raise not_found("Submission")
        reason = clean_text(reason, "reason", 3, 300)
        if action == "dismiss":
            self.c.subs.update(sid, moderation="NONE", flag_reason=None, flagged_by=None)
            code = "DISMISS_FLAG"
        elif action == "remove":
            self.c.subs.update(sid, moderation="REMOVED")
            code = "REMOVE_SUBMISSION"
            self.c.app.events.emit("submission.removed", self.c, submission=s)
        elif action == "restore":
            self.c.subs.update(sid, moderation="NONE", flag_reason=None)
            code = "RESTORE_SUBMISSION"
        else:
            raise ApiError("INVALID_INPUT", "Action must be dismiss, remove or restore.", 400)
        self.c.audit_repo.record(admin_id, code, "SUBMISSION", sid, reason)
        return {"id": sid, "action": action}

    # ---------------------------------------------------------------- audit + config + queue
    def audit(self, admin_id):
        self.need(admin_id, "VIEW_AUDIT")
        return self.c.audit_repo.list()

    def get_config(self, admin_id):
        self.need(admin_id, "MANAGE_CONFIG")
        return {"MAX_RESUBMISSIONS": self.c.max_resubmissions()}

    def update_config(self, admin_id, data):
        self.need(admin_id, "MANAGE_CONFIG")
        try:
            v = int(data.get("MAX_RESUBMISSIONS"))
        except (TypeError, ValueError):
            raise ApiError("INVALID_INPUT", "MAX_RESUBMISSIONS must be a whole number.", 400)
        if not 0 <= v <= 10:
            raise ApiError("INVALID_INPUT", "MAX_RESUBMISSIONS must be between 0 and 10.", 400)
        old = self.c.max_resubmissions()
        self.c.cfg_repo.set("MAX_RESUBMISSIONS", v)
        self.c.audit_repo.record(admin_id, "UPDATE_CONFIG", "CONFIG", "MAX_RESUBMISSIONS", f"{old} -> {v}")
        return self.get_config(admin_id)

    def requeue(self, admin_id):
        self.need(admin_id, "MODERATE")
        ids = [r["id"] for r in self.c.subs.pending()]
        for sid in ids:
            self.c.subs.update(sid, attempts=0)
        self.c.session.on_commit(lambda: [self.c.app.queue.enqueue(i) for i in ids])
        self.c.audit_repo.record(admin_id, "REQUEUE_SUBMISSIONS", "QUEUE", "-", f"{len(ids)} submissions")
        return {"requeued": len(ids)}
