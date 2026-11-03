"""Turns sub-scores plus measured signals into annotations (strengths + recommended actions).

Deterministic and template-based on purpose: every sentence can be traced to a measured fact (NFR8, explainability).
An LLM could later rephrase these, but it must not invent findings.
"""
from __future__ import annotations

from .features import DIM_MAX, DIMENSIONS

LABEL = {k: l for k, l, _ in DIMENSIONS}

ACTIONS = {
    "testing": [
        ("no_tests", "Add automated unit tests for the core logic (start with the code that handles errors and edge cases)."),
        ("no_ci", "Run the tests automatically on every push with a CI workflow (e.g. GitHub Actions)."),
        (None, "Increase test coverage: add tests for failure paths, not only the happy path."),
    ],
    "documentation": [
        ("short_readme", "Expand the README: what the project does, how to install it and a short usage walkthrough."),
        ("no_code_examples", "Add runnable usage examples (code blocks) to the README."),
        ("no_arch_docs", "Document architectural decisions - a short ARCHITECTURE.md or decision records explaining why, not just what."),
        (None, "Add a docs section or diagram that explains how the main components fit together."),
    ],
    "code_quality": [
        ("no_linter", "Add a linter/formatter configuration so style and common bugs are checked automatically."),
        ("no_tests", "Untested code is hard to refactor safely - add tests, then remove duplicated code."),
        (None, "Split large modules into smaller single-purpose ones and remove duplicated code."),
    ],
    "complexity": [
        (None, "Extend the project with a harder problem (e.g. concurrency, persistence, caching, auth or background jobs) and explain the trade-offs you made."),
    ],
    "technical_quality": [
        ("no_ci", "Add CI and a dependency manifest/lockfile so the project builds reproducibly."),
        (None, "Improve structure and error handling, and show sustained development with meaningful commits."),
    ],
    "relevance": [
        (None, "State the target skills explicitly in the README and repository topics so the project clearly demonstrates the role you are applying for."),
    ],
    "impact": [
        ("no_demo", "Deploy a live demo (or add screenshots/GIFs) and link it from the repository."),
        (None, "Show real-world use: users, a published package/release, benchmarks or a write-up of results."),
    ],
}


def build_feedback(points: dict[str, float], notes: list[str], quality: str, facts: list[str]):
    strengths, recs = [], []
    for key, label, mx in DIMENSIONS:
        frac = points[key] / mx
        if frac >= 0.75:
            strengths.append(f"{label}: strong ({points[key]:.1f}/{mx:g}).")
    if "no_tests" not in notes and points["testing"] / DIM_MAX["testing"] >= 0.5:
        strengths.append("Automated tests are present.")
    for key, label, mx in DIMENSIONS:
        frac = points[key] / mx
        if frac >= 0.65:
            continue
        chosen = []
        for note, text in ACTIONS.get(key, []):
            if note is None or note in notes:
                chosen.append(text)
            if len(chosen) == 2:
                break
        gain = round((mx - points[key]) * 0.6, 1)
        for t in chosen:
            recs.append({"dimension": key, "label": label, "text": t, "potential_gain": gain})
    recs.sort(key=lambda r: -r["potential_gain"])
    if quality != "full":
        msg = ("None of your evidence could be analysed - make sure repositories are public and links are reachable, then resubmit."
               if quality == "limited" else
               "Some of your evidence could not be analysed (private repository or unreachable link); it earned no credit.")
        recs.insert(0, {"dimension": "evidence", "label": "Evidence access", "text": msg, "potential_gain": 1.0})
    return strengths, recs[:8]
