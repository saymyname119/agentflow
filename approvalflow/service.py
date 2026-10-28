import logging
import time

from .policy import evaluate

log = logging.getLogger(__name__)


def process_one(store, github, policy):
    job = store.claim()
    if not job:
        return False
    started = time.perf_counter()
    try:
        snapshot = github.snapshot(job["repository"], job["number"])
        recommendation = evaluate(snapshot, policy)
        decision_id = store.record(snapshot, recommendation, policy, request_id=job["id"])
        if not store.finish(job, decision_id=decision_id):
            log.warning("lease_lost job=%s", job["id"])
        log.info("evaluated job=%s decision=%s outcome=%s elapsed_ms=%.2f",
                 job["id"], decision_id, recommendation.outcome, (time.perf_counter() - started) * 1000)
    except Exception as exc:
        # Exception strings can contain URLs or source snippets. Store only the class.
        store.finish(job, error=type(exc).__name__)
        log.warning("evaluation_failed job=%s error=%s", job["id"], type(exc).__name__)
    return True
