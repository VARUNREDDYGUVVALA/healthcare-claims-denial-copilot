"""Evaluate citations against explicit synthetic service-date cases."""
from datetime import date
import json
from pathlib import Path

from data.generator.claims import TABLES
from data.policies.catalog import policy_sections
from data_engineering.ingestion.duckdb_extract import connect, import_data
from generative_ai.retrieval.policies import policy


def evaluate_golden_cases():
    path = Path(__file__).resolve().parents[1] / "golden_datasets/policy_cases.json"
    cases = json.loads(path.read_text())
    with connect() as db:
        extract = {table: [] for table in TABLES}
        extract["policies"] = policy_sections()
        import_data(db, extract)
        results = []
        for case in cases:
            passage = policy(db, {**case, "service": date.fromisoformat(case["service"])})
            results.append({**case, "actual": passage["id"] if passage else None})
    return results


def main():
    results = evaluate_golden_cases()
    passed = sum(item["expected"] == item["actual"] for item in results)
    print(json.dumps({"passed": passed, "total": len(results), "cases": results}, indent=2))
    return int(passed != len(results))


if __name__ == "__main__":
    raise SystemExit(main())
