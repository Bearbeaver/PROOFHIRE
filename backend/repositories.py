"""Data access layer. Services depend on these classes only - never on SQL (design NFR4)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


class Repo:
    def __init__(self, conn):
        self.c = conn

    def one(self, sql, args=()):
        r = self.c.execute(sql, args).fetchone()
        return dict(r) if r else None

    def all(self, sql, args=()):
        return [dict(r) for r in self.c.execute(sql, args).fetchall()]

    def run(self, sql, args=()):
        return self.c.execute(sql, args)


class UserRepository(Repo):
    def create(self, name, email, password_hash, role):
        uid = new_id()
        self.run("INSERT INTO users(id,name,email,password_hash,role,status,created_at) VALUES (?,?,?,?,?, 'ACTIVE', ?)",
                 (uid, name, email, password_hash, role, now()))
        return uid

    def find(self, uid):
        return self.one("SELECT * FROM users WHERE id=?", (uid,))

    def find_by_email(self, email):
        return self.one("SELECT * FROM users WHERE email=?", (email,))

    def set_status(self, uid, status):
        self.run("UPDATE users SET status=? WHERE id=?", (status, uid))

    def search(self, q=None, role=None, status=None, limit=200):
        sql, args = "SELECT id,name,email,role,status,created_at FROM users WHERE 1=1", []
        if q:
            sql += " AND (name LIKE ? OR email LIKE ?)"
            args += [f"%{q}%", f"%{q}%"]
        if role:
            sql += " AND role=?"
            args.append(role)
        if status:
            sql += " AND status=?"
            args.append(status)
        return self.all(sql + " ORDER BY created_at DESC LIMIT ?", (*args, limit))

    def counts(self):
        return self.all("SELECT role, status, COUNT(*) AS n FROM users GROUP BY role, status")

    def admin_ids(self):
        return [r["id"] for r in self.all("SELECT id FROM users WHERE role='ADMIN' AND status='ACTIVE'")]


class CandidateRepository(Repo):
    def create(self, uid, field):
        self.run("INSERT INTO candidate(id, field) VALUES (?,?)", (uid, field))

    def find(self, cid):
        r = self.one("""SELECT c.*, u.name, u.email, u.status AS user_status, u.created_at
                        FROM candidate c JOIN users u ON u.id=c.id WHERE c.id=?""", (cid,))
        if r:
            r["skills"], r["portfolio_links"] = json.loads(r["skills"]), json.loads(r["portfolio_links"])
        return r

    def update_profile(self, cid, bio, skills, links, field):
        self.run("UPDATE candidate SET bio=?, skills=?, portfolio_links=?, field=? WHERE id=?",
                 (bio, json.dumps(skills), json.dumps(links), field, cid))


class RecruiterRepository(Repo):
    def create(self, uid, company):
        self.run("INSERT INTO recruiter(id, company) VALUES (?,?)", (uid, company))

    def find(self, rid):
        r = self.one("""SELECT r.*, u.name, u.email FROM recruiter r JOIN users u ON u.id=r.id WHERE r.id=?""", (rid,))
        if r:
            r["search_history"] = json.loads(r["search_history"])
        return r

    def record_search(self, rid, entry: dict):
        r = self.find(rid)
        hist = [h for h in r["search_history"] if h != entry]
        hist.insert(0, entry)
        self.run("UPDATE recruiter SET search_history=? WHERE id=?", (json.dumps(hist[:8]), rid))


class AdminRepository(Repo):
    def create(self, uid, permissions):
        self.run("INSERT INTO admin(id, permissions) VALUES (?,?)", (uid, json.dumps(permissions)))

    def permissions(self, aid):
        r = self.one("SELECT permissions FROM admin WHERE id=?", (aid,))
        return json.loads(r["permissions"]) if r else []


class SubmissionRepository(Repo):
    EDITABLE = {"status", "resubmission_count", "attempts", "last_error", "moderation", "flag_reason", "flagged_by", "title", "skill_area"}

    def create(self, candidate_id, title, skill_area, status="PENDING"):
        sid, ts = new_id(), now()
        self.run("""INSERT INTO submission(id,candidate_id,title,skill_area,date_submitted,updated_at,status)
                    VALUES (?,?,?,?,?,?,?)""", (sid, candidate_id, title, skill_area, ts, ts, status))
        return sid

    def find(self, sid):
        return self.one("SELECT * FROM submission WHERE id=?", (sid,))

    def update(self, sid, **fields):
        bad = set(fields) - self.EDITABLE
        if bad:
            raise ValueError(f"not editable: {bad}")
        sets = ", ".join(f"{k}=?" for k in fields) + ", updated_at=?"
        self.run(f"UPDATE submission SET {sets} WHERE id=?", (*fields.values(), now(), sid))

    def list_by_candidate(self, cid):
        return self.all("SELECT * FROM submission WHERE candidate_id=? AND moderation!='REMOVED' ORDER BY date_submitted DESC", (cid,))

    def add_evidence(self, sid, item):
        eid = new_id()
        self.run("INSERT INTO evidence(id,submission_id,type,url,file_ref,file_name,description) VALUES (?,?,?,?,?,?,?)",
                 (eid, sid, item["type"], item.get("url"), item.get("file_ref"), item.get("file_name"), item.get("description", "")))
        return eid

    def replace_evidence(self, sid, items):
        self.run("DELETE FROM evidence WHERE submission_id=?", (sid,))
        for it in items:
            self.add_evidence(sid, it)

    def evidence_for(self, sid):
        return self.all("SELECT * FROM evidence WHERE submission_id=? ORDER BY rowid", (sid,))

    def find_evidence(self, eid):
        return self.one("SELECT * FROM evidence WHERE id=?", (eid,))

    def exists_scored(self, cid):
        return bool(self.one("SELECT 1 AS x FROM submission WHERE candidate_id=? AND status='SCORED' AND moderation!='REMOVED' LIMIT 1", (cid,)))

    def pending(self):
        return self.all("SELECT id FROM submission WHERE status IN ('PENDING','QUEUED','RESUBMITTED') AND moderation!='REMOVED' ORDER BY date_submitted")

    def counts_by_status(self):
        return self.all("SELECT status, COUNT(*) AS n FROM submission WHERE moderation!='REMOVED' GROUP BY status")

    def per_day(self, days=7):
        start = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date().isoformat()
        rows = {r["d"]: r["n"] for r in self.all(
            "SELECT substr(date_submitted,1,10) AS d, COUNT(*) AS n FROM submission WHERE substr(date_submitted,1,10) >= ? GROUP BY d", (start,))}
        out = []
        for i in range(days):
            d = (datetime.now(timezone.utc) - timedelta(days=days - 1 - i)).date().isoformat()
            out.append({"date": d, "count": rows.get(d, 0)})
        return out

    def list_admin(self, moderation=None, status=None, q=None, limit=200):
        sql = """SELECT s.*, u.name AS candidate_name, u.email AS candidate_email
                 FROM submission s JOIN users u ON u.id=s.candidate_id WHERE 1=1"""
        args = []
        if moderation:
            sql += " AND s.moderation=?"
            args.append(moderation)
        if status:
            sql += " AND s.status=?"
            args.append(status)
        if q:
            sql += " AND (s.title LIKE ? OR u.name LIKE ?)"
            args += [f"%{q}%", f"%{q}%"]
        return self.all(sql + " ORDER BY s.date_submitted DESC LIMIT ?", (*args, limit))


class ProofScoreRepository(Repo):
    def save(self, sid, overall, sub_scores, recommendations, strengths, facts, attempt_no, model_version, data_quality):
        pid = new_id()
        self.run("""INSERT INTO proof_score(id,submission_id,overall_score,sub_scores,recommendations,strengths,facts,attempt_no,scored_at,model_version,data_quality)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                 (pid, sid, overall, json.dumps(sub_scores), json.dumps(recommendations), json.dumps(strengths),
                  json.dumps(facts), attempt_no, now(), model_version, data_quality))
        return pid

    @staticmethod
    def _inflate(r):
        if r:
            for k in ("sub_scores", "recommendations", "strengths", "facts"):
                r[k] = json.loads(r[k])
        return r

    def latest(self, sid):
        return self._inflate(self.one("SELECT * FROM proof_score WHERE submission_id=? ORDER BY attempt_no DESC LIMIT 1", (sid,)))

    def history(self, sid):
        return [self._inflate(r) for r in self.all("SELECT * FROM proof_score WHERE submission_id=? ORDER BY attempt_no", (sid,))]

    def visible_scored_rows(self):
        """Latest score of every SCORED, non-removed exhibit of an ACTIVE candidate (recruiter search source)."""
        rows = self.all("""
            SELECT c.id AS candidate_id, u.name, c.bio, c.skills, c.field,
                   s.id AS submission_id, s.title, s.skill_area, ps.overall_score, ps.scored_at
            FROM candidate c
            JOIN users u ON u.id = c.id AND u.status = 'ACTIVE'
            JOIN submission s ON s.candidate_id = c.id AND s.status = 'SCORED' AND s.moderation != 'REMOVED'
            JOIN proof_score ps ON ps.submission_id = s.id
                 AND ps.attempt_no = (SELECT MAX(attempt_no) FROM proof_score WHERE submission_id = s.id)""")
        for r in rows:
            r["skills"] = json.loads(r["skills"])
        return rows


class ShortlistRepository(Repo):
    def exists(self, rid, cid):
        return bool(self.one("SELECT 1 AS x FROM shortlist WHERE recruiter_id=? AND candidate_id=?", (rid, cid)))

    def add(self, rid, cid):
        self.run("INSERT INTO shortlist(id,recruiter_id,candidate_id,created_at) VALUES (?,?,?,?)", (new_id(), rid, cid, now()))

    def remove(self, rid, cid):
        self.run("DELETE FROM shortlist WHERE recruiter_id=? AND candidate_id=?", (rid, cid))

    def ids_for(self, rid):
        return {r["candidate_id"] for r in self.all("SELECT candidate_id FROM shortlist WHERE recruiter_id=?", (rid,))}

    def list_for(self, rid):
        return self.all("SELECT candidate_id, created_at FROM shortlist WHERE recruiter_id=? ORDER BY created_at DESC", (rid,))


class ContactRepository(Repo):
    def add(self, rid, cid, message):
        self.run("INSERT INTO contact_request(id,recruiter_id,candidate_id,message,sent_at) VALUES (?,?,?,?,?)",
                 (new_id(), rid, cid, message, now()))

    def last_sent(self, rid, cid):
        r = self.one("SELECT sent_at FROM contact_request WHERE recruiter_id=? AND candidate_id=? ORDER BY sent_at DESC LIMIT 1", (rid, cid))
        return r["sent_at"] if r else None

    def sent_by(self, rid):
        return self.all("""SELECT cr.id, cr.message, cr.sent_at, cr.candidate_id, u.name AS candidate_name, c.field
                           FROM contact_request cr JOIN users u ON u.id=cr.candidate_id JOIN candidate c ON c.id=cr.candidate_id
                           WHERE cr.recruiter_id=? ORDER BY cr.sent_at DESC""", (rid,))

    def add_view(self, rid, cid):
        self.run("INSERT INTO profile_view(id,recruiter_id,candidate_id,viewed_at) VALUES (?,?,?,?)", (new_id(), rid, cid, now()))

    def views_today(self, cid):
        r = self.one("SELECT COUNT(*) AS n FROM profile_view WHERE candidate_id=? AND viewed_at>=?", (cid, now()[:10]))
        return r["n"] if r else 0

    def for_candidate(self, cid):
        return self.all("""SELECT cr.id, cr.message, cr.sent_at, u.name AS recruiter_name, r.company
                           FROM contact_request cr JOIN users u ON u.id=cr.recruiter_id JOIN recruiter r ON r.id=cr.recruiter_id
                           WHERE cr.candidate_id=? ORDER BY cr.sent_at DESC""", (cid,))


class AuditRepository(Repo):
    def record(self, actor_id, action, target_type, target_id, detail=""):
        self.run("INSERT INTO audit_log(id,actor_id,action,target_type,target_id,detail,timestamp) VALUES (?,?,?,?,?,?,?)",
                 (new_id(), actor_id, action, target_type, target_id, detail, now()))

    def list(self, limit=200):
        return self.all("""SELECT a.*, u.name AS actor_name FROM audit_log a JOIN users u ON u.id=a.actor_id
                           ORDER BY a.timestamp DESC, a.rowid DESC LIMIT ?""", (limit,))


class ConfigRepository(Repo):
    def get(self, key, default=None):
        r = self.one("SELECT value FROM system_config WHERE key=?", (key,))
        return r["value"] if r else default

    def set(self, key, value):
        self.run("INSERT INTO system_config(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    def all(self):
        return {r["key"]: r["value"] for r in super().all("SELECT key,value FROM system_config")}


class JobRepository(Repo):
    def create(self, rid, title, company, field, location, description, skills):
        jid = new_id()
        self.run("INSERT INTO job(id,recruiter_id,title,company,field,location,description,skills,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                 (jid, rid, title, company, field, location, description, json.dumps(skills), now()))
        return jid

    def list(self, field=None, q=None, recruiter_id=None):
        sql, args = "SELECT * FROM job WHERE 1=1", []
        if field:
            sql += " AND field=?"
            args.append(field)
        if recruiter_id:
            sql += " AND recruiter_id=?"
            args.append(recruiter_id)
        if q:
            sql += " AND (title LIKE ? OR company LIKE ? OR description LIKE ?)"
            args += [f"%{q}%"] * 3
        rows = self.all(sql + " ORDER BY created_at DESC LIMIT 100", args)
        for r in rows:
            r["skills"] = json.loads(r["skills"])
        return rows


class NotificationRepository(Repo):
    def add(self, uid, kind, message, link=None):
        self.run("INSERT INTO notification(id,user_id,kind,message,link,created_at) VALUES (?,?,?,?,?,?)", (new_id(), uid, kind, message, link, now()))

    def list(self, uid, limit=30):
        return self.all("SELECT id,kind,message,link,created_at,is_read FROM notification WHERE user_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?", (uid, limit))

    def unread(self, uid):
        return self.one("SELECT COUNT(*) AS n FROM notification WHERE user_id=? AND is_read=0", (uid,))["n"]

    def mark_read(self, uid, ids=None):
        if ids:
            marks = ",".join("?" * len(ids))
            self.run(f"UPDATE notification SET is_read=1 WHERE user_id=? AND id IN ({marks})", (uid, *ids))
        else:
            self.run("UPDATE notification SET is_read=1 WHERE user_id=?", (uid,))


class AssessmentRepository(Repo):
    def add(self, cid, field, correct, total, passed, valid_until):
        self.run("INSERT INTO assessment_attempt(id,candidate_id,field,correct,total,passed,taken_at,valid_until) VALUES (?,?,?,?,?,?,?,?)",
                 (new_id(), cid, field, correct, total, int(passed), now(), valid_until))

    def latest_passed(self, cid, field):
        return self.one("SELECT * FROM assessment_attempt WHERE candidate_id=? AND field=? AND passed=1 ORDER BY taken_at DESC, rowid DESC LIMIT 1", (cid, field))

    def last_attempt(self, cid, field):
        return self.one("SELECT * FROM assessment_attempt WHERE candidate_id=? AND field=? ORDER BY taken_at DESC, rowid DESC LIMIT 1", (cid, field))
