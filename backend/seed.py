"""Demo data. Created only when PROOFHIRE_SEED_DEMO is on (default) and the database is empty.

ALL DEMO ACCOUNTS USE THE PASSWORD 'demo1234' - set PROOFHIRE_SEED_DEMO=0 for any real deployment.
Scores here are hand-written illustrations (the fictional people and repositories do not exist);
anything submitted through the app is scored by the real engine.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .repositories import new_id, now
from .scoring.client import DIMENSIONS
from .security import hash_password

DEMO_PASSWORD = "demo1234"

REC = {
    "testing": "Add automated unit tests for the core logic, including failure paths.",
    "documentation": "Expand the README and document architectural decisions.",
    "code_quality": "Add a linter configuration and split large modules.",
    "impact": "Deploy a live demo and link it from the repository.",
    "complexity": "Extend the project with a harder problem such as concurrency or persistence.",
    "relevance": "State the target skills explicitly in the README and repository topics.",
    "technical_quality": "Add CI and a dependency manifest so the project builds reproducibly.",
}
PATTERNS = {
    "strong": [0.8, 0.9, 0.7, 0.8, 0.75, 0.7, 0.55],
    "weak_tests": [0.7, 0.8, 0.6, 0.55, 0.5, 0.3, 0.4],
    "docs_light": [0.75, 0.75, 0.6, 0.7, 0.35, 0.6, 0.4],
    "beginner": [0.5, 0.45, 0.3, 0.3, 0.3, 0.1, 0.25],
}


def _ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def _scores(total10, pattern):
    raw = [PATTERNS[pattern][i] * mx for i, (_k, _l, mx) in enumerate(DIMENSIONS)]
    scale = total10 / sum(raw)
    return {k: {"score": round(min(mx, raw[i] * scale), 2), "max": mx} for i, (k, _l, mx) in enumerate(DIMENSIONS)}


def _add_score(sv, sid, total10, pattern, attempt, days_ago, quality="full"):
    subs = _scores(total10, pattern)
    weakest = sorted(subs, key=lambda k: subs[k]["score"] / subs[k]["max"])[:3]
    recs = [{"dimension": k, "label": next(l for kk, l, _ in DIMENSIONS if kk == k), "text": REC[k],
             "potential_gain": round((subs[k]["max"] - subs[k]["score"]) * 0.6, 1)} for k in weakest]
    strongest = sorted(subs, key=lambda k: -subs[k]["score"] / subs[k]["max"])[:2]
    strengths = [f"{next(l for kk, l, _ in DIMENSIONS if kk == k)}: strong ({subs[k]['score']:.1f}/{subs[k]['max']:g})." for k in strongest]
    pid = sv.scores.save(sid, round(sum(v["score"] for v in subs.values()) * 10, 1), subs, recs, strengths,
                         ["Demo data: hand-written illustration, not produced by the engine."], attempt, "demo-seed", quality)
    sv.conn.execute("UPDATE proof_score SET scored_at=? WHERE id=?", (_ago(days_ago), pid))


def _exhibit(sv, cid, title, field, items, history, resub=0, moderation="NONE", days=30):
    sid = sv.subs.create(cid, title, field, "SCORED")
    for it in items:
        sv.subs.add_evidence(sid, it)
    for i, (total, pattern, d) in enumerate(history, 1):
        _add_score(sv, sid, total, pattern, i, d)
    sv.conn.execute("UPDATE submission SET resubmission_count=?, moderation=?, date_submitted=? WHERE id=?", (resub, moderation, _ago(days), sid))
    return sid


def _assessment(sv, cid, field, days_ago, passed=True, correct=7, total=8):
    taken = _ago(days_ago)
    until = (datetime.fromisoformat(taken) + timedelta(days=sv.cfg.assessment_valid_days)).isoformat(timespec="seconds") if passed else None
    sv.conn.execute("""INSERT INTO assessment_attempt(id,candidate_id,field,correct,total,passed,taken_at,valid_until)
                       VALUES (?,?,?,?,?,?,?,?)""", (new_id(), cid, field, correct, total, int(passed), taken, until))


def seed_demo(sv):
    pw = hash_password(DEMO_PASSWORD)

    def user(name, email, role):
        return sv.users.create(name, email, pw, role)

    admin = user("Ada Admin", "admin@proofhire.dev", "ADMIN")
    sv.admins.create(admin, ["MANAGE_ACCOUNTS", "MODERATE", "VIEW_AUDIT", "MANAGE_CONFIG"])
    nova = user("Nova Talent", "nova@techcorp.com", "RECRUITER")
    sv.recruiters.create(nova, "TechCorp")
    sam = user("Sam Okafor", "sam@nimbuslabs.io", "RECRUITER")
    sv.recruiters.create(sam, "Nimbus Labs")

    people = [
        ("Alex Chen", "alex.chen@proofhire.dev", "Backend Engineering", "Backend developer who likes queues, retries and boring reliability.",
         ["Go", "gRPC", "Distributed systems", "PostgreSQL", "Docker"]),
        ("Priya Patel", "priya@example.com", "Frontend Engineering", "Front-end engineer focused on realtime and accessible interfaces.",
         ["React", "TypeScript", "WebSockets", "Accessibility"]),
        ("Marcus Webb", "marcus@example.com", "Data & ML Engineering", "Data engineer building streaming pipelines.",
         ["Python", "Kafka", "Airflow", "SQL"]),
        ("Sofia Reyes", "sofia@example.com", "Backend Engineering", "Full-stack engineer who ships APIs with tests.",
         ["Node.js", "PostgreSQL", "Docker", "REST", "TypeScript"]),
        ("Daniel Kim", "daniel@example.com", "Data & ML Engineering", "ML engineer interested in on-device inference.",
         ["PyTorch", "Python", "CoreML", "Computer vision"]),
        ("Thandi Mokoena", "thandi@example.com", "Frontend Engineering", "Self-taught front-end developer.",
         ["HTML", "CSS", "JavaScript"]),
    ]
    ids = {}
    for name, email, field, bio, skills in people:
        cid = user(name, email, "CANDIDATE")
        sv.candidates.create(cid, field)
        sv.candidates.update_profile(cid, bio, skills, [], field)
        ids[name] = cid

    gh = lambda repo, d="": {"type": "GITHUB", "url": f"https://github.com/{repo}", "description": d}
    alex = ids["Alex Chen"]
    _exhibit(sv, alex, "Queuely - Distributed Task Queue in Go", "Backend Engineering",
             [gh("alexchen/queuely", "Task queue with worker pools, retries and a dead-letter queue.")],
             [(5.4, "weak_tests", 40), (6.2, "weak_tests", 12)], resub=1, days=45)
    _exhibit(sv, alex, "Personal engineering blog", "Backend Engineering",
             [{"type": "PORTFOLIO", "url": "https://alexchen.dev", "description": "Write-ups on queues and reliability."}],
             [(5.1, "docs_light", 2)], days=3)
    _assessment(sv, alex, "Backend Engineering", days_ago=sv.cfg.assessment_valid_days - 9)   # expires in 9 days -> banner

    _exhibit(sv, ids["Priya Patel"], "Loomly - Realtime Design Canvas", "Frontend Engineering",
             [gh("priyapatel/loomly", "Collaborative canvas with React and WebSockets.")], [(6.9, "strong", 5)], days=6)
    _assessment(sv, ids["Priya Patel"], "Frontend Engineering", 30)

    _exhibit(sv, ids["Marcus Webb"], "Streamline - Kafka ETL Pipeline", "Data & ML Engineering",
             [gh("marcuswebb/streamline", "Kafka ETL with Airflow DAGs.")], [(3.9, "weak_tests", 25)], days=50)
    _assessment(sv, ids["Marcus Webb"], "Data & ML Engineering", sv.cfg.assessment_valid_days + 20)   # expired -> provisional

    sofia = ids["Sofia Reyes"]
    _exhibit(sv, sofia, "Ledgerly - Personal Finance API", "Backend Engineering",
             [gh("sofiareyes/ledgerly", "REST API with Node, PostgreSQL and JWT auth.")], [(6.8, "strong", 20), (7.3, "strong", 5)], resub=1, days=70)
    _exhibit(sv, sofia, "AWS Certified Developer", "Backend Engineering",
             [{"type": "CERTIFICATE", "url": "https://www.credly.com/badges/demo-aws-developer", "description": "AWS Certified Developer - Associate"}],
             [(5.6, "docs_light", 0)], days=1)
    _assessment(sv, sofia, "Backend Engineering", 15)

    _exhibit(sv, ids["Daniel Kim"], "VisionKit - On-device Image Classifier", "Data & ML Engineering",
             [gh("danielkim/visionkit", "PyTorch classifier exported to CoreML.")], [(5.8, "weak_tests", 4)], days=5)
    _assessment(sv, ids["Daniel Kim"], "Data & ML Engineering", 60)

    thandi = _exhibit(sv, ids["Thandi Mokoena"], "Portfolio redesign", "Frontend Engineering",
                      [{"type": "PORTFOLIO", "url": "https://thandi.example.com", "description": "My redesigned portfolio site."}],
                      [(4.4, "beginner", 1)], days=2, moderation="FLAGGED")
    sv.subs.update(thandi, flag_reason="Portfolio text looks copied from a public template.", flagged_by=nova)

    sv.shortlists.add(nova, sofia)
    sv.shortlists.add(nova, ids["Priya Patel"])
    sv.contacts.add(sam, alex, "Hi Alex - we are hiring a backend engineer and your Queuely project caught our eye. Open to a chat?")
    sv.notes_repo.add(alex, "CONTACT_REQUEST", "Sam Okafor from Nimbus Labs would like to contact you.", "#/candidate/messages")

    jobs = [
        (nova, "Backend Engineer (Go)", "TechCorp", "Backend Engineering", "Remote - Africa", "Build queue-based services in Go.", ["Go", "gRPC", "PostgreSQL"]),
        (nova, "Frontend Engineer", "TechCorp", "Frontend Engineering", "Cape Town", "Own our design-system components.", ["React", "TypeScript", "Accessibility"]),
        (sam, "Platform Engineer", "Nimbus Labs", "Backend Engineering", "Johannesburg", "Reliability and developer tooling.", ["Docker", "Distributed systems", "Go"]),
        (sam, "Data Engineer", "Nimbus Labs", "Data & ML Engineering", "Remote", "Streaming pipelines on Kafka.", ["Kafka", "Python", "SQL"]),
        (sam, "Junior Web Developer", "Nimbus Labs", "Frontend Engineering", "Durban", "Learn on the job with mentoring.", ["HTML", "CSS", "JavaScript"]),
    ]
    for rid, title, company, field, loc, desc, skills in jobs:
        sv.jobs_repo.create(rid, title, company, field, loc, desc, skills)
