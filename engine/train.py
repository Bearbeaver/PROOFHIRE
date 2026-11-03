"""Retrain the ProofScore model:  python -m engine.train

Uses engine/data/labelled_projects.csv (human labels) when present, otherwise the synthetic placeholder dataset."""
from .model import train

if __name__ == "__main__":
    print(train(n_synthetic=2500, folds=5))
