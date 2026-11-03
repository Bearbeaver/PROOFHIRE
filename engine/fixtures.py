"""Recorded signals for FICTIONAL demo repositories (used by the seeded demo accounts).

These let the full pipeline - submission -> queue -> engine -> ProofScore -> feedback - be demonstrated offline.
Real public repositories are analysed live through the GitHub API; nothing here is used for them.
"""
from __future__ import annotations


def _readme(sections: list[str], extra_words: int, code_blocks: int) -> str:
    out = ["# Project\n"]
    for s in sections:
        out.append(f"## {s}\n" + ("Lorem details about this section. " * max(1, extra_words // max(1, len(sections))) + "\n"))
        if code_blocks:
            out.append("```\nexample command\n```\n")
            code_blocks -= 1
    return "\n".join(out)


def _paths(ext: str, src: int, tests: int, *, ci=False, docs=False, docker=False, lint=False, license=True,
           gitignore=True, manifest="go.mod", dirs=("cmd", "internal/api", "internal/store", "internal/worker", "pkg/util")):
    paths = []
    for i in range(src):
        paths.append(f"{dirs[i % len(dirs)]}/module_{i}{ext}")
    test_dir = "tests" if ext in (".py", ".js", ".ts", ".tsx") else dirs[0]
    for i in range(tests):
        stem = f"module_{i}"
        paths.append(f"{test_dir}/{stem}_test{ext}" if ext == ".go" else f"{test_dir}/test_{stem}{ext}")
    if manifest:
        paths.append(manifest)
    if ci:
        paths.append(".github/workflows/ci.yml")
    if docs:
        paths += ["docs/architecture.md", "docs/design-decisions.md"]
    if docker:
        paths.append("Dockerfile")
    if lint:
        paths.append(".golangci.yml" if ext == ".go" else ".eslintrc.json" if ext in (".js", ".ts", ".tsx") else ".flake8")
    if license:
        paths.append("LICENSE")
    if gitignore:
        paths.append(".gitignore")
    paths.append("README.md")
    return paths


def _repo(full_name, description, topics, languages, paths, readme, commits, stars, forks, created, pushed, homepage=False, size_kb=800):
    return {
        "found": True, "full_name": full_name, "description": description, "topics": topics,
        "stars": stars, "forks": forks, "size_kb": size_kb, "languages": languages,
        "license": any(p == "LICENSE" for p in paths), "homepage": homepage,
        "created_at": created, "pushed_at": pushed, "commits": commits, "readme": readme, "paths": paths,
    }


FIXTURES = {
    # Backend (Go): decent project, thin tests / docs
    "alexchen/queuely": _repo(
        "alexchen/queuely", "Distributed task queue in Go with worker pools, retries and a dead-letter queue",
        ["go", "queue", "grpc", "distributed-systems", "worker"], {"Go": 180000, "Shell": 4000, "Dockerfile": 900},
        _paths(".go", 44, 7, ci=True, docker=True, lint=False, docs=False),
        _readme(["Overview", "Install", "Usage", "Benchmarks"], 220, 2), 143, 38, 6, "2026-01-02T10:00:00Z", "2026-10-02T09:00:00Z", size_kb=1900),
    # Same project after the candidate added tests, docs and a linter
    "alexchen/queuely-v2": _repo(
        "alexchen/queuely-v2", "Distributed task queue in Go with worker pools, retries, dead-letter queue and benchmarks",
        ["go", "queue", "grpc", "distributed-systems", "worker", "benchmarks"], {"Go": 195000, "Shell": 4000, "Dockerfile": 900},
        _paths(".go", 46, 24, ci=True, docker=True, lint=True, docs=True),
        _readme(["Overview", "Architecture", "Install", "Usage", "Design decisions", "Benchmarks"], 900, 4), 201, 41, 7, "2026-01-02T10:00:00Z", "2026-10-15T09:00:00Z", homepage=True, size_kb=2100),
    # Frontend (React)
    "priyapatel/loomly": _repo(
        "priyapatel/loomly", "Realtime collaborative design canvas built with React, TypeScript and WebSockets",
        ["react", "typescript", "websockets", "canvas", "frontend"], {"TypeScript": 120000, "CSS": 18000, "HTML": 2000},
        _paths(".tsx", 38, 9, ci=True, lint=True, manifest="package.json", dirs=("src/components", "src/hooks", "src/canvas", "src/state", "src/pages")),
        _readme(["Overview", "Getting started", "Usage", "Accessibility"], 400, 2), 96, 27, 4, "2026-02-01T10:00:00Z", "2026-09-20T09:00:00Z", homepage=True),
    # Data engineering: weak tests
    "marcuswebb/streamline": _repo(
        "marcuswebb/streamline", "Kafka-based ETL pipeline with Airflow DAGs",
        ["kafka", "airflow", "etl", "python", "data-pipeline"], {"Python": 60000, "Shell": 1500},
        _paths(".py", 18, 1, ci=False, lint=False, manifest="requirements.txt", dirs=("dags", "etl", "connectors", "utils")),
        _readme(["Overview", "Setup"], 120, 1), 41, 5, 1, "2026-03-01T10:00:00Z", "2026-07-01T09:00:00Z", size_kb=300),
    # Full-stack API: strong
    "sofiareyes/ledgerly": _repo(
        "sofiareyes/ledgerly", "Personal finance REST API with Node.js, PostgreSQL, Docker and JWT auth",
        ["nodejs", "postgresql", "docker", "rest", "api", "jwt", "backend"], {"JavaScript": 90000, "TypeScript": 40000, "Dockerfile": 1200},
        _paths(".ts", 52, 30, ci=True, docker=True, lint=True, docs=True, manifest="package.json", dirs=("src/routes", "src/services", "src/db", "src/middleware", "src/auth")),
        _readme(["Overview", "Architecture", "Install", "Usage", "API reference", "Design decisions"], 1100, 5), 312, 88, 16, "2025-11-01T10:00:00Z", "2026-10-10T09:00:00Z", homepage=True, size_kb=2600),
    # ML
    "danielkim/visionkit": _repo(
        "danielkim/visionkit", "On-device image classifier with PyTorch and CoreML export",
        ["pytorch", "machine-learning", "coreml", "classification", "inference"], {"Python": 70000, "Jupyter Notebook": 40000},
        _paths(".py", 22, 4, ci=False, lint=True, manifest="requirements.txt", dirs=("visionkit/models", "visionkit/data", "visionkit/train", "visionkit/export")),
        _readme(["Overview", "Install", "Training", "Results"], 300, 2), 77, 12, 2, "2026-03-15T10:00:00Z", "2026-09-01T09:00:00Z"),
    # Beginner projects for low-score demos
    "demo-user/todo-list": _repo(
        "demo-user/todo-list", "my first todo app", [], {"JavaScript": 6000, "HTML": 2000, "CSS": 1200},
        ["index.html", "app.js", "style.css", "README.md"], "# todo-list\nA simple todo app.\n", 4, 0, 0, "2026-09-01T10:00:00Z", "2026-09-03T09:00:00Z", size_kb=40),
    "demo-user/api-starter": _repo(
        "demo-user/api-starter", "Small Flask API", ["flask", "api", "python"], {"Python": 14000},
        _paths(".py", 6, 0, ci=False, lint=False, manifest="requirements.txt", license=False, dirs=("app", "app/routes")),
        "# API starter\n\n## Run\nrun the app with flask.\n", 12, 1, 0, "2026-08-01T10:00:00Z", "2026-08-20T09:00:00Z", size_kb=120),
}
