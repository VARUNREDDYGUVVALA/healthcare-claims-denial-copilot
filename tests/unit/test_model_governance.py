from datetime import date

from machine_learning.evaluation.governance import partition, promotion


def line(id, submitted, received, status="denied", claim_id="CLM-1000"):
    return {"id": id, "submitted": date.fromisoformat(submitted), "received": date.fromisoformat(received),
            "status": status, "claim_id": claim_id}


def test_partitions_use_labels_available_at_the_boundary():
    records = [
        line("known-train", "2025-06-20", "2025-06-30"),
        line("late-train", "2025-06-20", "2025-07-01"),
        line("known-validation", "2025-07-01", "2025-08-31"),
        line("late-validation", "2025-08-29", "2025-09-01"),
        line("test", "2025-09-01", "2025-09-06"),
        line("pending", "2025-09-01", "2025-09-06", status="pending"),
        line("guided", "2025-09-01", "2025-09-06", claim_id="CLM-GUIDE"),
    ]
    assert {key: [item["id"] for item in value] for key, value in partition(records).items()} == {
        "train": ["known-train"], "validation": ["known-validation"], "test": ["test"],
    }


def test_promotion_requires_operational_precision_and_calibration_as_well_as_ranking():
    comparison = {
        "logistic": {"pr_auc": .77, "precision_at_capacity": .65, "brier": .09},
        "candidate": {"pr_auc": .82, "precision_at_capacity": .64, "brier": .08},
    }
    assert [criterion["passed"] for criterion in promotion(comparison, "candidate")] == [True, False, True]
