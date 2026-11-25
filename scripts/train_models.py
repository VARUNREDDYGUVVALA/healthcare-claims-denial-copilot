"""Fit the denial model using the chronological training split."""
import joblib

from data_engineering.ingestion.duckdb_extract import connect
from machine_learning.evaluation.holdout import split
from machine_learning.feature_engineering.claims import claim_lines
from machine_learning.training.pipeline import ARTIFACTS, fit


def main():
    path = ARTIFACTS / "claims.duckdb"
    if not path.exists():
        raise SystemExit("Run python -m scripts.generate_data first.")
    with connect(path, read_only=True) as db:
        train, _ = split(claim_lines(db))
    joblib.dump(fit(train), ARTIFACTS / "model.joblib")
    print(f"Trained on {len(train):,} claim lines.")


if __name__ == "__main__":
    main()
