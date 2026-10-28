import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from approvalflow.api import create_app
from approvalflow.policy import evaluate


@pytest.fixture
def system(settings, store, snapshot):
    class FakeGitHub:
        def snapshot(self, *_):
            return snapshot
    with TestClient(create_app(settings, store, FakeGitHub())) as client:
        yield client


def headers(letter="m"):
    return {"Authorization": "Bearer " + letter * 32}


def signed(settings, body):
    return {"X-Hub-Signature-256": "sha256=" + hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest(),
            "X-GitHub-Delivery": uuid.uuid4().hex, "X-GitHub-Event": "pull_request"}


def test_signed_webhook_and_redelivery(system, settings):
    body = json.dumps({"action": "opened", "repository": {"full_name": "example/project"}, "number": 7}).encode()
    hdr = signed(settings, body)
    assert system.post("/webhooks/github", content=body, headers=hdr).json()["status"] == "queued"
    assert system.post("/webhooks/github", content=body, headers=hdr).json()["status"] == "duplicate"
    assert system.post("/webhooks/github", content=body + b" ", headers=hdr).status_code == 401


def test_wrong_signature(system):
    assert system.post("/webhooks/github", content=b"{}").status_code == 401


def test_malformed_action_is_a_client_error(system, settings):
    body = json.dumps({"action": [], "number": 7, "repository": {"full_name": "example/project"}}).encode()
    assert system.post("/webhooks/github", content=body, headers=signed(settings, body)).status_code == 400


def test_boolean_pr_number_is_not_accepted(system):
    assert system.post("/reviews", headers=headers("o"), json={"repository": "example/project", "number": True}).status_code == 422


def test_pr_number_cannot_overflow_database_integer(system):
    assert system.post("/reviews", headers=headers("o"), json={"repository": "example/project", "number": 2**64}).status_code == 422


def test_dot_repository_name_is_valid_and_canonical(system, settings, store):
    settings.repositories.add("example/.github")
    response = system.post("/reviews", headers=headers("o"), json={"repository": "Example/.github", "number": 7})
    assert response.status_code == 202
    assert store.job(response.json()["job_id"])["repository"] == "example/.github"


@pytest.mark.parametrize("repository", ["example/.", "example/..", "example/../project"])
def test_repository_cannot_be_a_traversal_path(system, repository):
    assert system.post("/reviews", headers=headers("o"), json={"repository": repository, "number": 7}).status_code == 422


def test_health_reflects_database_outage(system, store, monkeypatch):
    from sqlalchemy.exc import OperationalError
    def unavailable():
        raise OperationalError("SELECT", {}, RuntimeError("database down"))
    monkeypatch.setattr(store, "ping", unavailable)
    assert system.get("/health").status_code == 503


def test_superseded_recommendation_cannot_be_resolved(system, store, snapshot, policy):
    old = store.record(snapshot, evaluate(snapshot, policy), policy)
    store.record(snapshot, evaluate(snapshot, policy), policy)
    assert request_resolution(system, old).status_code == 409
    assert store.decision(old)["resolution"] is None


def test_review_superseded_during_refresh_is_fenced_at_database_write(settings, store, snapshot, policy):
    old = store.record(snapshot, evaluate(snapshot, policy), policy)
    class Gateway:
        def snapshot(self, *_):
            store.record(snapshot, evaluate(snapshot, policy), policy)
            return snapshot
    with TestClient(create_app(settings, store, Gateway())) as client:
        assert request_resolution(client, old).status_code == 409
    assert store.decision(old)["resolution"] is None


def test_allowed_repository_is_filtered_before_result_limit(system, store, snapshot, policy):
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    other = snapshot.model_copy(deep=True)
    other.repository = "other/project"
    for i in range(101):
        other.number = i + 1
        store.record(other, evaluate(other, policy), policy)
    rows = system.get("/decisions", headers=headers()).json()
    assert [r["id"] for r in rows] == [key]


def test_resolution_requires_a_substantive_reason(system, store, snapshot, policy):
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    result = system.post(f"/decisions/{key}/resolve", headers=headers(), json={
        "action": "approve", "expected_revision": 1, "reason": " " * 20})
    assert result.status_code == 422
    assert store.decision(key)["resolution"] is None


def test_signed_malformed_json(system, settings):
    assert system.post("/webhooks/github", content=b"not json", headers=signed(settings, b"not json")).status_code == 400


def test_body_limit(system):
    assert system.post("/webhooks/github", content=b"x" * 1_048_577).status_code == 413


def test_authentication_and_roles(system):
    assert system.get("/decisions").status_code == 401
    ref = {"repository": "example/project", "number": 7}
    assert system.post("/reviews", json=ref, headers=headers()).status_code == 403
    assert system.post("/reviews", json=ref, headers=headers("o")).status_code == 202
    ref["repository"] = "other/private"
    assert system.post("/reviews", json=ref, headers=headers("o")).status_code == 403


def test_signed_hook_allowlist(system, settings):
    body = json.dumps({"action": "opened", "repository": {"full_name": "other/private"}, "number": 7}).encode()
    assert system.post("/webhooks/github", content=body, headers=signed(settings, body)).status_code == 403


def request_resolution(system, key, letter="m", revision=1, action="approve"):
    return system.post(f"/decisions/{key}/resolve", headers=headers(letter), json={
        "action": action, "expected_revision": revision, "reason": "Inspected changes and test results"})


def test_human_approval_and_audit(system, store, snapshot, policy):
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    assert request_resolution(system, key, "o").status_code == 403
    assert request_resolution(system, key, "c").status_code == 403
    assert request_resolution(system, key, revision=9).status_code == 409
    result = request_resolution(system, key)
    assert result.status_code == 200
    assert result.json()["github_action"] == "none"
    assert request_resolution(system, key).status_code == 409
    record = system.get(f"/decisions/{key}", headers=headers()).json()
    assert record["audit"][-1]["actor"] == "maintainer"


@pytest.mark.parametrize("mutation", ["head", "base", "ci", "policy", "patch"])
def test_changed_evidence_prevents_stale_approval(system, store, snapshot, policy, mutation):
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    if mutation == "head":
        snapshot.head_sha = "d" * 40
    elif mutation == "base":
        snapshot.base_sha = "d" * 40
    elif mutation == "ci":
        snapshot.checks[0].conclusion = "failure"
    elif mutation == "policy":
        policy.max_lines = 1  # Same version, different content must also invalidate.
    else:
        snapshot.files[0].patch = "+changed"
    assert request_resolution(system, key).status_code == 409
    assert store.decision(key)["resolution"] is None


def test_blocked_cannot_be_overridden(system, store, snapshot, policy):
    snapshot.checks.clear()
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    assert request_resolution(system, key).status_code == 409
    assert request_resolution(system, key, action="reject").status_code == 200


def test_review_recommendation_can_have_reasoned_human_signoff(system, store, snapshot, policy):
    snapshot.files[0].filename = "auth/permissions.md"
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    assert request_resolution(system, key).status_code == 200


def test_expired_recommendation_requires_new_request(system, store, snapshot, policy):
    import time
    from sqlalchemy import update
    from approvalflow.storage import decisions
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    with store.engine.begin() as db:
        db.execute(update(decisions).where(decisions.c.id == key).values(created_at=time.time() - 3601))
    assert request_resolution(system, key).status_code == 409
    refreshed = store.record(snapshot, evaluate(snapshot, policy), policy)
    assert request_resolution(system, refreshed).status_code == 200
