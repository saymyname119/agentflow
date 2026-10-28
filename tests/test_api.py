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
