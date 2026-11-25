"""Reproducible challenger evaluation for the synthetic denial-ranking task."""
from collections import defaultdict
from datetime import date
from hashlib import sha256
import json

from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import brier_score_loss
from sklearn.pipeline import make_pipeline
from threadpoolctl import threadpool_limits

from machine_learning.evaluation.holdout import CAPACITY, CUTOFF, DEMO_CLAIMS, evaluate
from machine_learning.feature_engineering.claims import baseline, features
from machine_learning.training.pipeline import fit

VALIDATION_START = date(2025, 7, 1)
CHAMPION = "logistic"
MIN_PR_GAIN = 0.005
FEATURE_DRIFT_ALERT = 0.10


def partition(lines):
    """Use only labels available at each boundary before model selection."""
    windows = {"train": [], "validation": [], "test": []}
    for line in lines:
        if line["status"] not in ("approved", "denied") or line["claim_id"] in DEMO_CLAIMS:
            continue
        submitted, received = line["submitted"], line["received"]
        if submitted >= CUTOFF:
            windows["test"].append(line)
        elif submitted >= VALIDATION_START and received < CUTOFF:
            windows["validation"].append(line)
        elif submitted < VALIDATION_START and received < VALIDATION_START:
            windows["train"].append(line)
    return windows


def labels(lines):
    return [int(line["status"] == "denied") for line in lines]


def calibration(observed, scores):
    bins = defaultdict(list)
    for actual, score in zip(observed, scores, strict=True):
        bins[min(9, int(score * 10))].append((actual, score))
    return [
        {"lower": index / 10, "count": len(items),
         "predicted": round(sum(score for _, score in items) / len(items), 4),
         "observed": round(sum(actual for actual, _ in items) / len(items), 4)}
        for index, items in sorted(bins.items())
    ]


def metrics(lines, scores, probabilistic):
    result = evaluate(lines, scores)
    if probabilistic:
        result["brier"] = round(float(brier_score_loss(labels(lines), scores)), 4)
    return result


def promotion(validation, candidate):
    champion = validation[CHAMPION]
    metrics_candidate = validation[candidate]
    return [
        {"name": "PR-AUC improves by at least 0.005",
         "passed": round(metrics_candidate["pr_auc"] - champion["pr_auc"], 4) >= MIN_PR_GAIN},
        {"name": "Daily-capacity precision does not decline",
         "passed": metrics_candidate["precision_at_capacity"] >= champion["precision_at_capacity"]},
        {"name": "Brier score does not increase",
         "passed": metrics_candidate["brier"] <= champion["brier"]},
    ]


def slices(lines, scores):
    grouped = defaultdict(list)
    for line, score in zip(lines, scores, strict=True):
        for key in ("payer", "procedure"):
            grouped[(key, line[key])].append((line, score))
    result = []
    for (dimension, value), items in sorted(grouped.items()):
        records, values = zip(*items, strict=True)
        denied = sum(labels(records))
        result.append({
            "dimension": dimension, "value": value, "count": len(records), "denials": denied,
            "brier": round(float(brier_score_loss(labels(records), values)), 4),
            "denial_rate": round(denied / len(records), 4),
            "mean_score": round(sum(values) / len(values), 4),
        })
    return result


def feature_drift(train, test):
    rows = []
    for key in ("missing_eligibility", "missing_imaging_authorization", "possible_duplicate"):
        reference = sum(features(line)[key] for line in train) / len(train)
        current = sum(features(line)[key] for line in test) / len(test)
        rows.append({"feature": key, "train_rate": round(reference, 4), "test_rate": round(current, 4),
                     "delta": round(current - reference, 4), "alert": abs(current - reference) >= FEATURE_DRIFT_ALERT})
    return rows


@threadpool_limits.wrap(limits=1)
def build_report(lines):
    windows = partition(lines)
    if any(len(set(labels(records))) != 2 for records in windows.values()):
        raise ValueError("Each governance split must contain both outcomes.")
    train = windows["train"]
    x_train = [features(line) for line in train]
    y_train = labels(train)
    models = {
        CHAMPION: fit(train),
        "random_forest": make_pipeline(DictVectorizer(), RandomForestClassifier(
            n_estimators=100, max_depth=6, min_samples_leaf=12, random_state=43, n_jobs=1,
        )).fit(x_train, y_train),
        "gradient_boosting": make_pipeline(DictVectorizer(sparse=False), HistGradientBoostingClassifier(
            max_iter=100, max_leaf_nodes=12, min_samples_leaf=20, random_state=43,
        )).fit(x_train, y_train),
    }

    def score_window(window):
        x = [features(line) for line in window]
        scores = {name: model.predict_proba(x)[:, 1] for name, model in models.items()}
        scores["rules"] = [baseline(line) for line in window]
        return scores, {name: metrics(window, values, name != "rules") for name, values in scores.items()}

    _, validation = score_window(windows["validation"])
    gates = {name: promotion(validation, name) for name in models if name != CHAMPION}
    passing = [name for name, checks in gates.items() if all(check["passed"] for check in checks)]
    selected = min(passing, key=lambda name: (-validation[name]["pr_auc"], name), default=CHAMPION)

    test = windows["test"]
    test_scores, test_results = score_window(test)
    release_gates = []
    if selected != CHAMPION:
        candidate, reference = test_results[selected], test_results[CHAMPION]
        release_gates = [
            {"name": "Frozen-test PR-AUC does not decline", "passed": candidate["pr_auc"] >= reference["pr_auc"]},
            {"name": "Frozen-test daily-capacity precision does not decline",
             "passed": candidate["precision_at_capacity"] >= reference["precision_at_capacity"]},
            {"name": "Frozen-test Brier score does not increase", "passed": candidate["brier"] <= reference["brier"]},
        ]
    release = "eligible_for_manual_review" if release_gates and all(check["passed"] for check in release_gates) else "retain_reference"
    # Hash the actual scoring inputs and labels rather than the output artifact.
    manifest_rows = [
        (name, line["id"], str(line["submitted"]), str(line["received"]), features(line), line["status"])
        for name, records in windows.items() for line in sorted(records, key=lambda item: item["id"])
    ]
    return {
        "validation_start": str(VALIDATION_START), "test_start": str(CUTOFF), "review_capacity": CAPACITY,
        "dataset_sha256": sha256(json.dumps(manifest_rows, sort_keys=True).encode()).hexdigest(),
        "windows": {name: {"lines": len(records), "denials": sum(labels(records))} for name, records in windows.items()},
        "reference": CHAMPION, "recommended": selected,
        "validation": validation, "gates": gates, "test": test_results,
        "release": release, "release_gates": release_gates,
        "calibration": calibration(labels(test), test_scores[selected]),
        "test_slices": slices(test, test_scores[selected]),
        "feature_drift": feature_drift(train, test),
    }
