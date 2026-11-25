import json

from fastapi.testclient import TestClient

from apps.api.main import app


TOKEN = "s" * 32
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
CLAIM = {
    "payer_code": "NORTHSTAR", "plan_code": "DEMO", "procedure_code": "IMG-01",
    "service_date": "2026-03-30", "units": 1, "coverage_active": "yes",
    "authorization_present": "yes", "authorization_date": "2026-04-01", "duplicate_confirmed": "no",
}


def configure(monkeypatch):
    monkeypatch.setenv("COPILOT_ANALYST_TOKEN", TOKEN)
    monkeypatch.setenv("COPILOT_SUPERVISOR_TOKEN", "r" * 32)
    monkeypatch.delenv("COPILOT_SCREENING_POLICIES", raising=False)


def test_live_requests_and_policy_date_boundary(monkeypatch):
    configure(monkeypatch)
    with TestClient(app) as client:
        assert client.get("/api/screening/capabilities").json() == {"available": True, "policy_mode": "synthetic"}
        assert client.post("/api/screening", json=CLAIM).status_code == 401
        earlier = client.post("/api/screening", json=CLAIM, headers=HEADERS)
        assert earlier.status_code == 200
        assert earlier.headers["Cache-Control"] == "no-store"
        assert earlier.json()["recommendation"] == "ready_for_review"
        assert earlier.json()["matched_policy"]["policy_id"] == "NS-IMG-2026-v1"
        later = client.post("/api/screening", json={**CLAIM, "service_date": "2026-04-01"}, headers=HEADERS).json()
        assert later["recommendation"] == "needs_review"
        assert later["issues"][0]["code"] == "AUTH_TIME_UNKNOWN"
        assert later["matched_policy"]["policy_id"] == "NS-IMG-2026-v2"
        absent = client.post("/api/screening", headers=HEADERS, json={
            **CLAIM, "authorization_present": "no", "authorization_date": None
        }).json()
        assert absent["recommendation"] == "correct_before_submission"
        gap = client.post("/api/screening", json={**CLAIM, "plan_code": "UNMAPPED"}, headers=HEADERS).json()
        assert gap["recommendation"] == "needs_review" and not gap["matched_policy"]
        assert client.post("/api/screening", json={**CLAIM, "member_name": "Synthetic name"}, headers=HEADERS).status_code == 422


def test_local_policy_catalog_is_used_and_fails_closed(monkeypatch, tmp_path):
    configure(monkeypatch)
    file = tmp_path / "policies.json"
    monkeypatch.setenv("COPILOT_SCREENING_POLICIES", str(file))
    policy = {
        **{key: CLAIM[key] for key in ("payer_code", "plan_code", "procedure_code")},
        "policy_id": "TEST-RULE", "effective_start": "2026-01-01", "effective_end": "2027-01-01",
        "authorization": "not_required", "max_units": 1, "source_url": "https://example.org/policy",
    }
    file.write_text(json.dumps([policy]))
    with TestClient(app) as client:
        result = client.post("/api/screening", json={**CLAIM, "units": 2}, headers=HEADERS).json()
        assert result["policy_mode"] == "configured"
        assert result["matched_policy"]["source_url"] == "https://example.org/policy"
        assert result["recommendation"] == "correct_before_submission"
        assert result["issues"][0]["code"] == "UNIT_LIMIT"
        file.write_text(json.dumps([policy, {**policy, "policy_id": "OVERLAP"}]))
        ambiguous = client.post("/api/screening", json=CLAIM, headers=HEADERS).json()
        assert ambiguous["recommendation"] == "needs_review"
        assert ambiguous["issues"][0]["code"] == "POLICY_AMBIGUOUS"
        file.write_text("invalid")
        assert client.post("/api/screening", json=CLAIM, headers=HEADERS).status_code == 503
