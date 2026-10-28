import time

from fastapi.testclient import TestClient

from approvalflow.api import create_app
from approvalflow.demo import OPERATOR_TOKEN, REVIEWER_TOKEN, create_demo_app


def bearer(token):
    return {"Authorization": "Bearer " + token}


def test_live_config_does_not_expose_credentials(settings, store):
    with TestClient(create_app(settings, store, object())) as client:
        response = client.get("/app-config")
        assert response.json() == {"demo": False}
        for secret in [settings.operator_token, *settings.reviewers.values()]:
            assert secret not in response.text
        assert client.get("/session").status_code == 401


def test_session_exposes_role_and_trusted_policy(settings, store):
    with TestClient(create_app(settings, store, object())) as client:
        response = client.get("/session", headers=bearer(settings.reviewers["maintainer"]))
        assert response.json()["role"] == "reviewer"
        assert response.json()["policy"] == settings.policy.model_dump()
        assert response.json()["publication_enabled"] is False
        assert client.get("/session", headers=bearer(settings.operator_token)).json()["role"] == "operator"


def test_built_frontend_is_served_without_authorizing_api_access(settings, store):
    with TestClient(create_app(settings, store, object())) as client:
        response = client.get("/")
        assert response.status_code == 200, "Build the frontend before running the full integration suite"
        assert 'id="root"' in response.text
        assert response.headers["cache-control"] == "no-cache"
        assert client.get("/decisions").status_code == 401


def test_demo_uses_real_policy_and_refuses_github_publication(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_WRITE_ENABLED", "true")
    with TestClient(create_demo_app("sqlite:///" + (tmp_path / "demo.db").as_posix())) as client:
        config = client.get("/app-config").json()
        assert config["demo_tokens"]["reviewer"] == REVIEWER_TOKEN
        rows = client.get("/decisions", headers=bearer(REVIEWER_TOKEN)).json()
        assert len(rows) == 8
        assert {r["recommendation"]["outcome"] for r in rows} == {"READY", "REVIEW", "BLOCKED"}
        row = next(r for r in rows if r["number"] == 142)
        assert row["evidence"]["title"] == "Add rate limiting to the checkout API"
        approved = client.post(f'/decisions/{row["id"]}/resolve', headers=bearer(REVIEWER_TOKEN), json={
            "action": "approve", "expected_revision": 1, "reason": "Inspected this sample payment change and its test updates."})
        assert approved.status_code == 200
        assert client.post(f'/decisions/{row["id"]}/publish', headers=bearer(REVIEWER_TOKEN)).status_code == 403
        saved = client.get(f'/decisions/{row["id"]}', headers=bearer(REVIEWER_TOKEN)).json()
        assert saved["audit"][-1]["action"] == "approve"


def test_demo_worker_processes_operator_requests_without_network(tmp_path):
    with TestClient(create_demo_app("sqlite:///" + (tmp_path / "queue.db").as_posix())) as client:
        response = client.post("/reviews", headers=bearer(OPERATOR_TOKEN), json={"repository": "tanay-labs/commerce-api", "number": 143})
        job_id = response.json()["job_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get(f"/jobs/{job_id}", headers=bearer(OPERATOR_TOKEN)).json()
            if job["status"] == "done":
                break
            time.sleep(.05)
        assert job["status"] == "done"
        record = client.get(f'/decisions/{job["decision_id"]}', headers=bearer(REVIEWER_TOKEN)).json()
        assert record["recommendation"]["outcome"] == "READY"


def test_demo_sessions_are_isolated(tmp_path):
    first = create_demo_app("sqlite:///" + (tmp_path / "first.db").as_posix())
    second = create_demo_app("sqlite:///" + (tmp_path / "second.db").as_posix())
    with TestClient(first) as one, TestClient(second) as two:
        ids_one = {r["id"] for r in one.get("/decisions", headers=bearer(REVIEWER_TOKEN)).json()}
        ids_two = {r["id"] for r in two.get("/decisions", headers=bearer(REVIEWER_TOKEN)).json()}
        assert ids_one.isdisjoint(ids_two)
