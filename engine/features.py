"""Feature extraction for the ProofScore Engine.

Turns an evidence bundle plus the signals collected about it (GitHub repository
metadata, fetched portfolio pages, certificate metadata) into:

* ``raw``   - a dict of human-readable numbers (counts, flags, ratios)
* ``facts`` - short plain-language statements of what was measured (explainability, NFR8)
* ``quality`` - how much of the submitted evidence could actually be analysed

The engine never receives the candidate's name, e-mail or any personal attribute,
only the evidence itself, the target skill area and the candidate's self-declared skill tags.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from html.parser import HTMLParser

# (key, label, max points) - weights from the ProofHire proposal, total 10.0
DIMENSIONS = [
    ("relevance", "Relevance to the job", 2.0),
    ("technical_quality", "Technical quality", 2.0),
    ("complexity", "Complexity / problem-solving", 1.5),
    ("code_quality", "Code quality & maintainability", 1.5),
    ("documentation", "Documentation", 1.0),
    ("testing", "Testing & reliability", 1.0),
    ("impact", "Evidence of real-world impact", 1.0),
]
DIM_KEYS = [d[0] for d in DIMENSIONS]
DIM_MAX = {d[0]: d[2] for d in DIMENSIONS}

FIELD_KEYWORDS = {
    "Backend Engineering": {
        "api", "rest", "grpc", "graphql", "server", "database", "sql", "postgres", "postgresql", "mysql",
        "redis", "queue", "kafka", "microservice", "microservices", "auth", "jwt", "backend", "docker",
        "concurrency", "cache", "orm", "spring", "django", "flask", "fastapi", "express", "gin",
        "goroutine", "worker", "endpoint", "middleware", "migration",
    },
    "Frontend Engineering": {
        "react", "vue", "angular", "svelte", "css", "html", "typescript", "javascript", "component",
        "components", "ui", "ux", "responsive", "accessibility", "a11y", "tailwind", "webpack", "vite",
        "dom", "frontend", "state", "router", "redux", "browser", "design", "animation", "canvas",
    },
    "Data & ML Engineering": {
        "machine", "learning", "model", "pytorch", "tensorflow", "sklearn", "scikit", "pandas", "numpy",
        "dataset", "training", "pipeline", "etl", "spark", "airflow", "notebook", "neural",
        "classification", "regression", "data", "kafka", "feature", "inference", "ml", "analytics",
    },
}
FIELD_LANGS = {
    "Backend Engineering": {"Go", "Java", "Python", "C#", "Rust", "Kotlin", "PHP", "Ruby", "Scala", "C++", "Shell", "Dockerfile"},
    "Frontend Engineering": {"JavaScript", "TypeScript", "HTML", "CSS", "SCSS", "Vue", "Svelte", "Dart"},
    "Data & ML Engineering": {"Python", "Jupyter Notebook", "R", "Scala", "SQL", "Julia", "Shell"},
}
KNOWN_ISSUERS = [
    "coursera", "edx", "udemy", "udacity", "aws", "amazon web services", "google", "microsoft", "azure",
    "oracle", "cisco", "comptia", "meta", "ibm", "freecodecamp", "linux foundation", "linuxfoundation",
    "hackerrank", "pluralsight", "kaggle", "scrum.org", "red hat", "datacamp", "harvard", "stanford", "mit",
    "jetbrains", "hashicorp", "kubernetes", "cncf",
]

SOURCE_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".kt", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp",
    ".cs", ".rb", ".php", ".swift", ".scala", ".vue", ".svelte", ".dart", ".ipynb", ".sql", ".r",
}
IGNORED_DIRS = {"node_modules", "vendor", "dist", "build", ".git", "venv", ".venv", "__pycache__", "target", ".idea"}

FEATURE_NAMES = [
    "readme_len", "readme_headings", "readme_code_blocks", "readme_install", "readme_usage", "readme_arch",
    "readme_images", "desc_len",
    "file_count", "source_files", "size_kb", "language_count", "dir_count", "max_depth",
    "test_files", "test_ratio", "has_test_dir", "has_ci", "has_license", "has_docs_dir", "has_docker",
    "has_linter", "has_gitignore", "has_manifest",
    "commits", "span_days", "recency", "stars", "forks", "has_homepage",
    "field_overlap", "lang_field_match", "skill_overlap",
    "portfolio_words", "portfolio_headings", "portfolio_reachable",
    "cert_count", "cert_known_issuer", "cert_verifiable", "cert_field_match",
    "n_github", "n_portfolio", "n_items", "analysed_fraction",
]
LOG_FEATURES = {
    "readme_len", "readme_headings", "readme_code_blocks", "readme_images", "desc_len", "file_count",
    "source_files", "size_kb", "dir_count", "max_depth", "test_files", "commits", "span_days", "stars",
    "forks", "portfolio_words", "portfolio_headings",
}


def to_vector(raw: dict) -> list[float]:
    """Single place where raw features become model inputs (used by training AND serving)."""
    out = []
    for name in FEATURE_NAMES:
        v = float(raw.get(name, 0.0) or 0.0)
        out.append(math.log1p(max(v, 0.0)) if name in LOG_FEATURES else v)
    return out


# --------------------------------------------------------------------------- text helpers
def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#]+", (text or "").lower()))


def readme_stats(text: str) -> dict:
    t = text or ""
    low = t.lower()
    headings = len(re.findall(r"^\s{0,3}#{1,6}\s+\S", t, re.M)) + len(re.findall(r"^\S[^\n]*\n(?:=+|-+)\s*$", t, re.M))
    return {
        "len": len(t),
        "headings": headings,
        "code_blocks": t.count("```") // 2,
        "install": bool(re.search(r"\b(install|installation|getting started|setup|set up|quick ?start)\b", low)),
        "usage": bool(re.search(r"\b(usage|examples?|how to use|api reference)\b", low)),
        "arch": bool(re.search(r"\b(architecture|design decisions?|how it works|adr|diagram|components?)\b", low)),
        "images": len(re.findall(r"!\[[^\]]*\]\([^)]+\)|<img\s", t)),
    }


_TEST_RE = re.compile(
    r"(^|/)(tests?|__tests__|specs?|e2e)(/|$)|(^|/)test_[^/]+\.\w+$|_test\.\w+$|\.(test|spec)\.\w+$|Tests?\.(java|cs|kt)$",
    re.I,
)
_CI_RE = re.compile(r"(^|/)(\.github/workflows/|\.gitlab-ci\.yml$|\.circleci/|Jenkinsfile$|\.travis\.yml$|azure-pipelines\.yml$)")
_LINT_RE = re.compile(
    r"(^|/)(\.eslintrc[^/]*|eslint\.config\.[^/]+|\.prettierrc[^/]*|\.flake8|ruff\.toml|\.golangci\.[^/]+|\.pylintrc|pylintrc|"
    r"\.editorconfig|tslint\.json|\.rubocop\.yml|clippy\.toml|rustfmt\.toml|checkstyle[^/]*\.xml)$"
)
_MANIFEST_RE = re.compile(
    r"(^|/)(package\.json|requirements[^/]*\.txt|pyproject\.toml|go\.mod|pom\.xml|build\.gradle(\.kts)?|Cargo\.toml|Gemfile|composer\.json|[^/]+\.csproj)$"
)


def path_stats(paths: list[str]) -> dict:
    clean = []
    for p in paths:
        parts = p.split("/")
        if any(part in IGNORED_DIRS for part in parts[:-1]):
            continue
        clean.append(p)
    dirs, depth = set(), 0
    src = tests = 0
    for p in clean:
        parts = p.split("/")
        depth = max(depth, len(parts) - 1)
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
        ext = "." + p.rsplit(".", 1)[-1].lower() if "." in parts[-1] else ""
        is_test = bool(_TEST_RE.search(p))
        if is_test and ext in SOURCE_EXT:
            tests += 1
        elif ext in SOURCE_EXT:
            src += 1
    lower = [p.lower() for p in clean]
    return {
        "files": len(clean),
        "source": src,
        "tests": tests,
        "dirs": len(dirs),
        "depth": depth,
        "has_test_dir": any(re.search(r"(^|/)(tests?|__tests__|specs?)/", p, re.I) for p in clean),
        "ci": any(_CI_RE.search(p) for p in clean),
        "license": any(re.search(r"(^|/)licen[cs]e(\.[a-z]+)?$", p) for p in lower),
        "docs": any(p.startswith(("docs/", "doc/")) or p.endswith(("architecture.md", "contributing.md")) for p in lower),
        "docker": any(p.endswith("dockerfile") or "docker-compose" in p for p in lower),
        "linter": any(_LINT_RE.search(p) for p in clean),
        "gitignore": any(p == ".gitignore" for p in lower),
        "manifest": any(_MANIFEST_RE.search(p) for p in clean),
    }


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text, self.headings, self._skip = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag in ("h1", "h2", "h3"):
            self.headings += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.text.append(data.strip())


def page_stats(html: str) -> dict:
    p = _PageParser()
    try:
        p.feed(html or "")
    except Exception:  # malformed HTML must never break scoring
        pass
    text = " ".join(p.text)
    return {"words": len(text.split()), "headings": p.headings, "text": text[:20000]}


def _parse_dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def field_relevance(field: str, text_tokens: set[str], langs: dict) -> tuple[float, float]:
    kws = FIELD_KEYWORDS.get(field, set())
    overlap = len(kws & text_tokens) / 8.0 if kws else 0.0
    total = sum(langs.values()) or 0
    typical = FIELD_LANGS.get(field, set())
    lang_match = (sum(b for l, b in langs.items() if l in typical) / total) if total else 0.0
    return min(1.0, overlap), min(1.0, lang_match)


# --------------------------------------------------------------------------- main entry
def build_raw_features(bundle: dict, github: list, pages: list, now: datetime | None = None):
    """``github`` / ``pages`` are lists aligned with the GITHUB / PORTFOLIO items (None = could not be analysed)."""
    now = now or datetime.now(timezone.utc)
    field = bundle.get("skill_area", "")
    items = bundle.get("evidence", [])
    skills = {s.lower() for s in bundle.get("candidate_skills", [])}
    raw = dict.fromkeys(FEATURE_NAMES, 0.0)
    facts: list[str] = []
    notes: list[str] = []
    analysed, total_items = 0.0, 0
    all_tokens: set[str] = set()
    langs: dict[str, int] = {}
    readme_texts: list[str] = []
    desc_len = 0

    gh_items = [i for i in items if i["type"] == "GITHUB"]
    pf_items = [i for i in items if i["type"] == "PORTFOLIO"]
    ct_items = [i for i in items if i["type"] == "CERTIFICATE"]
    raw["n_github"], raw["n_portfolio"], raw["cert_count"] = len(gh_items), len(pf_items), len(ct_items)
    raw["n_items"] = len(items)

    for it in items:
        desc_len += len(it.get("description") or "")
        all_tokens |= tokens(it.get("description") or "") | tokens(it.get("url") or "")

    latest_push = None
    for it, sig in zip(gh_items, github):
        total_items += 1
        if not sig or not sig.get("found"):
            notes.append("repo_unreachable")
            facts.append(f"Could not access {it.get('url')} (private, missing or rate-limited) - it earned no technical credit.")
            continue
        analysed += 1
        ps = path_stats(sig.get("paths", []))
        rs = readme_stats(sig.get("readme", ""))
        readme_texts.append(sig.get("readme", ""))
        raw["file_count"] += ps["files"]
        raw["source_files"] += ps["source"]
        raw["test_files"] += ps["tests"]
        raw["dir_count"] += ps["dirs"]
        raw["max_depth"] = max(raw["max_depth"], ps["depth"])
        raw["size_kb"] += sig.get("size_kb", 0)
        raw["commits"] += sig.get("commits", 0)
        raw["stars"] += sig.get("stars", 0)
        raw["forks"] += sig.get("forks", 0)
        for flag, key in (("has_test_dir", "has_test_dir"), ("has_ci", "ci"), ("has_license", "license"),
                          ("has_docs_dir", "docs"), ("has_docker", "docker"), ("has_linter", "linter"),
                          ("has_gitignore", "gitignore"), ("has_manifest", "manifest")):
            raw[flag] = max(raw[flag], 1.0 if ps[key] else 0.0)
        raw["has_license"] = max(raw["has_license"], 1.0 if sig.get("license") else 0.0)
        raw["has_homepage"] = max(raw["has_homepage"], 1.0 if sig.get("homepage") else 0.0)
        raw["readme_len"] += rs["len"]
        raw["readme_headings"] += rs["headings"]
        raw["readme_code_blocks"] += rs["code_blocks"]
        raw["readme_images"] += rs["images"]
        for k in ("install", "usage", "arch"):
            raw[f"readme_{k}"] = max(raw[f"readme_{k}"], 1.0 if rs[k] else 0.0)
        for l, b in (sig.get("languages") or {}).items():
            langs[l] = langs.get(l, 0) + b
        all_tokens |= tokens(sig.get("readme", "")) | tokens(sig.get("description", "")) | {t.lower() for t in sig.get("topics", [])}
        c, p = _parse_dt(sig.get("created_at")), _parse_dt(sig.get("pushed_at"))
        if c and p:
            raw["span_days"] = max(raw["span_days"], max((p - c).days, 0))
        if p and (latest_push is None or p > latest_push):
            latest_push = p
        bits = [f"{ps['files']} files ({ps['source']} source)", f"{ps['tests']} test files"]
        bits.append("CI configured" if ps["ci"] else "no CI configuration")
        bits.append(f"README {rs['len']} chars" + (" with install/usage sections" if rs["install"] and rs["usage"] else ""))
        if sig.get("commits"):
            bits.append(f"{sig['commits']} commits")
        facts.append(f"GitHub {sig.get('full_name', it.get('url'))}: " + ", ".join(bits) + ".")
        if ps["tests"] == 0:
            notes.append("no_tests")
        if not ps["ci"]:
            notes.append("no_ci")
        if not ps["linter"]:
            notes.append("no_linter")
        if rs["len"] < 600:
            notes.append("short_readme")
        if not rs["arch"]:
            notes.append("no_arch_docs")
        if rs["code_blocks"] == 0:
            notes.append("no_code_examples")
        if not ps["docs"]:
            notes.append("no_docs_dir")
        if not sig.get("homepage"):
            notes.append("no_demo")

    for it, pg in zip(pf_items, pages):
        total_items += 1
        if not pg:
            notes.append("portfolio_unreachable")
            facts.append(f"Could not open portfolio link {it.get('url')}.")
            continue
        analysed += 1
        raw["portfolio_reachable"] = 1.0
        raw["portfolio_words"] += pg["words"]
        raw["portfolio_headings"] += pg["headings"]
        all_tokens |= tokens(pg["text"])
        facts.append(f"Portfolio page {it.get('url')}: about {pg['words']} words of content, {pg['headings']} headings.")

    cert_tokens: set[str] = set()
    for it in ct_items:
        total_items += 1
        blob = " ".join([(it.get("description") or ""), (it.get("url") or ""), (it.get("file_name") or "")]).lower()
        cert_tokens |= tokens(blob)
        has_proof = bool(it.get("url") or it.get("file_name"))
        analysed += 1.0 if has_proof else 0.0
        if any(k in blob for k in KNOWN_ISSUERS):
            raw["cert_known_issuer"] += 1
        if (it.get("url") or "").startswith("https://"):
            raw["cert_verifiable"] += 1
        facts.append("Certificate: " + ("issuer recognised, " if any(k in blob for k in KNOWN_ISSUERS) else "issuer not recognised, ")
                     + ("verification link provided." if it.get("url") else "file only (content is not machine-verified)."))
    if ct_items and not raw["cert_verifiable"]:
        notes.append("cert_unverifiable")
    raw["cert_field_match"] = min(1.0, len(FIELD_KEYWORDS.get(field, set()) & cert_tokens) / 3.0) if ct_items else 0.0

    raw["language_count"] = len(langs)
    raw["test_ratio"] = min(2.0, raw["test_files"] / max(1.0, raw["source_files"]))
    raw["desc_len"] = desc_len
    raw["field_overlap"], raw["lang_field_match"] = field_relevance(field, all_tokens, langs)
    raw["skill_overlap"] = min(1.0, len(skills & all_tokens) / max(1, min(len(skills), 5))) if skills else 0.0
    if latest_push:
        raw["recency"] = max(0.0, 1.0 - (now - latest_push).days / 730.0)
    raw["analysed_fraction"] = (analysed / total_items) if total_items else 0.0

    frac = raw["analysed_fraction"]
    quality = "full" if frac >= 0.999 else ("partial" if frac > 0 else "limited")
    if langs:
        top = ", ".join(sorted(langs, key=langs.get, reverse=True)[:3])
        facts.append(f"Main languages: {top}.")
    return raw, facts, quality, sorted(set(notes))
