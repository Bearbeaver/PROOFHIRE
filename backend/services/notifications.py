"""NotificationService: Observer that turns domain events into in-app notifications (design Section 5.3)."""
from __future__ import annotations


class NotificationService:
    def __init__(self, ctx):
        self.c = ctx

    def list(self, uid):
        return {"items": self.c.notes_repo.list(uid), "unread": self.c.notes_repo.unread(uid)}

    def mark_read(self, uid, ids=None):
        self.c.notes_repo.mark_read(uid, ids)


def register_handlers(events):
    def scored(ctx, submission, overall):
        ctx.notes_repo.add(submission["candidate_id"], "SCORE_READY",
                           f"“{submission['title']}” was scored {overall / 10:.1f}/10.", f"#/candidate/exhibit/{submission['id']}")

    def queued(ctx, submission):
        ctx.notes_repo.add(submission["candidate_id"], "QUEUED",
                           f"The scoring engine is busy. “{submission['title']}” is saved and will be scored shortly.",
                           f"#/candidate/exhibit/{submission['id']}")

    def failing(ctx, submission, error):
        for aid in ctx.users.admin_ids():
            ctx.notes_repo.add(aid, "SCORING_FAILING", f"Scoring keeps failing for “{submission['title']}” ({error[:80]}).", "#/admin/dashboard")

    def contact(ctx, recruiter, candidate_id):
        r = ctx.recruiters.find(recruiter["id"])
        ctx.notes_repo.add(candidate_id, "CONTACT_REQUEST", f"{r['name']} from {r['company']} would like to contact you.", "#/candidate/messages")

    def flagged(ctx, submission, reason):
        for aid in ctx.users.admin_ids():
            ctx.notes_repo.add(aid, "SUBMISSION_FLAGGED", f"“{submission['title']}” was flagged: {reason[:80]}", "#/admin/registers")

    def removed(ctx, submission):
        ctx.notes_repo.add(submission["candidate_id"], "SUBMISSION_REMOVED", f"“{submission['title']}” was removed by a moderator.", "#/candidate/portfolio")

    def assessed(ctx, candidate_id, field, passed, correct, total):
        msg = (f"You passed the {field} assessment ({correct}/{total}). Your ProofScore stays verified." if passed
               else f"You scored {correct}/{total} on the {field} assessment. You can retake it.")
        ctx.notes_repo.add(candidate_id, "ASSESSMENT", msg, "#/candidate/assessments")

    for name, fn in (("submission.scored", scored), ("submission.queued", queued), ("scoring.failing", failing),
                     ("contact.sent", contact), ("submission.flagged", flagged), ("submission.removed", removed),
                     ("assessment.completed", assessed)):
        events.subscribe(name, fn)
