"""Synthetic training data for the ProofScore model.

IMPORTANT - READ BEFORE TRUSTING ANY SCORE
------------------------------------------
The ProofHire proposal calls for a human-labelled dataset (several evaluators scoring real projects on the
seven dimensions). That dataset does not exist yet, so this module generates a *placeholder* one:

1. sample plausible project feature vectors (``sample_raw``),
2. label them with a hand-written rubric (``rubric``) plus noise that imitates three human raters.

A model trained on this therefore reproduces the rubric; its cross-validated R^2 says how well it learned the
rubric, NOT how well it predicts what real evaluators think. Replace it by dropping a CSV with the real labels at
``engine/data/labelled_projects.csv`` (columns = FEATURE_NAMES + ``y_<dimension>`` points) and re-running
``python -m engine.train``.
"""
from __future__ import annotations

import math

import numpy as np

from .features import DIM_KEYS, DIM_MAX, FEATURE_NAMES, FIELD_KEYWORDS


def sat(x: float, k: float) -> float:
    return 1.0 - math.exp(-max(x, 0.0) / k)


def _c(x: float) -> float:
    return max(0.0, min(1.0, x))


def rubric(raw: dict) -> dict[str, float]:
    """Fraction (0..1) of each dimension's points a careful reviewer would award for these measurements."""
    a = raw["analysed_fraction"]
    has_code = raw["file_count"] > 0
    portfolio = sat(raw["portfolio_words"], 700)
    rel = 0.10 + 0.42 * raw["field_overlap"] + 0.22 * raw["lang_field_match"] + 0.14 * raw["skill_overlap"] + 0.12 * sat(raw["desc_len"], 300)
    rel *= 0.35 + 0.65 * a
    tq = (0.25 * sat(raw["source_files"], 25) + 0.15 * min(1, raw["language_count"] / 3) + 0.15 * sat(raw["dir_count"], 10)
          + 0.12 * raw["has_manifest"] + 0.15 * sat(raw["commits"], 60) + 0.08 * raw["has_ci"] + 0.10 * raw["has_docker"])
    comp = (0.35 * sat(raw["source_files"], 60) + 0.20 * sat(raw["size_kb"], 2000) + 0.20 * sat(raw["dir_count"], 25)
            + 0.15 * min(1, raw["language_count"] / 4) + 0.10 * sat(raw["span_days"], 180))
    cq = (0.30 * raw["has_linter"] + 0.25 * min(1, raw["test_ratio"] / 0.3) + 0.15 * raw["has_gitignore"]
          + 0.15 * sat(raw["max_depth"], 3) + 0.15 * raw["has_ci"])
    doc = (0.30 * sat(raw["readme_len"], 2500) + 0.15 * sat(raw["readme_headings"], 8) + 0.15 * sat(raw["readme_code_blocks"], 4)
           + 0.10 * raw["readme_install"] + 0.10 * raw["readme_usage"] + 0.10 * raw["readme_arch"] + 0.10 * raw["has_docs_dir"])
    doc = max(doc, 0.5 * portfolio) if not has_code else doc + 0.1 * portfolio
    test = (0.50 * min(1, raw["test_ratio"] / 0.3) + 0.20 * sat(raw["test_files"], 8) + 0.15 * raw["has_test_dir"] + 0.15 * raw["has_ci"])
    imp = (0.25 * sat(raw["stars"], 30) + 0.10 * sat(raw["forks"], 10) + 0.20 * raw["has_homepage"] + 0.15 * raw["recency"]
           + 0.10 * portfolio + 0.10 * min(1, raw["cert_known_issuer"] / 2) + 0.10 * min(1, raw["cert_verifiable"] / 2))
    out = {"relevance": rel, "technical_quality": tq, "complexity": comp, "code_quality": cq,
           "documentation": doc, "testing": test, "impact": imp}
    return {k: _c(v) for k, v in out.items()}


def sample_raw(rng: np.random.Generator) -> dict:
    field = rng.choice(list(FIELD_KEYWORDS))
    q = rng.beta(2.2, 2.0)       # craftsmanship
    scale = rng.beta(1.7, 2.3)   # ambition / project size
    raw = dict.fromkeys(FEATURE_NAMES, 0.0)
    has_gh = rng.random() < 0.9
    has_pf = rng.random() < 0.3
    n_cert = int(rng.choice([0, 0, 1, 1, 2]))
    raw["n_github"], raw["n_portfolio"], raw["cert_count"] = int(has_gh) + int(has_gh and rng.random() < 0.2), int(has_pf), n_cert
    raw["n_items"] = raw["n_github"] + raw["n_portfolio"] + n_cert
    kws = len(FIELD_KEYWORDS[field])
    items = analysed = 0.0
    sk = rng.beta(1.5, 2.0)
    raw["desc_len"] = float(max(0, rng.normal(120 + 500 * q, 120)))

    for _ in range(raw["n_github"]):
        items += 1
        if rng.random() < 0.93:
            analysed += 1
            src = max(1, int(math.exp(rng.normal(1.6 + 3.0 * scale, 0.45))))
            files = int(src * rng.uniform(1.4, 3.0)) + int(rng.integers(3, 12))
            tests = int(src * float(np.clip(rng.normal(0.38 * q ** 1.4, 0.08), 0, 0.9)))
            raw["source_files"] += src
            raw["file_count"] += files
            raw["test_files"] += tests
            raw["dir_count"] += max(1, int(src / rng.uniform(3, 8)))
            raw["max_depth"] = max(raw["max_depth"], int(rng.integers(1, 3 + int(4 * scale))))
            raw["size_kb"] += float(math.exp(rng.normal(4.5 + 4.0 * scale, 0.6)))
            raw["commits"] += int(math.exp(rng.normal(2.2 + 3.0 * (0.5 * scale + 0.5 * q), 0.6)))
            raw["stars"] += int(max(0, rng.exponential(1 + 15 * scale * q) - 0.5))
            raw["forks"] += int(max(0, rng.exponential(0.5 + 4 * scale * q) - 0.5))
            raw["has_test_dir"] = max(raw["has_test_dir"], float(tests > 0))
            for k, p in (("has_ci", 0.15 + 0.7 * q), ("has_license", 0.2 + 0.6 * q), ("has_docs_dir", 0.05 + 0.6 * q * q),
                         ("has_docker", 0.1 + 0.5 * scale), ("has_linter", 0.1 + 0.7 * q), ("has_gitignore", 0.5 + 0.45 * q),
                         ("has_manifest", 0.6 + 0.35 * q), ("has_homepage", 0.05 + 0.4 * q * scale)):
                raw[k] = max(raw[k], float(rng.random() < p))
            raw["readme_len"] += float(max(30, rng.normal(300 + 3200 * q, 350)))
            raw["readme_headings"] += int(max(0, rng.normal(1 + 9 * q, 1.5)))
            raw["readme_code_blocks"] += int(max(0, rng.normal(4 * q, 1)))
            raw["readme_images"] += int(max(0, rng.normal(2 * q, 1)))
            for k, p in (("readme_install", 0.15 + 0.8 * q), ("readme_usage", 0.15 + 0.8 * q), ("readme_arch", 0.05 + 0.6 * q * q)):
                raw[k] = max(raw[k], float(rng.random() < p))
            raw["language_count"] = max(raw["language_count"], int(1 + rng.integers(0, 2 + int(3 * scale))))
            raw["span_days"] = max(raw["span_days"], int(math.exp(rng.normal(3.0 + 2.5 * scale, 0.7))))
            raw["recency"] = max(raw["recency"], float(np.clip(rng.beta(3, 1.5), 0, 1)))
            raw["field_overlap"] = max(raw["field_overlap"], float(np.clip(rng.beta(2, 2) * (0.5 + 0.5 * q) + 0.1, 0, 1)))
            raw["lang_field_match"] = max(raw["lang_field_match"], float(np.clip(rng.beta(3, 1.5), 0, 1)))
    for _ in range(raw["n_portfolio"]):
        items += 1
        if rng.random() < 0.85:
            analysed += 1
            raw["portfolio_reachable"] = 1.0
            raw["portfolio_words"] += int(max(20, rng.normal(150 + 900 * q, 200)))
            raw["portfolio_headings"] += int(max(0, rng.normal(2 + 6 * q, 1.5)))
            raw["field_overlap"] = max(raw["field_overlap"], float(np.clip(rng.beta(1.8, 2.5), 0, 1)))
    for _ in range(n_cert):
        items += 1
        analysed += 1 if rng.random() < 0.9 else 0
        raw["cert_known_issuer"] += float(rng.random() < 0.6)
        raw["cert_verifiable"] += float(rng.random() < 0.5)
        raw["cert_field_match"] = max(raw["cert_field_match"], float(rng.random() < 0.6))
        raw["field_overlap"] = max(raw["field_overlap"], float(np.clip(rng.beta(1.5, 3), 0, 1)))
    raw["test_ratio"] = min(2.0, raw["test_files"] / max(1.0, raw["source_files"]))
    raw["skill_overlap"] = float(np.clip(sk, 0, 1))
    raw["analysed_fraction"] = analysed / items if items else 0.0
    if raw["analysed_fraction"] == 0:  # nothing could be analysed: only description-derived signals exist
        raw["field_overlap"] = float(np.clip(rng.beta(1.2, 4), 0, 1)) * 0.5
        raw["lang_field_match"] = 0.0
    return raw


def generate(n: int = 2500, seed: int = 7, raters: int = 3):
    """Returns (X_raw list[dict], Y array (n x 7) of FRACTIONS, as the average of simulated raters)."""
    rng = np.random.default_rng(seed)
    X, Y = [], []
    for _ in range(n):
        raw = sample_raw(rng)
        base = rubric(raw)
        votes = []
        for _r in range(raters):
            bias = rng.normal(0, 0.03)
            votes.append([float(np.clip(base[k] + bias + rng.normal(0, 0.06), 0, 1)) for k in DIM_KEYS])
        X.append(raw)
        Y.append(np.mean(votes, axis=0))
    return X, np.array(Y)


def points_to_fraction(points_row: dict) -> list[float]:
    return [points_row[k] / DIM_MAX[k] for k in DIM_KEYS]
