"""Trusted approval boundary; repository text and advisory output have no authority here."""
import time

from .policy import evaluate
from .storage import fingerprint


class GuardrailViolation(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def require_matching_evidence(snapshot, repository, number):
    if snapshot.repository.lower() != repository.lower() or snapshot.number != number:
        raise GuardrailViolation(409, "Fetched evidence does not match the requested pull request")


def require_reviewer(actor, author):
    if actor == "operator":
        raise GuardrailViolation(403, "Named reviewer required")
    if actor.lower() == author.lower():
        raise GuardrailViolation(403, "Authors cannot resolve their own changes")


def refresh_for_approval(decision, store, github, policy):
    # Storage repeats the current-review check under a lock at the final mutation.
    if not store.is_current(decision["id"]):
        raise GuardrailViolation(409, "A newer review supersedes this recommendation")
    age = time.time() - decision["created_at"]
    if age < 0 or age > 3600:
        raise GuardrailViolation(409, "Recommendation expired; request a fresh review")
    try:
        current = github.snapshot(decision["repository"], decision["number"])
    except Exception:
        raise GuardrailViolation(503, "Could not refresh GitHub evidence; retry later") from None
    require_matching_evidence(current, decision["repository"], decision["number"])
    if fingerprint(current, policy) != decision["fingerprint"]:
        raise GuardrailViolation(409, "Evidence or policy changed; request a fresh review")
    if evaluate(current, policy).outcome == "BLOCKED":
        raise GuardrailViolation(409, "Required safety checks are blocked")
    return current
