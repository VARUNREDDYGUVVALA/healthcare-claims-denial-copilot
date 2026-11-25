"""Evaluate the saved logistic model and rules on the same chronological holdout."""
import json

import joblib

from data_engineering.ingestion.duckdb_extract import connect
from machine_learning.evaluation.holdout import split
from machine_learning.feature_engineering.claims import claim_lines
from machine_learning.training.pipeline import ARTIFACTS, report


def main():
    model_path = ARTIFACTS / "model.joblib"
    if not model_path.exists() or not (ARTIFACTS / "claims.duckdb").exists():
        raise SystemExit("Run python -m scripts.generate_data and python -m scripts.train_models first.")
    with connect(ARTIFACTS / "claims.duckdb", read_only=True) as db:
        train, holdout = split(claim_lines(db))
    content = json.dumps(report(joblib.load(model_path), train, holdout), indent=2)
    (ARTIFACTS / "metrics.json").write_text(content + "\n")
    print(content)


if __name__ == "__main__":
    main()
