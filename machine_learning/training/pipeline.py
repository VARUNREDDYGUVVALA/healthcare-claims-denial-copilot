"""Train denial scores and build the reproducible static demo export."""
from collections import defaultdict
from datetime import date
import json
from pathlib import Path

import joblib
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.pipeline import make_pipeline

from data.generator.claims import PROCEDURES, generate
from data_engineering.ingestion.duckdb_extract import connect, import_data, rows
from generative_ai.retrieval.policies import explain, policy
from machine_learning.evaluation.holdout import CAPACITY, CUTOFF, DEMO_CLAIMS, evaluate, split
from machine_learning.feature_engineering.claims import baseline, claim_lines, features

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"


def serialize(value):
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(type(value))

def fit(train):
    model = make_pipeline(DictVectorizer(), LogisticRegression(max_iter=500))
    model.fit([features(line) for line in train], [line["status"] == "denied" for line in train])
    return model


def report(model, train, holdout):
    scores = model.predict_proba([features(line) for line in holdout])[:, 1]
    labels = [line["status"] == "denied" for line in holdout]
    result = {
        "cutoff": str(CUTOFF), "capacity": CAPACITY, "train_lines": len(train),
        "holdout_lines": len(holdout), "holdout_denials": sum(labels),
        "model": evaluate(holdout, scores),
        "rules": evaluate(holdout, [baseline(line) for line in holdout]),
    }
    result["model"]["brier_score"] = round(float(brier_score_loss(labels, scores)), 4)
    return result


def build():
    ARTIFACTS.mkdir(exist_ok=True)
    data = generate()
    with connect(ARTIFACTS / "claims.duckdb") as db:
        import_data(db, data)
        lines = claim_lines(db)
        train, holdout = split(lines)
        model = fit(train)
        scores = model.predict_proba([features(line) for line in lines])[:, 1]
        metrics = report(model, train, holdout)
        by_month = defaultdict(lambda: {"finalized": 0, "denied": 0, "reviews": 0})
        historical = sorted(data["decisions"], key=lambda decision: decision["id"])
        by_id = {line["id"]: line for line in lines}
        for decision in historical:
            by_month[str(by_id[decision["line_id"]]["submitted"])[:7]]["reviews"] += 1
        for line in lines:
            if line["status"] in ("denied", "approved") and line["claim_id"] not in DEMO_CLAIMS:
                month = by_month[str(line["submitted"])[:7]]
                month["finalized"] += 1
                month["denied"] += line["status"] == "denied"
        holdout_ids = {line["id"] for line in holdout}
        ranked = sorted(zip(lines, scores, strict=True), key=lambda item: (-item[1], item[0]["id"]))
        demo = {
            "lines": [{**line, "description": PROCEDURES[line["procedure"]], "risk": round(float(score), 6),
                       "staged": line["claim_id"] in DEMO_CLAIMS, "rules_score": baseline(line),
                       "holdout": line["id"] in holdout_ids, "explanation": explain(db, line)} for line, score in ranked],
            "metrics": metrics,
            "policies": data["policies"],
            "months": [{"month": month, **stats} for month, stats in sorted(by_month.items())],
            "unmatched": rows(db, "SELECT r.* FROM responses r LEFT JOIN lines l ON l.id=r.line_id WHERE l.id IS NULL ORDER BY r.id"),
            "decisions": historical,
        }
    joblib.dump(model, ARTIFACTS / "model.joblib")
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    encoded = json.dumps(demo, default=serialize, ensure_ascii=False, separators=(",", ":")) + "\n"
    (ARTIFACTS / "scored_claim_lines.json").write_text(encoded, encoding="utf-8")
    (ROOT / "apps/frontend/public/demo.json").write_text(encoded, encoding="utf-8")
    print(json.dumps(metrics, indent=2))

if __name__ == "__main__":
    build()
