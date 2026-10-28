"""Concurrency/recovery experiment. Run only against a dedicated test database."""
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from approvalflow.models import Policy, Snapshot
from approvalflow.policy import evaluate
from approvalflow.storage import Store, jobs

ROOT = Path(__file__).resolve().parents[1]


def main():
    url = os.getenv("RELIABILITY_DATABASE_URL", "sqlite:///" + (ROOT / "evaluation/reliability.db").as_posix())
    store = Store(url)
    with store.engine.connect() as db:
        if db.execute(select(func.count()).select_from(jobs)).scalar_one():
            raise SystemExit("Use an empty, dedicated reliability database")
    snapshot = Snapshot.model_validate_json((ROOT / "examples/docs-pr.json").read_text())
    policy = Policy.model_validate_json((ROOT / "policy.json").read_text())
    recommendation = evaluate(snapshot, policy)
    started = time.perf_counter()
    delivery = uuid.uuid4().hex
    with ThreadPoolExecutor(max_workers=16) as pool:
        inserted = sum(pool.map(lambda _: store.enqueue(delivery, snapshot.repository, snapshot.number), range(1000)))
    job = store.claim()
    assert job["id"] == delivery and store.finish(job, decision_id="dedup-experiment")
    winners, events = 0, 0
    with ThreadPoolExecutor(max_workers=32) as pool:
        for _ in range(100):
            decision_id = store.record(snapshot, recommendation, policy)
            successes = sum(pool.map(lambda _: store.resolve(decision_id, 1, "maintainer", "approve", "Synthetic concurrent review"), range(32)))
            winners += successes
            events += sum(e["action"] == "approve" for e in store.events(decision_id))
            assert successes == 1
    recovered = 0
    for _ in range(20):
        key = uuid.uuid4().hex
        store.enqueue(key, snapshot.repository, snapshot.number)
        abandoned = store.claim(lease_seconds=0)
        assert abandoned["id"] == key
        store.engine.dispose()
        store = Store(url)
        replacement = store.claim()
        assert replacement["id"] == key and replacement["attempts"] == 2
        assert not store.finish(abandoned, decision_id="stale")
        assert store.finish(replacement, decision_id="recovered")
        recovered += 1
    assert inserted == 1 and winners == events == 100 and recovered == 20
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "database": store.engine.dialect.name,
        "database_version": list(store.engine.dialect.server_version_info or ()),
        "duplicate_delivery_attempts": 1000, "delivery_concurrency": 16, "jobs_created": inserted,
        "approval_races": 100, "reviewers_per_race": 32, "successful_resolutions": winners,
        "approval_audit_events": events, "conflicting_resolutions_prevented": 3200 - winners,
        "simulated_restarts": 20, "jobs_recovered": recovered,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "scope": "Synthetic contention and engine-restart/expired-lease experiments. Not OS kill, network partition or production load tests."
    }
    output = ROOT / "evaluation/reliability-results.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    store.engine.dispose()


if __name__ == "__main__":
    main()
