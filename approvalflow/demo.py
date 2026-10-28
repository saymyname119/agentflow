"""Isolated fixture-backed product demo. Never connects to GitHub."""
import secrets
import hashlib
import time
from pathlib import Path

from sqlalchemy import update

from .api import create_app
from .config import Settings
from .models import ChangedFile, Policy, Snapshot
from .policy import evaluate
from .storage import Store, decisions

REVIEWER_TOKEN = "demo-reviewer-local-fixtures-only-0001"
OPERATOR_TOKEN = "demo-operator-local-fixtures-only-0002"


def fixtures():
    base = {
        "repository": "tanay-labs/commerce-api", "number": 142, "title": "Add rate limiting to the checkout API",
        "head_sha": "a" * 40, "base_sha": "b" * 40, "author": "maya-dev", "mergeable": True,
        "files": [
            {"filename": "src/payments/checkout.py", "additions": 38, "deletions": 9, "patch": "+rate_limiter.check(request)"},
            {"filename": "tests/test_checkout.py", "additions": 64, "deletions": 4, "patch": "+assert throttled.status_code == 429"},
            {"filename": "docs/checkout.md", "additions": 12, "deletions": 2, "patch": "+Rate limits apply to checkout requests."},
        ],
        "checks": [{"name": name, "app_id": 15368, "status": "completed", "conclusion": "success", "head_sha": "a" * 40} for name in ["test", "lint", "security-scan"]],
    }
    primary = Snapshot.model_validate(base)
    output = [primary]
    specifications = [
        (143, "Clarify local development setup", "eli-chen", "docs/development.md", "ready"),
        (144, "Update authentication token expiry", "sara-k", "src/auth/tokens.py", "review"),
        (145, "Add pagination to the product catalog", "arjun-dev", "src/catalog.py", "failed"),
        (146, "Add an index for order lookups", "maya-dev", "db/migrations/008_order_index.sql", "review"),
        (147, "Cover empty carts in checkout tests", "eli-chen", "tests/test_checkout.py", "ready"),
        (148, "Refresh dependency lockfile", "sara-k", "uv.lock", "review"),
        (149, "Remove unused feature flag", "arjun-dev", "docs/feature-flags.md", "ready"),
    ]
    for number, title, author, path, risk in specifications:
        snap = primary.model_copy(deep=True)
        snap.number, snap.title, snap.author = number, title, author
        snap.head_sha = hashlib.sha256(f"approvalflow-fixture-{number}".encode()).hexdigest()[:40]
        for check in snap.checks:
            check.head_sha = snap.head_sha
        snap.files = [ChangedFile(filename=path, additions=18, deletions=4, patch="+updated behavior")]
        if risk == "failed":
            snap.checks[0].conclusion = "failure"
        output.append(snap)
    return output


class DemoGitHub:
    def __init__(self, snapshots):
        self.snapshots = {(s.repository, s.number): s for s in snapshots}

    def snapshot(self, repository, number):
        try:
            return self.snapshots[(repository, number)].model_copy(deep=True)
        except KeyError:
            raise ValueError("This demo includes fixture pull requests 142 through 149 only")

    def publish_approval(self, *_):
        raise RuntimeError("Demo mode never publishes to GitHub")


def create_demo_app(database_url=None):
    if database_url is None:
        workspace = Path(".demo")
        workspace.mkdir(exist_ok=True)
        database_url = "sqlite:///" + (workspace / f"session-{secrets.token_hex(6)}.db").resolve().as_posix()
    policy = Policy(version="2026-10-28.1", required_checks=[{"name": "test", "app_id": 15368}, {"name": "lint", "app_id": 15368}])
    settings = Settings(database_url=database_url, webhook_secret="demo-webhook-fixture-only-00000000",
                        operator_token=OPERATOR_TOKEN, reviewers={"demo-reviewer": REVIEWER_TOKEN},
                        repositories={"tanay-labs/commerce-api"}, policy=policy, demo_mode=True)
    store, snapshots = Store(database_url), fixtures()
    now = time.time()
    for index, snapshot in enumerate(snapshots):
        key = store.record(snapshot, evaluate(snapshot, policy), policy)
        with store.engine.begin() as db:
            db.execute(update(decisions).where(decisions.c.id == key).values(created_at=now - 60 * (index * 5 + 3)))
        if snapshot.number in {147, 149}:
            store.resolve(key, 1, "demo-reviewer", "approve", "Reviewed the changes and supporting test results.")
    return create_app(settings, store, DemoGitHub(snapshots))
