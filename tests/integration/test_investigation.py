import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient

from apps.api import main as api
from agentic_ai.workflows import investigation
from mcp_server import server as mcp_server
from data.generator.claims import generate
from data_engineering.ingestion.duckdb_extract import connect, import_data
from machine_learning.feature_engineering.claims import claim_lines
from generative_ai.retrieval.policies import explain

ANALYST = {"Authorization": "Bearer " + "a" * 32}
SUPERVISOR = {"Authorization": "Bearer " + "s" * 32}


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(mcp_server, "ARTIFACTS", tmp_path)
    data = generate()
    ids = {"CLM-GUIDE", "CLM-LEDGER"}
    data["claims"] = [row for row in data["claims"] if row["id"] in ids]
    data["lines"] = [row for row in data["lines"] if row["claim_id"] in ids]
    members = {row["member"] for row in data["claims"]}
    for key in ("authorizations", "eligibility"):
        data[key] = [row for row in data[key] if row["member"] in members]
    lines = {row["id"] for row in data["lines"]}
    data["responses"] = [row for row in data["responses"] if row["line_id"] in lines]
    data["decisions"] = []
    path = tmp_path / "claims.duckdb"
    with connect(path) as db:
        import_data(db, data)
    monkeypatch.setenv("COPILOT_ANALYST_TOKEN", "a" * 32)
    monkeypatch.setenv("COPILOT_SUPERVISOR_TOKEN", "s" * 32)
    return path


def test_authorized_review_is_durable_and_final(prepared):
    with TestClient(api.app) as client:
        request = {"line_id": "CLM-LEDGER-1"}
        assert client.get("/api/lines/CLM-LEDGER-1").status_code == 401
        assert client.post("/api/investigations", json=request).status_code == 401
        assert client.post("/api/investigations", json={"line_id": "CLM-GUIDE-2"}, headers=ANALYST).status_code == 409
        created = client.post("/api/investigations", json=request, headers=ANALYST)
        assert created.status_code == 201, created.text
        item = created.json()
        assert item["status"] == "awaiting_review"
        assert item["policy"]["id"] == "NS-IMG-2026-v1"
        assert "A-LEDGER-1" in item["appeal_draft"]
        assert item["trace"][-1] == "Awaiting human review"
        assert item["audit"][0]["role"] == "analyst"
        path = f"/api/investigations/{item['id']}"
        decision = {"decision": "approve", "note": "Verified fictional source evidence."}
        assert client.post(path + "/decision", json=decision, headers=ANALYST).status_code == 403
    with TestClient(api.app) as restarted:
        assert restarted.get(path, headers=ANALYST).json()["status"] == "awaiting_review"
        result = restarted.post(path + "/decision", json=decision, headers=SUPERVISOR)
        assert result.status_code == 200
        assert result.json()["status"] == "approved"
        assert [event["event"] for event in result.json()["audit"]] == ["investigation_prepared", "review_approved"]
        assert restarted.post(path + "/decision", json=decision, headers=SUPERVISOR).status_code == 409


def test_missing_evidence_never_produces_an_appeal(prepared):
    with connect(prepared) as db:
        line = next(item for item in claim_lines(db) if item["id"] == "CLM-GUIDE-1")
        result = investigation.investigate(db, line)
        assert result["appeal_draft"] is None
        assert result["recorded_reason"] == "Prior authorization required"
        assert "No matching authorization" in result["findings"][0]
        without_policy = investigation.investigate(db, {**line, "payer": "Juniper Mutual"})
        assert without_policy["policy"] is None
        assert without_policy["appeal_draft"] is None
        assert without_policy["recorded_reason"] == result["recorded_reason"]


def test_temporary_tool_failure_retries_once(prepared, monkeypatch):
    original = investigation.verify
    calls = 0

    def flaky(state):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("Transient tool failure")
        return original(state)

    monkeypatch.setattr(investigation, "verify", flaky)
    graph = investigation.build_graph()
    with connect(prepared) as db:
        line = next(item for item in claim_lines(db) if item["id"] == "CLM-LEDGER-1")
        result = graph.invoke({"line": line, "explanation": explain(db, line)})
    assert calls == 2
    assert result["trace"].count("Policy and evidence verification") == 1


def test_read_only_mcp_tools(prepared):
    tools = asyncio.run(mcp_server.server.list_tools())
    assert {tool.name for tool in tools} == {"applicable_policies", "claim_evidence"}
    policies = mcp_server.applicable_policies("Northstar Health", "IMG-01", date(2026, 4, 1))
    assert [policy["id"] for policy in policies] == ["NS-IMG-2026-v2"]
    assert mcp_server.claim_evidence("CLM-LEDGER-1")["explanation"]["policy"]["id"] == "NS-IMG-2026-v1"
