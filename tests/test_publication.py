from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from approvalflow.api import create_app
from approvalflow.github import GitHub
from approvalflow.policy import evaluate


@pytest.fixture
def publisher(settings, store, snapshot, policy):
    class Gateway:
        calls = 0
        fail = False

        def snapshot(self, *_):
            return snapshot

        def publish_approval(self, current, decision_id, actor, reason):
            self.calls += 1
            assert current.head_sha == snapshot.head_sha
            if self.fail:
                raise TimeoutError("Token and source must not leak")
            return {"review_id": 42, "url": "https://github.com/example/project/pull/7#pullrequestreview-42"}
    gateway = Gateway()
    settings.github_write_enabled = True
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    with TestClient(create_app(settings, store, gateway)) as client:
        yield client, gateway, key


def publish(client, key, token="m"):
    return client.post(f"/decisions/{key}/publish", headers={"Authorization": "Bearer " + token * 32})


def approve(store, key):
    assert store.resolve(key, 1, "maintainer", "approve", "Inspected the code and verification")


def test_publication_disabled_by_configuration(publisher, settings, store):
    client, gateway, key = publisher
    settings.github_write_enabled = False
    approve(store, key)
    assert publish(client, key).status_code == 403
    assert gateway.calls == 0


def test_unapproved_or_wrong_reviewer_cannot_publish(publisher, store):
    client, gateway, key = publisher
    assert publish(client, key).status_code == 403
    approve(store, key)
    assert publish(client, key, "c").status_code == 403
    assert publish(client, key, "o").status_code == 403
    assert gateway.calls == 0


def test_publish_once_and_return_existing_result(publisher, store):
    client, gateway, key = publisher
    approve(store, key)
    assert publish(client, key).json()["state"] == "published"
    assert publish(client, key).json()["review_id"] == "42"
    assert gateway.calls == 1
    assert store.events(key)[-1]["action"] == "published"


def test_changed_commit_prevents_publication(publisher, store, snapshot):
    client, gateway, key = publisher
    approve(store, key)
    snapshot.head_sha = "d" * 40
    assert publish(client, key).status_code == 409
    assert store.publication(key) is None
    assert gateway.calls == 0


def test_superseded_approval_cannot_be_published(publisher, store, snapshot, policy):
    client, gateway, old = publisher
    approve(store, old)
    current = store.record(snapshot, evaluate(snapshot, policy), policy)
    assert store.resolve(current, 1, "maintainer", "reject", "This newer review rejects the change")
    assert publish(client, old).status_code == 409
    assert gateway.calls == 0


def test_review_superseded_during_refresh_cannot_reserve_publication(publisher, store, snapshot, policy, monkeypatch):
    client, gateway, old = publisher
    approve(store, old)
    def refreshed(*_):
        store.record(snapshot, evaluate(snapshot, policy), policy)
        return snapshot
    monkeypatch.setattr(gateway, "snapshot", refreshed)
    assert publish(client, old).status_code == 409
    assert gateway.calls == 0


def test_timeout_is_uncertain_and_never_automatically_retried(publisher, store):
    client, gateway, key = publisher
    approve(store, key)
    gateway.fail = True
    assert publish(client, key).status_code == 503
    assert store.publication(key)["state"] == "uncertain"
    assert store.publication(key)["error"] == "TimeoutError"
    assert publish(client, key).status_code == 409
    assert gateway.calls == 1


def test_simultaneous_publications_send_one_review(publisher, store):
    client, gateway, key = publisher
    approve(store, key)
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda _: publish(client, key).status_code, range(8)))
    assert all(c in {200, 409} for c in codes)
    assert gateway.calls == 1


def test_github_review_request_is_bound_to_inspected_commit(snapshot):
    def handler(request):
        import json
        data = json.loads(request.content)
        assert request.method == "POST"
        assert request.url.path == "/repos/example/project/pulls/7/reviews"
        assert data["commit_id"] == snapshot.head_sha
        assert data["event"] == "APPROVE"
        assert "approvalflow:test-decision" in data["body"]
        return httpx.Response(200, json={"id": 42, "html_url": "https://github.com/example/review"})
    github = GitHub(client=httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler)))
    assert github.publish_approval(snapshot, "test-decision", "maintainer", "Inspected code")["review_id"] == 42
