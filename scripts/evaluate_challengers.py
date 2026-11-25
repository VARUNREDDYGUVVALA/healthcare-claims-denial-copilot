"""Evaluate challengers and publish the credential-free governance snapshot."""
import json

from data_engineering.ingestion.duckdb_extract import connect
from machine_learning.evaluation.governance import build_report
from machine_learning.feature_engineering.claims import claim_lines
from machine_learning.training.pipeline import ARTIFACTS, ROOT


def main():
    database = ARTIFACTS / "claims.duckdb"
    if not database.exists():
        raise SystemExit("Run python -m scripts.generate_data first.")
    with connect(database, read_only=True) as db:
        results = build_report(claim_lines(db))
    content = json.dumps(results, indent=2) + "\n"
    (ARTIFACTS / "model-governance.json").write_text(content)
    (ROOT / "apps/frontend/public/model-governance.json").write_text(content)
    print(content)


if __name__ == "__main__":
    main()
