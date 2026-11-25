"""Chronological splitting and daily-capacity evaluation."""
from collections import defaultdict
from datetime import date

from sklearn.metrics import average_precision_score, roc_auc_score

CUTOFF = date(2025, 9, 1)
CAPACITY = 3
DEMO_CLAIMS = ("CLM-GUIDE", "CLM-EARLY", "CLM-LEDGER")


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
            "reviewed": len(reviewed),
            "recall_at_capacity": round(sum(reviewed) / sum(actual), 4),
            "roc_auc": round(float(roc_auc_score(actual, scores)), 4)}
