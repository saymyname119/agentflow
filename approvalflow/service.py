import logging
import time
from sqlalchemy.exc import SQLAlchemyError

from .policy import evaluate

log = logging.getLogger(__name__)


def process_one(store, github, policy):
    try:
        job = store.claim()
    except SQLAlchemyError:
        log.warning("claim_failed error=DatabaseUnavailable")
        return False
    if not job:
        return False
    started = time.perf_counter()
    try:
        snapshot = github.snapshot(job["repository"], job["number"])
        recommendation = evaluate(snapshot, policy)
        decision_id = store.complete(job, snapshot, recommendation, policy)
        if decision_id is None:
            log.warning("lease_lost job=%s", job["id"])
            return True
        log.info("evaluated job=%s decision=%s outcome=%s elapsed_ms=%.2f",
                 job["id"], decision_id, recommendation.outcome, (time.perf_counter() - started) * 1000)
    except Exception as exc:
        # Exception strings can contain URLs or source snippets. Store only the class.
        try:
            store.finish(job, error=type(exc).__name__)
        except SQLAlchemyError:
            log.warning("retry_write_failed job=%s error=DatabaseUnavailable", job["id"])
        log.warning("evaluation_failed job=%s error=%s", job["id"], type(exc).__name__)
    return True
