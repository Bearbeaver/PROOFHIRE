"""Engine tests. Run:  python -m unittest tests.test_engine -v   (trains the model on first run if missing)"""
import unittest

from engine.features import DIM_MAX, FEATURE_NAMES, build_raw_features, page_stats, path_stats, readme_stats, to_vector
from engine.fixtures import FIXTURES
from engine.model import ensure_model
from engine.server import create_app
from engine.signals import (FixtureFetcher, UpstreamRateLimited, UpstreamUnavailable, is_public_host, parse_github_url, safe_get)

KEY = {"X-Engine-Key": "dev-engine-key"}
MODEL = None


def model():
    global MODEL
    if MODEL is None:
        MODEL = ensure_model()
    return MODEL


class Fake:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def repo_signals(self, owner, name):
        if self.error:
            raise self.error
        return self.result


def bundle(url, area="Backend Engineering", skills=("Go",)):
    return {"skill_area": area, "candidate_skills": list(skills), "evidence": [{"type": "GITHUB", "url": url, "description": ""}]}


class TestFeatures(unittest.TestCase):
    def test_path_stats(self):
        ps = path_stats(["src/a.py", "src/b.py", "tests/test_a.py", ".github/workflows/ci.yml", "node_modules/x/y.js", "Dockerfile",
                         ".flake8", "requirements.txt", "docs/architecture.md", "LICENSE", ".gitignore"])
        self.assertEqual((ps["source"], ps["tests"]), (2, 1))                  # vendored files ignored, tests separated
        self.assertTrue(all(ps[k] for k in ("ci", "docker", "linter", "manifest", "docs", "license", "gitignore", "has_test_dir")))

    def test_readme_stats(self):
        r = readme_stats("# Title\n## Install\n```\npip install x\n```\n## Usage\nsee examples\n## Architecture\n![img](a.png)")
        self.assertEqual((r["headings"], r["code_blocks"], r["images"]), (4, 1, 1))
        self.assertTrue(r["install"] and r["usage"] and r["arch"])

    def test_page_stats_ignores_scripts(self):
        p = page_stats("<h1>Hi</h1><script>var secret=1</script><p>some words here</p>")
        self.assertEqual(p["headings"], 1)
        self.assertNotIn("secret", p["text"])

    def test_vector_is_fixed_length_and_finite(self):
        sig = FIXTURES["alexchen/queuely"]
        raw, facts, quality, notes = build_raw_features(bundle("https://github.com/alexchen/queuely"), [sig], [])
        v = to_vector(raw)
        self.assertEqual(len(v), len(FEATURE_NAMES))
        self.assertTrue(all(x == x and abs(x) < 1e6 for x in v))
        self.assertEqual(quality, "full")
        self.assertGreater(raw["test_files"], 0)
        self.assertIn("no_linter", notes)

    def test_unreachable_evidence_earns_no_credit(self):
        raw, facts, quality, notes = build_raw_features(bundle("https://github.com/x/y"), [None], [])
        self.assertEqual((quality, raw["analysed_fraction"], raw["file_count"]), ("limited", 0.0, 0.0))
        self.assertIn("repo_unreachable", notes)


class TestModel(unittest.TestCase):
    def predict(self, repo, area="Backend Engineering"):
        owner, name = repo.split("/")
        raw, *_ = build_raw_features(bundle(f"https://github.com/{repo}", area), [FIXTURES[repo]], [])
        return model().predict(raw)

    def test_better_projects_score_higher(self):
        total = lambda r, a="Backend Engineering": sum(self.predict(r, a).values())
        self.assertGreater(total("alexchen/queuely-v2"), total("alexchen/queuely"))       # tests + docs + CI added
        self.assertGreater(total("sofiareyes/ledgerly"), total("demo-user/api-starter"))
        self.assertGreater(total("demo-user/api-starter"), total("demo-user/todo-list", "Frontend Engineering"))

    def test_improvements_land_in_the_right_dimensions(self):
        a, b = self.predict("alexchen/queuely"), self.predict("alexchen/queuely-v2")
        self.assertGreater(b["testing"], a["testing"])
        self.assertGreater(b["documentation"], a["documentation"])

    def test_outputs_within_bounds(self):
        for repo in FIXTURES:
            for k, v in self.predict(repo, "Backend Engineering").items():
                self.assertTrue(0 <= v <= DIM_MAX[k], (repo, k, v))


class TestServer(unittest.TestCase):
    def setUp(self):
        self.app = create_app(model=model(), github=FixtureFetcher(FIXTURES))
        self.c = self.app.test_client()

    def test_auth_and_validation(self):
        self.assertEqual(self.c.post("/evaluate", json=bundle("https://github.com/a/b")).status_code, 401)
        self.assertEqual(self.c.post("/evaluate", headers={"X-Engine-Key": "nope"}, json=bundle("https://github.com/a/b")).status_code, 401)
        for bad in ({}, {"evidence": []}, {"evidence": [{"type": "X"}]}, {"evidence": [{"type": "GITHUB", "url": 5}]}, {"evidence": [{"type": "GITHUB"}] * 7}):
            self.assertEqual(self.c.post("/evaluate", headers=KEY, json=bad).status_code, 400, bad)

    def test_evaluate_response_shape_and_consistency(self):
        r = self.c.post("/evaluate", headers=KEY, json=bundle("https://github.com/alexchen/queuely-v2"))
        d = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(d["sub_scores"]), set(DIM_MAX))
        self.assertAlmostEqual(d["overall"], sum(v["score"] for v in d["sub_scores"].values()) * 10, delta=0.01)
        self.assertEqual(d["data_quality"], "full")
        self.assertTrue(d["facts"] and d["strengths"] is not None)
        self.assertTrue(all("text" in x and "potential_gain" in x for x in d["recommendations"]))

    def test_deterministic(self):
        a = self.c.post("/evaluate", headers=KEY, json=bundle("https://github.com/alexchen/queuely")).get_json()
        b = self.c.post("/evaluate", headers=KEY, json=bundle("https://github.com/alexchen/queuely")).get_json()
        self.assertEqual(a, b)

    def test_unknown_repo_in_offline_mode_is_limited_with_advice(self):
        app = create_app(model=model(), github=Fake(result=None))
        d = app.test_client().post("/evaluate", headers=KEY, json=bundle("https://github.com/ghost/missing")).get_json()
        self.assertEqual(d["data_quality"], "limited")
        self.assertEqual(d["recommendations"][0]["dimension"], "evidence")
        self.assertLess(d["overall"], 30)

    def test_upstream_failures_are_503_so_backend_can_retry(self):
        for err in (UpstreamUnavailable("down"), UpstreamRateLimited("slow down")):
            app = create_app(model=model(), github=Fake(error=err))
            r = app.test_client().post("/evaluate", headers=KEY, json=bundle("https://github.com/a/b"))
            self.assertEqual(r.status_code, 503)

    def test_health_reports_model_card(self):
        d = self.c.get("/health").get_json()
        self.assertEqual(d["status"], "ok")
        self.assertIn("trained_on", d)


class TestSafety(unittest.TestCase):
    def test_parse_github_url(self):
        self.assertEqual(parse_github_url("https://github.com/pallets/flask"), ("pallets", "flask"))
        self.assertEqual(parse_github_url("https://github.com/pallets/flask.git/"), ("pallets", "flask"))
        for bad in ("http://github.com/a/b", "https://evil.com/a/b", "https://github.com/a", "https://github.com/a/b/c", "javascript:alert(1)"):
            self.assertIsNone(parse_github_url(bad), bad)

    def test_ssrf_guard(self):
        for host in ("127.0.0.1", "localhost", "10.0.0.5", "192.168.1.1", "169.254.169.254", "0.0.0.0", "::1"):
            self.assertFalse(is_public_host(host), host)
        for url in ("http://127.0.0.1:5000/api/meta", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd", "ftp://example.com/x", "http://localhost/"):
            self.assertIsNone(safe_get(url), url)


if __name__ == "__main__":
    unittest.main()
