"""Train, evaluate, score and export the static demo from the same evidence as the API."""
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import re

import joblib
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import make_pipeline

from .data import PROCEDURES, REASONS, connect, generate, import_data, rows

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
CUTOFF = date(2025, 9, 1)
CAPACITY = 3
DEMO_CLAIMS = ("CLM-GUIDE", "CLM-EARLY")
POLICY_TERMS = {"AUTH": {"authorization", "preauthorization"},
                "ELIG": {"coverage", "eligibility"}, "DUP": {"duplicate", "resubmitting"}}
SUGGESTIONS = {"AUTH": "Verify authorization", "ELIG": "Verify coverage", "DUP": "Check for duplicate"}

def claim_lines(db):
    return rows(db, """
        WITH coverage AS (
            SELECT l.id, list(struct_pack(id := e.id, starts := e.starts, ends := e.ends, recorded := e.recorded) ORDER BY e.id) AS records FROM lines l
            JOIN claims c ON c.id=l.claim_id JOIN eligibility e
            ON e.member=c.member AND e.payer=c.payer AND l.service >= e.starts
            AND l.service < e.ends AND e.recorded < c.submitted GROUP BY l.id
        ), auth AS (
            SELECT l.id, list(struct_pack(id := a.id, starts := a.starts, ends := a.ends, recorded := a.recorded) ORDER BY a.id) AS records FROM lines l
            JOIN claims c ON c.id=l.claim_id JOIN authorizations a
            ON a.member=c.member AND a.payer=c.payer AND a.procedure=l.procedure
            AND l.service >= a.starts AND l.service < a.ends AND a.recorded < c.submitted GROUP BY l.id
        ), responses_by_claim AS (
            SELECT l.claim_id, count(*) FILTER (WHERE r.status='denied') AS denied,
                count(*) FILTER (WHERE r.status='approved') AS approved,
                count(*) FILTER (WHERE r.status='pending' OR r.status IS NULL) AS pending
            FROM lines l LEFT JOIN responses r ON r.line_id=l.id GROUP BY l.claim_id
        )
        SELECT l.*, c.member, c.payer, c.submitted,
            coalesce(e.records, []) AS eligibility, coalesce(a.records, []) AS authorizations,
            (SELECT list(p.id ORDER BY p.id) FROM lines p JOIN claims pc ON pc.id=p.claim_id
             WHERE pc.member=c.member AND pc.payer=c.payer AND p.service=l.service
             AND p.procedure=l.procedure AND (pc.submitted<c.submitted OR
             (p.claim_id=l.claim_id AND p.id<l.id))) AS duplicates,
            r.status, r.reason, r.received,
            CASE WHEN rc.denied>0 AND rc.approved>0 THEN 'partially denied'
                 WHEN rc.pending>0 THEN 'pending'
                 WHEN rc.denied>0 THEN 'denied' ELSE 'approved' END AS claim_status
        FROM lines l JOIN claims c ON c.id=l.claim_id
        LEFT JOIN coverage e ON e.id=l.id LEFT JOIN auth a ON a.id=l.id
        LEFT JOIN responses r ON r.line_id=l.id JOIN responses_by_claim rc ON rc.claim_id=l.claim_id
        ORDER BY c.submitted, l.id
    """)

def features(line):
    return {
        "payer": line["payer"], "procedure": line["procedure"],
        "missing_eligibility": int(not line["eligibility"]),
        "missing_imaging_authorization": int(line["procedure"] == "IMG-01" and not line["authorizations"]),
        "possible_duplicate": int(bool(line["duplicates"])),
    }

def split(lines):
    labeled = [line for line in lines if line["status"] in ("denied", "approved")
               and line["claim_id"] not in DEMO_CLAIMS]
    return (
        [line for line in labeled if line["submitted"] < CUTOFF and line["received"] < CUTOFF],
        [line for line in labeled if line["submitted"] >= CUTOFF],
    )

def evaluate(lines, scores):
    daily = defaultdict(list)
    actual = [int(line["status"] == "denied") for line in lines]
    for line, score, label in zip(lines, scores, actual, strict=True):
        daily[line["submitted"]].append((float(score), line["id"], label))
    reviewed = [
        label for day in daily.values()
        for _, _, label in sorted(day, key=lambda item: (-item[0], item[1]))[:CAPACITY]
    ]
    return {"pr_auc": round(float(average_precision_score(actual, scores)), 4),
            "precision_at_capacity": round(sum(reviewed) / len(reviewed), 4),
            "reviewed": len(reviewed)}

def baseline(line):
    f = features(line)
    return .55 * f["missing_eligibility"] + .38 * f["missing_imaging_authorization"] + .48 * f["possible_duplicate"]

def policy(db, line):
    if not line["reason"]:
        return None
    candidates = rows(db, """
        SELECT * FROM policies WHERE payer=? AND procedure=? AND starts<=? AND ends>?
    """, [line["payer"], line["procedure"], line["service"], line["service"]])
    tokens = POLICY_TERMS[line["reason"]]
    def relevance(candidate):
        return len(tokens & set(re.findall(r"\w+", candidate["excerpt"].lower())))
    ranked = [candidate for candidate in candidates if relevance(candidate)]
    return min(ranked, key=lambda candidate: (-relevance(candidate), candidate["id"]), default=None)

def explain(db, line):
    if line["status"] != "denied":
        return None
    citation = policy(db, line)
    return {"reason": REASONS[line["reason"]], "code": line["reason"], "policy": citation,
            "action": SUGGESTIONS[line["reason"]] if citation else "Request payer clarification"}

def serialize(value):
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(type(value))

def build():
    ARTIFACTS.mkdir(exist_ok=True)
    data = generate()
    with connect(ARTIFACTS / "claims.duckdb") as db:
        import_data(db, data)
        lines = claim_lines(db)
        train, holdout = split(lines)
        model = make_pipeline(DictVectorizer(), LogisticRegression(max_iter=500))
        model.fit([features(line) for line in train], [line["status"] == "denied" for line in train])
        scores = model.predict_proba([features(line) for line in lines])[:, 1]
        metrics = {
            "cutoff": str(CUTOFF), "capacity": CAPACITY, "train_lines": len(train),
            "holdout_lines": len(holdout), "holdout_denials": sum(line["status"] == "denied" for line in holdout),
            "model": evaluate(holdout, model.predict_proba([features(line) for line in holdout])[:, 1]),
            "rules": evaluate(holdout, [baseline(line) for line in holdout]),
        }
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
        ranked = sorted(zip(lines, scores, strict=True), key=lambda item: (-item[1], item[0]["id"]))
        demo = {
            "lines": [{**line, "description": PROCEDURES[line["procedure"]], "risk": round(float(score), 6),
                       "staged": line["claim_id"] in DEMO_CLAIMS, "explanation": explain(db, line)} for line, score in ranked],
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
    (ROOT / "frontend/public/demo.json").write_text(encoded, encoding="utf-8")
    print(json.dumps(metrics, indent=2))

if __name__ == "__main__":
    build()
