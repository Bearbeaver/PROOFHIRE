"""Backend tests. Run:  python -m unittest discover -s tests -v"""
import io
import json
import shutil
import tempfile
import time
import unittest

from backend.app import create_app
from backend.assessments_bank import BANK
from backend.config import Config
from backend.scoring.client import EngineError, EngineUnavailable, MockProofScoreClient

GH = {"type": "GITHUB", "url": "https://github.com/demo-user/todo-list", "description": "demo"}


class Base(unittest.TestCase):
    scorer = None
    cfg_kwargs = {}

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ph_test_")
        cfg = Config(instance_dir=self.dir, scorer="mock", backoff_base_s=0.05, **self.cfg_kwargs)
        self.scorer = self.scorer or MockProofScoreClient()
        self.app = create_app(cfg, scorer=self.scorer)
        self.ctx = self.app.extensions["proofhire"]
        self.c = self.app.test_client()

    def tearDown(self):
        self.ctx.queue.stop()
        time.sleep(0.2)
        shutil.rmtree(self.dir, ignore_errors=True)

    def call(self, method, path, tok=None, **kw):
        h = {"Authorization": f"Bearer {tok}"} if tok else {}
        r = getattr(self.c, method)(path, headers=h, **kw)
        return r.status_code, (r.get_json(silent=True) if r.is_json else r.data)

    def demo(self, role):
        return self.call("post", "/api/auth/demo", json={"role": role})[1]["token"]

    def drain(self):
        self.assertTrue(self.ctx.queue.drain(10), "queue did not drain")

    def submit(self, tok, items=None, title="My exhibit", area="Backend Engineering"):
        s, d = self.call("post", "/api/candidate/submissions", tok, json={"title": title, "skill_area": area, "items": items or [GH]})
        self.assertEqual(s, 201, d)
        return d["id"]

    def new_candidate(self, email="new@example.com", field="Backend Engineering"):
        s, d = self.call("post", "/api/auth/register", json={"name": "New Person", "email": email, "password": "longenough1", "role": "CANDIDATE", "field": field})
        self.assertEqual(s, 201, d)
        return d["token"]


class TestAuth(Base):
    def test_register_login_and_validation(self):
        tok = self.new_candidate()
        self.assertEqual(self.call("get", "/api/auth/me", tok)[1]["user"]["role"], "CANDIDATE")
        s, d = self.call("post", "/api/auth/register", json={"name": "A", "email": "new@example.com", "password": "longenough1", "role": "CANDIDATE"})
        self.assertEqual(s, 400)                                    # name too short
        s, d = self.call("post", "/api/auth/register", json={"name": "Again Same", "email": "NEW@example.com", "password": "longenough1", "role": "CANDIDATE"})
        self.assertEqual((s, d["error"]["code"]), (409, "EMAIL_TAKEN"))
        self.assertEqual(self.call("post", "/api/auth/register", json={"name": "Bad Pw", "email": "b@x.io", "password": "short", "role": "CANDIDATE"})[0], 400)
        self.assertEqual(self.call("post", "/api/auth/register", json={"name": "Evil Admin", "email": "e@x.io", "password": "longenough1", "role": "ADMIN"})[0], 400)
        self.assertEqual(self.call("post", "/api/auth/login", json={"email": "new@example.com", "password": "longenough1"})[0], 200)

    def test_password_is_hashed_not_stored(self):
        self.new_candidate()
        with self.ctx.db.session(False) as s:
            h = s.conn.execute("SELECT password_hash FROM users WHERE email='new@example.com'").fetchone()[0]
        self.assertTrue(h.startswith("scrypt:"))
        self.assertNotIn("longenough1", h)

    def test_login_throttle(self):
        for _ in range(5):
            self.assertEqual(self.call("post", "/api/auth/login", json={"email": "alex.chen@proofhire.dev", "password": "wrong-pass"})[0], 401)
        s, d = self.call("post", "/api/auth/login", json={"email": "alex.chen@proofhire.dev", "password": "demo1234"})
        self.assertEqual((s, d["error"]["code"]), (429, "TOO_MANY_ATTEMPTS"))

    def test_tokens(self):
        self.assertEqual(self.call("get", "/api/auth/me", "garbage.token.value-garbage")[0], 401)
        self.assertEqual(self.call("get", "/api/auth/me")[0], 401)


class TestRBAC(Base):
    def test_roles_are_isolated(self):
        cand, rec, adm = self.demo("CANDIDATE"), self.demo("RECRUITER"), self.demo("ADMIN")
        self.assertEqual(self.call("get", "/api/candidate/profile", rec)[0], 403)
        self.assertEqual(self.call("get", "/api/recruiter/candidates", cand)[0], 403)
        self.assertEqual(self.call("get", "/api/admin/stats", cand)[0], 403)
        self.assertEqual(self.call("get", "/api/admin/stats", rec)[0], 403)
        self.assertEqual(self.call("get", "/api/admin/stats", adm)[0], 200)
        self.assertEqual(self.call("post", "/api/jobs", cand, json={"title": "x"})[0], 403)

    def test_candidate_cannot_read_others_exhibits(self):
        alex = self.demo("CANDIDATE")
        other = self.new_candidate()
        sid = self.call("get", "/api/candidate/submissions", alex)[1][0]["id"]
        self.assertEqual(self.call("get", f"/api/candidate/submissions/{sid}", other)[0], 404)
        self.assertEqual(self.call("post", f"/api/candidate/submissions/{sid}/resubmit", other, json={"items": [GH]})[0], 404)

    def test_suspended_user_is_rejected_at_token_validation(self):
        adm, cand = self.demo("ADMIN"), self.demo("CANDIDATE")
        uid = self.call("get", "/api/auth/me", cand)[1]["user"]["id"]
        self.assertEqual(self.call("post", f"/api/admin/users/{uid}/status", adm, json={"status": "SUSPENDED", "reason": "test"})[0], 200)
        s, d = self.call("get", "/api/candidate/profile", cand)
        self.assertEqual((s, d["error"]["code"]), (403, "ACCOUNT_SUSPENDED"))
        self.assertEqual(self.call("post", "/api/auth/login", json={"email": "alex.chen@proofhire.dev", "password": "demo1234"})[0], 403)


class TestSubmissionLifecycle(Base):
    def test_submit_score_resubmit_limit(self):
        tok = self.new_candidate()
        sid = self.submit(tok)
        self.drain()
        d = self.call("get", f"/api/candidate/submissions/{sid}", tok)[1]
        self.assertEqual(d["status"], "SCORED")
        self.assertEqual(d["latest"]["attempt_no"], 1)
        self.assertEqual(len(d["latest"]["sub_scores"]), 7)
        self.assertAlmostEqual(sum(x["score"] for x in d["latest"]["sub_scores"]) * 10, d["latest"]["overall"], delta=0.6)
        for n in (1, 2):
            s, r = self.call("post", f"/api/candidate/submissions/{sid}/resubmit", tok, json={"items": [dict(GH, description=f"v{n}")]})
            self.assertEqual((s, r["status"]), (200, "RESUBMITTED"))
            self.drain()
        d = self.call("get", f"/api/candidate/submissions/{sid}", tok)[1]
        self.assertEqual((d["status"], d["latest"]["attempt_no"], d["resubmissions_remaining"], d["can_resubmit"]), ("SCORED", 3, 0, False))
        self.assertEqual(len(d["history"]), 3)                        # every attempt preserved
        s, r = self.call("post", f"/api/candidate/submissions/{sid}/resubmit", tok, json={"items": [GH]})
        self.assertEqual((s, r["error"]["code"]), (409, "RESUBMISSION_LIMIT_REACHED"))

    def test_cannot_resubmit_while_not_scored(self):
        tok = self.new_candidate()
        self.ctx.config.start_worker = False
        self.ctx.queue.stop()
        time.sleep(0.3)
        sid = self.submit(tok)                                         # stays PENDING: nobody consumes the queue
        s, r = self.call("post", f"/api/candidate/submissions/{sid}/resubmit", tok, json={"items": [GH]})
        self.assertEqual((s, r["error"]["code"]), (409, "ONLY_SCORED_CAN_RESUBMIT"))

    def test_admin_changes_limit_without_code_change(self):
        adm, tok = self.demo("ADMIN"), self.new_candidate()
        self.assertEqual(self.call("put", "/api/admin/config", adm, json={"MAX_RESUBMISSIONS": 0})[0], 200)
        sid = self.submit(tok)
        self.drain()
        s, r = self.call("post", f"/api/candidate/submissions/{sid}/resubmit", tok, json={"items": [GH]})
        self.assertEqual((s, r["error"]["code"]), (409, "RESUBMISSION_LIMIT_REACHED"))
        self.assertEqual(self.call("put", "/api/admin/config", adm, json={"MAX_RESUBMISSIONS": 99})[0], 400)

    def test_evidence_validation(self):
        tok = self.new_candidate()
        bad = [
            [], [{"type": "GITHUB", "url": "https://gitlab.com/a/b"}], [{"type": "GITHUB", "url": "javascript:alert(1)"}],
            [{"type": "PORTFOLIO", "url": "ftp://x.io/a"}], [{"type": "CERTIFICATE"}], [{"type": "NOPE", "url": "https://x.io/a"}],
            [{"type": "GITHUB", "url": "https://github.com/a/b", "description": "x" * 2001}],
        ]
        for items in bad:
            s, d = self.call("post", "/api/candidate/submissions", tok, json={"title": "Valid title", "items": items})
            self.assertEqual(s, 400, items)
        self.assertEqual(self.call("post", "/api/candidate/submissions", tok, json={"title": "ab", "items": [GH]})[0], 400)

    def test_certificate_upload_and_signed_url(self):
        tok = self.new_candidate()
        pdf = b"%PDF-1.4 test certificate"
        payload = json.dumps({"title": "My certificate", "items": [{"type": "CERTIFICATE", "description": "x", "file_key": "f0"}]})
        r = self.c.post("/api/candidate/submissions", headers={"Authorization": f"Bearer {tok}"},
                        data={"payload": payload, "f0": (io.BytesIO(pdf), "cert.pdf")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201, r.get_json())
        sid = r.get_json()["id"]
        self.drain()
        d = self.call("get", f"/api/candidate/submissions/{sid}", tok)[1]
        eid = d["evidence"][0]["id"]
        self.assertTrue(d["evidence"][0]["has_file"])
        s, u = self.call("get", f"/api/evidence/{eid}/file-url", tok)
        self.assertEqual(s, 200)
        s, body = self.call("get", u["url"])
        self.assertEqual((s, body), (200, pdf))
        self.assertEqual(self.call("get", "/api/files/not-a-token")[0], 401)
        other = self.new_candidate("other@example.com")
        self.assertEqual(self.call("get", f"/api/evidence/{eid}/file-url", other)[0], 403)
        # recruiters cannot see files of an unscored/other context but can of scored visible exhibits
        rec = self.demo("RECRUITER")
        self.assertEqual(self.call("get", f"/api/evidence/{eid}/file-url", rec)[0], 200)

    def test_upload_rejects_bad_files(self):
        tok = self.new_candidate()
        for name, data in (("evil.exe", b"MZ..."), ("fake.pdf", b"not a pdf"), ("empty.pdf", b"")):
            payload = json.dumps({"title": "Bad upload", "items": [{"type": "CERTIFICATE", "file_key": "f0"}]})
            r = self.c.post("/api/candidate/submissions", headers={"Authorization": f"Bearer {tok}"},
                            data={"payload": payload, "f0": (io.BytesIO(data), name)}, content_type="multipart/form-data")
            self.assertEqual(r.status_code, 400, name)


class TestEngineDown(Base):
    scorer = MockProofScoreClient(fail_first=2)

    def test_queued_then_scored_after_retry(self):
        tok = self.new_candidate()
        sid = self.submit(tok)
        self.drain()
        time.sleep(0.6)
        self.drain()
        d = self.call("get", f"/api/candidate/submissions/{sid}", tok)[1]
        self.assertEqual(d["status"], "SCORED")
        self.assertEqual(self.scorer.calls, 3)                         # 2 failures + success
        kinds = [n["kind"] for n in self.call("get", "/api/notifications", tok)[1]["items"]]
        self.assertIn("QUEUED", kinds)
        self.assertIn("SCORE_READY", kinds)


class TestEngineStaysDown(Base):
    scorer = MockProofScoreClient(fail_first=999)
    cfg_kwargs = {"max_retries": 3}

    def test_gives_up_alerts_admin_and_can_be_requeued(self):
        tok, adm = self.new_candidate(), self.demo("ADMIN")
        sid = self.submit(tok)
        time.sleep(1.5)
        self.drain()
        d = self.call("get", f"/api/candidate/submissions/{sid}", tok)[1]
        self.assertEqual(d["status"], "QUEUED")
        self.assertIn("saved and will be scored", d["message"])
        st = self.call("get", "/api/admin/stats", adm)[1]
        self.assertEqual(st["failing"], 1)
        self.assertIn("SCORING_FAILING", [n["kind"] for n in self.call("get", "/api/notifications", adm)[1]["items"]])
        self.scorer.fail_first = 0                                      # engine recovers
        self.assertEqual(self.call("post", "/api/admin/queue/requeue", adm)[1]["requeued"], 1)
        self.drain()
        self.assertEqual(self.call("get", f"/api/candidate/submissions/{sid}", tok)[1]["status"], "SCORED")


class TestEngineRejects(Base):
    scorer = MockProofScoreClient(fail_first=999, error=EngineError("bad bundle"))

    def test_non_retryable_error_is_not_retried_forever(self):
        tok = self.new_candidate()
        self.submit(tok)
        self.drain()
        time.sleep(0.3)
        self.assertEqual(self.scorer.calls, 1)


class TestRecruiter(Base):
    def test_search_filters_and_visibility(self):
        rec = self.demo("RECRUITER")
        s, d = self.call("get", "/api/recruiter/candidates?min_score=6.5", rec)
        self.assertTrue(all(i["top_exhibit"]["out_of_10"] >= 6.5 for i in d["items"]))
        self.assertEqual([i["name"] for i in d["items"]], sorted([i["name"] for i in d["items"]], key=lambda n: -next(x for x in d["items"] if x["name"] == n)["score"]))
        d = self.call("get", "/api/recruiter/candidates?skill=kafka", rec)[1]
        self.assertEqual([i["name"] for i in d["items"]], ["Marcus Webb"])
        d = self.call("get", "/api/recruiter/candidates?verified=1", rec)[1]
        self.assertNotIn("Marcus Webb", [i["name"] for i in d["items"]])        # expired assessment -> provisional
        self.assertNotIn("Thandi Mokoena", [i["name"] for i in d["items"]])      # never assessed -> provisional
        d = self.call("get", "/api/recruiter/candidates?field=Data%20%26%20ML%20Engineering", rec)[1]
        self.assertEqual({i["name"] for i in d["items"]}, {"Marcus Webb", "Daniel Kim"})
        self.assertTrue(self.call("get", "/api/recruiter/search-history", rec)[1])

    def test_unscored_and_suspended_candidates_are_invisible(self):
        rec, adm = self.demo("RECRUITER"), self.demo("ADMIN")
        tok = self.new_candidate("fresh@example.com")
        cid = self.call("get", "/api/auth/me", tok)[1]["user"]["id"]
        self.assertEqual(self.call("get", f"/api/recruiter/candidates/{cid}", rec)[0], 404)
        self.assertEqual(self.call("put", f"/api/recruiter/candidates/{cid}/shortlist", rec)[1]["error"]["code"], "CANDIDATE_NOT_SCORED")
        self.assertEqual(self.call("post", f"/api/recruiter/candidates/{cid}/contact", rec, json={"message": "hello there friend"})[1]["error"]["code"], "CANDIDATE_NOT_SCORED")
        d = self.call("get", "/api/recruiter/candidates", rec)[1]
        sofia = next(i for i in d["items"] if i["name"] == "Sofia Reyes")["candidate_id"]
        self.assertEqual(self.call("get", f"/api/recruiter/candidates/{sofia}", rec)[0], 200)
        uid = sofia
        self.call("post", f"/api/admin/users/{uid}/status", adm, json={"status": "SUSPENDED", "reason": "test"})
        self.assertEqual(self.call("get", f"/api/recruiter/candidates/{sofia}", rec)[0], 404)
        self.assertNotIn("Sofia Reyes", [i["name"] for i in self.call("get", "/api/recruiter/candidates", rec)[1]["items"]])

    def test_profile_hides_improvement_advice_and_shortlist_roundtrip(self):
        rec = self.demo("RECRUITER")
        d = self.call("get", "/api/recruiter/candidates", rec)[1]
        pid = next(i for i in d["items"] if i["name"] == "Daniel Kim")["candidate_id"]
        p = self.call("get", f"/api/recruiter/candidates/{pid}", rec)[1]
        self.assertNotIn("recommendations", p["exhibits"][0]["score"])
        self.assertEqual(self.call("put", f"/api/recruiter/candidates/{pid}/shortlist", rec)[0], 200)
        self.assertEqual(self.call("put", f"/api/recruiter/candidates/{pid}/shortlist", rec)[0], 200)   # idempotent
        self.assertIn(pid, [i["candidate_id"] for i in self.call("get", "/api/recruiter/shortlist", rec)[1]["items"]])
        self.call("delete", f"/api/recruiter/candidates/{pid}/shortlist", rec)
        self.assertNotIn(pid, [i["candidate_id"] for i in self.call("get", "/api/recruiter/shortlist", rec)[1]["items"]])

    def test_contact_notifies_candidate_and_is_rate_limited(self):
        rec, cand = self.demo("RECRUITER"), self.demo("CANDIDATE")
        cid = self.call("get", "/api/auth/me", cand)[1]["user"]["id"]
        s, d = self.call("post", f"/api/recruiter/candidates/{cid}/contact", rec, json={"message": "We would love to talk to you."})
        self.assertEqual(s, 200, d)
        s, d = self.call("post", f"/api/recruiter/candidates/{cid}/contact", rec, json={"message": "Another message right away."})
        self.assertEqual((s, d["error"]["code"]), (429, "CONTACT_RATE_LIMIT"))
        self.assertEqual(self.call("post", f"/api/recruiter/candidates/{cid}/contact", rec, json={"message": "short"})[0], 400)
        self.assertIn("CONTACT_REQUEST", [n["kind"] for n in self.call("get", "/api/notifications", cand)[1]["items"]])
        self.assertTrue(self.call("get", "/api/candidate/contact-requests", cand)[1])


class TestAdmin(Base):
    def test_suspend_writes_audit_atomically_and_protects_admins(self):
        adm = self.demo("ADMIN")
        users = self.call("get", "/api/admin/users?role=CANDIDATE", adm)[1]
        marcus = next(u for u in users if u["name"] == "Marcus Webb")["id"]
        self.assertEqual(self.call("post", f"/api/admin/users/{marcus}/status", adm, json={"status": "SUSPENDED"})[0], 400)   # reason required
        self.assertEqual(self.call("post", f"/api/admin/users/{marcus}/status", adm, json={"status": "SUSPENDED", "reason": "Fake evidence"})[0], 200)
        log = self.call("get", "/api/admin/audit", adm)[1]
        self.assertEqual((log[0]["action"], log[0]["target_id"], log[0]["detail"]), ("SUSPEND_USER", marcus, "Fake evidence"))
        me = self.call("get", "/api/auth/me", adm)[1]["user"]["id"]
        self.assertEqual(self.call("post", f"/api/admin/users/{me}/status", adm, json={"status": "REMOVED", "reason": "oops"})[0], 403)
        self.call("post", f"/api/admin/users/{marcus}/status", adm, json={"status": "ACTIVE"})
        self.assertEqual(self.call("get", "/api/admin/audit", adm)[1][0]["action"], "RESTORE_USER")

    def test_flag_and_moderate(self):
        adm = self.demo("ADMIN")
        flagged = self.call("get", "/api/admin/submissions?moderation=FLAGGED", adm)[1]
        self.assertEqual(len(flagged), 1)
        sid = flagged[0]["id"]
        self.assertEqual(self.call("post", f"/api/admin/submissions/{sid}/moderate", adm, json={"action": "remove", "reason": "Plagiarised"})[0], 200)
        rec = self.demo("RECRUITER")
        self.assertNotIn("Thandi Mokoena", [i["name"] for i in self.call("get", "/api/recruiter/candidates", rec)[1]["items"]])
        self.assertEqual(self.call("get", "/api/admin/audit", adm)[1][0]["action"], "REMOVE_SUBMISSION")
        # recruiter flags another exhibit -> admin notified
        d = self.call("get", "/api/recruiter/candidates", rec)[1]
        sub = d["items"][0]["top_exhibit"]["id"]
        self.assertEqual(self.call("post", f"/api/recruiter/submissions/{sub}/flag", rec, json={"reason": "Looks suspicious"})[0], 200)
        self.assertIn("SUBMISSION_FLAGGED", [n["kind"] for n in self.call("get", "/api/notifications", adm)[1]["items"]])

    def test_stats(self):
        s, d = self.call("get", "/api/admin/stats", self.demo("ADMIN"))
        self.assertEqual(s, 200)
        self.assertEqual(len(d["per_day"]), 7)
        self.assertEqual(d["active_users"]["CANDIDATE"], 6)
        self.assertIn("status", d["engine"])


class TestAssessments(Base):
    def answers(self, field, wrong=0):
        out = {q["id"]: q["answer"] for q in BANK[field]}
        for q in list(BANK[field])[:wrong]:
            out[q["id"]] = (q["answer"] + 1) % len(q["options"])
        return out

    def test_never_leaks_answers_and_grading(self):
        tok = self.new_candidate("quiz@example.com")
        self.assertEqual(self.call("get", "/api/candidate/assessments", tok)[1][0]["status"], "not_started")
        s, q = self.call("post", "/api/candidate/assessments/Backend%20Engineering/start", tok)
        self.assertNotIn("answer", json.dumps(q))
        self.assertEqual(len(q["questions"]), 8)
        r = self.call("post", "/api/candidate/assessments/Backend%20Engineering/submit", tok, json={"answers": self.answers("Backend Engineering", wrong=3)})[1]
        self.assertEqual((r["passed"], r["correct"]), (False, 5))
        self.assertTrue(r["topics_to_review"])
        self.assertEqual(self.call("get", "/api/candidate/assessments", tok)[1][0]["status"], "failed")
        r = self.call("post", "/api/candidate/assessments/Backend%20Engineering/submit", tok, json={"answers": self.answers("Backend Engineering", wrong=2)})[1]
        self.assertEqual((r["passed"], r["correct"]), (True, 6))
        ov = self.call("get", "/api/candidate/assessments", tok)[1]
        self.assertEqual((ov[0]["status"], ov[0]["required"]), ("valid", True))
        self.assertEqual(self.call("post", "/api/candidate/assessments/Nope/start", tok)[0], 404)

    def test_provisional_flag_follows_assessment(self):
        tok = self.new_candidate("prov@example.com")
        self.submit(tok)
        self.drain()
        rec = self.demo("RECRUITER")
        find = lambda: next(i for i in self.call("get", "/api/recruiter/candidates", rec)[1]["items"] if i["name"] == "New Person")
        self.assertTrue(find()["provisional"])
        self.call("post", "/api/candidate/assessments/Backend%20Engineering/submit", tok, json={"answers": self.answers("Backend Engineering")})
        self.assertFalse(find()["provisional"])

    def test_expiry_states(self):
        alex = self.demo("CANDIDATE")
        self.assertEqual(self.call("get", "/api/candidate/profile", alex)[1]["assessment"]["status"], "due_soon")
        mid = self.call("get", "/api/recruiter/candidates", self.demo("RECRUITER"))[1]["items"]
        self.assertTrue(next(i for i in mid if i["name"] == "Marcus Webb")["provisional"])      # expired


class TestMisc(Base):
    def test_error_format_and_headers(self):
        s, d = self.call("get", "/api/nope")
        self.assertEqual((s, d["error"]["code"]), (404, "NOT_FOUND"))
        r = self.c.get("/api/meta")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        self.assertEqual(self.call("post", "/api/auth/login", data="not json", content_type="text/plain")[0], 400)

    def test_jobs(self):
        cand, rec = self.demo("CANDIDATE"), self.demo("RECRUITER")
        jobs = self.call("get", "/api/jobs?field=Backend%20Engineering", cand)[1]
        self.assertTrue(jobs and jobs[0]["match"] is not None)
        self.assertEqual(self.call("post", "/api/jobs", rec, json={"title": "SRE", "field": "Backend Engineering", "skills": ["Go"]})[0], 201)
        self.assertEqual(self.call("post", "/api/jobs", rec, json={"title": "SRE", "field": "Bogus"})[0], 400)
        self.assertEqual(len(self.call("get", "/api/jobs?mine=1", rec)[1]), 3)

    def test_engine_never_sees_personal_data(self):
        seen = []
        orig = self.scorer.evaluate
        self.scorer.evaluate = lambda b: (seen.append(b), orig(b))[1]
        tok = self.new_candidate("private@example.com")
        self.submit(tok)
        self.drain()
        blob = json.dumps(seen)
        self.assertNotIn("private@example.com", blob)
        self.assertNotIn("New Person", blob)

    def test_pending_recovered_after_restart(self):
        tok = self.new_candidate()
        self.ctx.queue.stop()
        time.sleep(0.3)
        sid = self.submit(tok)                                          # nobody consumes it
        cfg = Config(instance_dir=self.dir, scorer="mock")
        app2 = create_app(cfg, scorer=MockProofScoreClient())           # "restart": same database
        app2.extensions["proofhire"].queue.drain(10)
        with app2.extensions["proofhire"].db.session(False) as s:
            self.assertEqual(s.conn.execute("SELECT status FROM submission WHERE id=?", (sid,)).fetchone()[0], "SCORED")
        app2.extensions["proofhire"].queue.stop()


if __name__ == "__main__":
    unittest.main()


class NewFeatureTests(Base):
    def test_every_tech_role_registers_and_has_an_assessment(self):
        meta = self.call("get", "/api/meta")[1]
        self.assertGreaterEqual(len(meta["fields"]), 30)
        self.assertEqual(sorted(sum(meta["role_groups"].values(), [])), sorted(meta["fields"]))
        for i, role in enumerate(["UI & UX Design", "Cybersecurity Analyst", "Product Management", "AI & LLM Engineering"]):
            code, out = self.call("post", "/api/auth/register", json={"name": f"Tester {i}", "email": f"t{i}@x.dev", "password": "Passw0rd!x", "role": "CANDIDATE", "field": role})
            self.assertEqual(code, 201, out)
            code, qs = self.call("post", f"/api/candidate/assessments/{role}/start", out["token"])
            self.assertEqual(code, 200, qs)
            self.assertGreaterEqual(len(qs["questions"]), 5)
        code, _ = self.call("post", "/api/auth/register", json={"name": "Bad Role", "email": "b@x.dev", "password": "Passw0rd!x", "role": "CANDIDATE", "field": "Wizard"})
        self.assertEqual(code, 400)

    def test_social_login_creates_then_reuses_account(self):
        body = {"provider": "google", "email": "sam.dev@gmail.com", "name": "Sam Dev", "role": "CANDIDATE", "field": "DevOps Engineering"}
        c1, a = self.call("post", "/api/auth/social", json=body)
        c2, b = self.call("post", "/api/auth/social", json=body)
        self.assertEqual((c1, c2), (200, 200))
        self.assertEqual(a["user"]["id"], b["user"]["id"])
        self.assertEqual(self.call("post", "/api/auth/social", json={**body, "provider": "myspace"})[0], 400)
        self.assertEqual(self.call("post", "/api/auth/social", json={**body, "email": "nope"})[0], 400)

    def test_recruiter_messages_and_candidate_views(self):
        rec, cand = self.demo("RECRUITER"), self.demo("CANDIDATE")
        cid = self.call("get", "/api/auth/me", cand)[1]["user"]["id"]
        self.assertEqual(self.call("get", "/api/recruiter/messages", rec)[1], [])
        before = self.call("get", "/api/candidate/stats", cand)[1]["views_today"]
        self.assertEqual(self.call("get", f"/api/recruiter/candidates/{cid}", rec)[0], 200)
        self.assertEqual(self.call("get", "/api/candidate/stats", cand)[1]["views_today"], before + 1)
        self.assertEqual(self.call("post", f"/api/recruiter/candidates/{cid}/contact", rec, json={"message": "Hello, we have a role for you."})[0], 200)
        msgs = self.call("get", "/api/recruiter/messages", rec)[1]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(self.call("get", "/api/recruiter/messages", cand)[0], 403)
