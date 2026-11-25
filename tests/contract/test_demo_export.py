import json

from machine_learning.training import pipeline


def test_export_contract():
    demo = json.loads((pipeline.ROOT / "apps/frontend/public/demo.json").read_text())
    assert demo["metrics"]["capacity"] == 3
    assert all(0 <= line["risk"] <= 1 for line in demo["lines"])
    assert next(line["risk"] for line in demo["lines"] if line["id"] == "CLM-GUIDE-1") >= .65
