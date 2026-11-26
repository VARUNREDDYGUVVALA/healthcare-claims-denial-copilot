from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.routes.workspace import Credentials, database, provision


CLAIM = {
    "payer_code": "NORTHSTAR", "plan_code": "DEMO", "procedure_code": "IMG-01",
    "service_date": "2026-03-30", "units": 1, "coverage_active": "yes",
    "authorization_present": "no", "duplicate_confirmed": "no",
}
PASSWORD = "fictional-test-password"
ROOT = "/api/workspace"


def test_role_handoff_and_persisted_history(monkeypatch, tmp_path):
    monkeypatch.setenv("COPILOT_WORKSPACE_DB", str(tmp_path / "workspace.sqlite3"))
    monkeypatch.delenv("COPILOT_SCREENING_POLICIES", raising=False)
    with database() as db:
        for username, role in [("owner", "customer"), ("other", "customer"), ("manager", "manager")]:
            provision(db, Credentials(username=username, password=PASSWORD), role)

    with TestClient(app) as client:
        def login(username, role):
            response = client.post(ROOT + "/sessions", json={"username": username, "password": PASSWORD})
            assert response.status_code == 200
            assert response.json()["role"] == role
            return {"Authorization": "Bearer " + response.json()["token"]}

        assert client.get(ROOT + "/cases").status_code == 401
        owner = login("owner", "customer")
        other = login("other", "customer")
        manager = login("manager", "manager")
        account = {"username": "analyst", "password": PASSWORD}
        assert client.post(ROOT + "/analysts", json=account, headers=owner).status_code == 403
        assert client.post(ROOT + "/analysts", json=account, headers=manager).status_code == 201
        analyst = login("analyst", "analyst")
        assert client.post(ROOT + "/cases", json=CLAIM, headers=analyst).status_code == 403
        assert client.post(ROOT + "/cases", json={**CLAIM, "member_name": "test"}, headers=owner).status_code == 422
        preview = client.post(ROOT + "/screening", json=CLAIM, headers=owner)
        assert preview.json()["recommendation"] == "correct_before_submission"
        assert client.get(ROOT + "/cases", headers=manager).json()["cases"] == []
        submitted = client.post(ROOT + "/cases", json=CLAIM, headers=owner)
        assert submitted.status_code == 201
        path = ROOT + "/cases/" + submitted.json()["id"]
        assert client.get(path, headers=other).status_code == 404
        assert client.get(path, headers=analyst).status_code == 404
        screening = client.get(path, headers=owner).json()["screening"]
        assert screening["matched_policy"]["policy_id"] == "NS-IMG-2026-v1"
        assert screening["recommendation"] == "correct_before_submission"

        assert client.post(path + "/assignment", headers=manager, json={"analyst": "other"}).status_code == 422
        assert client.post(path + "/assignment", headers=manager, json={"analyst": "analyst"}).status_code == 204
        assert client.get(path, headers=analyst).json()["status"] == "assigned"
        assert client.post(path + "/escalation", headers=analyst).status_code == 204
        outcome = {"outcome": "needs_review"}
        assert client.post(path + "/review", headers=analyst, json=outcome).status_code == 409
        assert client.post(path + "/resolution", headers=manager, json=outcome).status_code == 204
        customer_detail = client.get(path, headers=owner).json()
        assert customer_detail["outcome"] == "needs_review"
        assert [event["action"] for event in customer_detail["events"]] == ["submitted", "assigned", "escalated", "resolved"]
        assert "actor" not in customer_detail["events"][-1]
        assert client.get(path, headers=manager).json()["events"][-1]["actor"] == "manager"
        assert client.delete(ROOT + "/sessions/current", headers=owner).status_code == 204
        assert client.get(path, headers=owner).status_code == 401

    with TestClient(app) as client:
        assert client.get(path, headers=manager).json()["status"] == "reviewed"
