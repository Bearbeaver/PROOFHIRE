"""ProofScore model: training (with model comparison) and prediction."""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import synthetic
from .features import DIM_KEYS, DIM_MAX, DIMENSIONS, FEATURE_NAMES, to_vector

HERE = Path(__file__).resolve().parent
MODEL_PATH = HERE / "models" / "proofscore_model.joblib"
METRICS_PATH = HERE / "models" / "metrics.json"
LABELLED_CSV = HERE / "data" / "labelled_projects.csv"
WEIGHTS = np.array([DIM_MAX[k] for k in DIM_KEYS])


def candidates():
    """The algorithms compared (proposal risk table: compare multiple ML algorithms)."""
    return {
        "ridge_baseline": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "random_forest": RandomForestRegressor(n_estimators=120, min_samples_leaf=2, random_state=0, n_jobs=1),
        "gradient_boosting": MultiOutputRegressor(
            GradientBoostingRegressor(n_estimators=140, max_depth=3, learning_rate=0.08, subsample=0.9, random_state=0)),
    }


def load_dataset(n_synthetic: int):
    """Human-labelled CSV if present, otherwise the synthetic placeholder."""
    if LABELLED_CSV.exists():
        X, Y = [], []
        with open(LABELLED_CSV, newline="") as f:
            for row in csv.DictReader(f):
                raw = {k: float(row[k]) for k in FEATURE_NAMES}
                X.append(raw)
                Y.append([float(row[f"y_{k}"]) / DIM_MAX[k] for k in DIM_KEYS])
        return X, np.array(Y), "human-labelled CSV"
    X, Y = synthetic.generate(n_synthetic)
    return X, Y, "synthetic placeholder (NOT human-labelled)"


def _metrics(y_true_frac, y_pred_frac):
    yt, yp = (y_true_frac * WEIGHTS).sum(axis=1), (np.clip(y_pred_frac, 0, 1) * WEIGHTS).sum(axis=1)  # overall /10
    return {
        "mae": float(mean_absolute_error(yt, yp)),
        "rmse": float(np.sqrt(mean_squared_error(yt, yp))),
        "r2": float(r2_score(yt, yp)),
    }


def train(n_synthetic: int = 2500, folds: int = 5, verbose: bool = True) -> dict:
    t0 = time.time()
    raws, Y, source = load_dataset(n_synthetic)
    X = np.array([to_vector(r) for r in raws])
    report = {}
    for name, est in candidates().items():
        oof = np.zeros_like(Y)
        for tr, te in KFold(folds, shuffle=True, random_state=1).split(X):
            m = candidates()[name]
            m.fit(X[tr], Y[tr])
            oof[te] = m.predict(X[te])
        report[name] = _metrics(Y, oof)
        report[name]["per_dimension_r2"] = {k: float(r2_score(Y[:, i], np.clip(oof[:, i], 0, 1))) for i, k in enumerate(DIM_KEYS)}
        if verbose:
            r = report[name]
            print(f"  {name:18s} CV  MAE={r['mae']:.3f}  RMSE={r['rmse']:.3f}  R2={r['r2']:.3f}  (overall points /10)")
    best = min(report, key=lambda k: report[k]["rmse"])
    final = candidates()[best]
    final.fit(X, Y)
    version = f"{best}-v1"
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": final, "version": version, "trained_on": source, "n": len(raws)}, MODEL_PATH)
    meta = {"selected": best, "version": version, "trained_on": source, "samples": len(raws), "cv_folds": folds,
            "cv_results": report, "seconds": round(time.time() - t0, 1),
            "note": "Metrics measure agreement with the training labels. With synthetic labels they say nothing about agreement with human evaluators."}
    METRICS_PATH.write_text(json.dumps(meta, indent=2))
    if verbose:
        print(f"  selected: {best}  ({meta['seconds']}s)  trained on: {source}")
    return meta


class ProofScoreModel:
    def __init__(self, path: Path = MODEL_PATH):
        blob = joblib.load(path)
        self.model, self.version, self.trained_on = blob["model"], blob["version"], blob["trained_on"]

    def predict(self, raw: dict) -> dict[str, float]:
        """Points per dimension (0..max)."""
        frac = np.clip(self.model.predict(np.array([to_vector(raw)]))[0], 0.0, 1.0)
        return {k: round(float(f) * DIM_MAX[k], 2) for k, f in zip(DIM_KEYS, frac)}


def ensure_model(retrain_if_unloadable: bool = True) -> ProofScoreModel:
    """Load the saved model; train one on first start (or if it was saved by an incompatible scikit-learn)."""
    if MODEL_PATH.exists():
        try:
            return ProofScoreModel()
        except Exception as e:  # pickle from another sklearn version etc.
            if not retrain_if_unloadable:
                raise
            print(f"[engine] saved model unusable ({e.__class__.__name__}); retraining")
    print("[engine] training ProofScore model (first start only)...")
    train(n_synthetic=1800, folds=3)
    return ProofScoreModel()


def model_card() -> dict:
    return json.loads(METRICS_PATH.read_text()) if METRICS_PATH.exists() else {}
