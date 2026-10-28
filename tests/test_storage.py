import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import update

from approvalflow.policy import evaluate
from approvalflow.service import process_one
from approvalflow.storage import jobs


def test_duplicate_delivery_is_one_job(store):
    delivery = uuid.uuid4().hex
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.enqueue(delivery, "example/project", 7), range(20)))
    assert sum(results) == 1


def test_only_one_worker_claims(store):
    store.enqueue(uuid.uuid4().hex, "example/project", 7)
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: store.claim(), range(8)))
    assert sum(c is not None for c in claims) == 1


def test_crashed_worker_reclaimed_and_fenced(store):
    store.enqueue(uuid.uuid4().hex, "example/project", 7)
    old = store.claim(lease_seconds=0)
    current = store.claim()
    assert current["attempts"] == 2
    assert not store.finish(old, decision_id="stale")
    assert store.finish(current, decision_id="fresh")
    assert store.job(current["id"])["decision_id"] == "fresh"


def test_retries_end_in_dead_letter(store):
    delivery = uuid.uuid4().hex
    store.enqueue(delivery, "example/project", 7)
    for _ in range(5):
        job = store.claim()
        assert job
        store.finish(job, error="TimeoutError")
        with store.engine.begin() as db:
            db.execute(update(jobs).where(jobs.c.id == delivery).values(available_at=0))
    assert store.job(delivery)["status"] == "dead"
    assert store.claim() is None


def test_replayed_work_has_one_decision(store, snapshot, policy):
    key = uuid.uuid4().hex
    recommendation = evaluate(snapshot, policy)
    first = store.record(snapshot, recommendation, policy, key)
    assert store.record(snapshot, recommendation, policy, key) == first
    assert len(store.events(first)) == 1
    assert "patch" not in store.decision(first)["evidence"]["files"][0]
    # A new request may refresh old evidence without reusing an expired decision.
    assert store.record(snapshot, recommendation, policy) != first


def test_only_one_human_resolution_and_audit_is_atomic(store, snapshot, policy):
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.resolve(key, 1, "maintainer", "approve", "Reviewed the evidence"), range(8)))
    assert sum(results) == 1
    assert len(store.events(key)) == 2
    assert store.decision(key)["revision"] == 2


def test_restart_preserves_jobs_and_decisions(store, snapshot, policy):
    from approvalflow.storage import Store
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    delivery = uuid.uuid4().hex
    store.enqueue(delivery, "example/project", 7)
    reopened = Store(store.engine.url)
    try:
        assert reopened.decision(key)["head_sha"] == snapshot.head_sha
        assert reopened.job(delivery)["status"] == "queued"
    finally:
        reopened.engine.dispose()


def test_worker_handles_job(store, snapshot, policy):
    class FakeGitHub:
        def snapshot(self, *_):
            return snapshot
    delivery = uuid.uuid4().hex
    store.enqueue(delivery, "example/project", 7)
    assert process_one(store, FakeGitHub(), policy)
    job = store.job(delivery)
    assert job["status"] == "done"
    assert store.decision(job["decision_id"])["recommendation"]["outcome"] == "READY"


def test_worker_failure_is_retryable_without_source_or_token_leaks(store, policy):
    class BrokenGitHub:
        def snapshot(self, *_):
            raise RuntimeError("secret token should never be stored")
    delivery = uuid.uuid4().hex
    store.enqueue(delivery, "example/project", 7)
    assert process_one(store, BrokenGitHub(), policy)
    job = store.job(delivery)
    assert job["status"] == "retry"
    assert job["error"] == "RuntimeError"
    assert job["decision_id"] is None


def test_final_expired_lease_becomes_dead(store):
    delivery = uuid.uuid4().hex
    store.enqueue(delivery, "example/project", 7)
    for _ in range(5):
        assert store.claim(lease_seconds=0)
    assert store.claim() is None
    assert store.job(delivery)["status"] == "dead"
