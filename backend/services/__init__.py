"""Service layer (business logic). Controllers call services; services call repositories."""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from .. import repositories as R


@dataclass
class AppContext:
    """Process-wide singletons shared by every request."""
    config: object
    db: object
    events: object
    tokens: object
    throttle: object
    scorer: object
    queue: object = None


class Services:
    """Per-request (or per-job) bundle: one DB session + lazily built repositories and services."""

    def __init__(self, session, app: AppContext):
        self.session, self.conn, self.app, self.cfg = session, session.conn, app, app.config

    # repositories
    @cached_property
    def users(self): return R.UserRepository(self.conn)
    @cached_property
    def candidates(self): return R.CandidateRepository(self.conn)
    @cached_property
    def recruiters(self): return R.RecruiterRepository(self.conn)
    @cached_property
    def admins(self): return R.AdminRepository(self.conn)
    @cached_property
    def subs(self): return R.SubmissionRepository(self.conn)
    @cached_property
    def scores(self): return R.ProofScoreRepository(self.conn)
    @cached_property
    def shortlists(self): return R.ShortlistRepository(self.conn)
    @cached_property
    def contacts(self): return R.ContactRepository(self.conn)
    @cached_property
    def audit_repo(self): return R.AuditRepository(self.conn)
    @cached_property
    def cfg_repo(self): return R.ConfigRepository(self.conn)
    @cached_property
    def jobs_repo(self): return R.JobRepository(self.conn)
    @cached_property
    def notes_repo(self): return R.NotificationRepository(self.conn)
    @cached_property
    def assess_repo(self): return R.AssessmentRepository(self.conn)

    # services
    @cached_property
    def auth(self):
        from .auth import AuthService
        return AuthService(self)
    @cached_property
    def profile(self):
        from .auth import ProfileService
        return ProfileService(self)
    @cached_property
    def files(self):
        from .files import FileStore
        return FileStore(self)
    @cached_property
    def submissions(self):
        from .submissions import SubmissionService
        return SubmissionService(self)
    @cached_property
    def scoring(self):
        from .submissions import ScoringService
        return ScoringService(self)
    @cached_property
    def assessments(self):
        from .assessments import AssessmentService
        return AssessmentService(self)
    @cached_property
    def search(self):
        from .recruiting import SearchService
        return SearchService(self)
    @cached_property
    def shortlist(self):
        from .recruiting import ShortlistService
        return ShortlistService(self)
    @cached_property
    def jobs(self):
        from .recruiting import JobService
        return JobService(self)
    @cached_property
    def admin(self):
        from .admin import AdminService
        return AdminService(self)
    @cached_property
    def notifications(self):
        from .notifications import NotificationService
        return NotificationService(self)

    def max_resubmissions(self) -> int:
        return int(self.cfg_repo.get("MAX_RESUBMISSIONS", self.cfg.default_max_resubmissions))
