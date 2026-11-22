from datetime import date
import json

import pytest
from fastapi.testclient import TestClient

from copilot import api, pipeline
from copilot.data import connect, generate, import_data

@pytest.fixture(scope="module")
def db():
    with connect() as connection:
        import_data(connection, generate())
        yield connection

@pytest.fixture(scope="module")
def lines(db):
    return {line["id"]: line for line in pipeline.claim_lines(db)}

def test_idempotent_import_and_unmatched(db):
    before = db.execute("SELECT count(*) FROM responses").fetchone()
    import_data(db, generate())
    assert db.execute("SELECT count(*) FROM responses").fetchone() == before
    assert db.execute("SELECT r.id FROM responses r ANTI JOIN lines l ON r.line_id=l.id").fetchall() == [("R-UNMATCHED",)]

def test_conflict_rolls_back(db):
    data = generate()
    data["lines"][0]["amount"] += 1
    with pytest.raises(ValueError, match="Conflicting identifier in lines"):
        import_data(db, data)
    assert db.execute("SELECT amount FROM lines WHERE id=?", [data["lines"][0]["id"]]).fetchone()[0] == data["lines"][0]["amount"] - 1

def test_partial_denials(lines):
    denied, approved = (lines[f"CLM-GUIDE-{i}"] for i in (1, 2))
    assert denied["status"] == "denied"
    assert approved["status"] == "approved"
    assert denied["claim_status"] == approved["claim_status"] == "partially denied"
    assert any(line["status"] == "pending" for line in lines.values())

def test_chronological_split_and_feature_contract(lines):
    train, holdout = pipeline.split(lines.values())
    assert train and holdout
    assert max(line["submitted"] for line in train) < pipeline.CUTOFF <= min(line["submitted"] for line in holdout)
    assert all(line["received"] < pipeline.CUTOFF for line in train)
    assert all(line["status"] != "pending" and line["claim_id"] not in pipeline.DEMO_CLAIMS for line in train + holdout)
    sample = train[0]
    assert pipeline.features(sample) == pipeline.features({**sample, "status": "denied", "reason": "AUTH"})

@pytest.mark.parametrize(("day", "version"), [
    (date(2024, 12, 31), None), (date(2025, 1, 1), "v1"),
    (date(2025, 6, 30), "v1"), (date(2025, 7, 1), "v2"), (date(2026, 1, 1), "2026-v1"),
    (date(2026, 3, 30), "2026-v1"), (date(2026, 4, 2), "2026-v2"), (date(2026, 7, 1), None),
])
def test_policy_boundary(db, lines, day, version):
    excerpt = pipeline.policy(db, {**lines["CLM-GUIDE-1"], "service": day})
    assert (excerpt["id"] if excerpt else None) == (f"NS-IMG-{version}" if version else None)

def test_missing_extract_and_policy_evidence(db, lines):
    assert any(line["status"] == "approved" and not line["eligibility"] for line in lines.values())
    assert any(line["status"] == "approved" and line["procedure"] == "IMG-01"
               and not line["authorizations"] for line in lines.values())
    example = {**lines["CLM-GUIDE-1"], "payer": "Juniper Mutual"}
    explanation = pipeline.explain(db, example)
    assert explanation == {"reason": "Prior authorization required", "code": "AUTH", "policy": None,
                           "action": "Request payer clarification"}
    assert pipeline.policy(db, {**lines["CLM-GUIDE-1"], "procedure": "LAB-02"}) is None
    assert pipeline.policy(db, {**lines["CLM-GUIDE-1"], "reason": "DUP"}) is None

def test_api_decision_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "ARTIFACTS", tmp_path)
    with connect(tmp_path / "claims.duckdb") as db:
        import_data(db, generate())
    client = TestClient(api.app)
    assert client.get("/api/unmatched-responses").json()[0]["id"] == "R-UNMATCHED"
    assert client.get("/api/lines/CLM-GUIDE-1").json()["explanation"]["policy"]["id"] == "NS-IMG-v2"
    data = {"action": "Verify authorization", "note": "Check portal"}
    response = client.post("/api/lines/CLM-GUIDE-1/decisions", json=data)
    assert response.status_code == 201
    assert client.get("/api/lines/CLM-GUIDE-1").json()["decisions"] == [response.json()]
    assert client.post("/api/lines/CLM-GUIDE-2/decisions", json=data).status_code == 409

def test_export_contract():
    demo = json.loads((pipeline.ROOT / "frontend/public/demo.json").read_text())
    assert demo["metrics"]["capacity"] == 3
    assert all(0 <= line["risk"] <= 1 for line in demo["lines"])
    assert next(line["risk"] for line in demo["lines"] if line["id"] == "CLM-GUIDE-1") >= .65
