import os

import pytest

from approvalflow.config import Settings
from approvalflow.models import Policy, Snapshot
from approvalflow.storage import Store


@pytest.fixture
def policy():
    return Policy(version="test-v1", required_checks=[{"name": "test", "app_id": 15368}])


@pytest.fixture
def snapshot():
    return Snapshot.model_validate({
        "repository": "example/project", "number": 7, "head_sha": "a" * 40, "base_sha": "b" * 40,
        "author": "contributor", "mergeable": True,
        "files": [{"filename": "README.md", "additions": 4, "deletions": 1, "patch": "@@ -1 +1 @@\n-old\n+new"}],
        "checks": [{"name": "test", "app_id": 15368, "status": "completed", "conclusion": "success", "head_sha": "a" * 40}],
    })


@pytest.fixture
def store(tmp_path):
    instance = Store(os.getenv("TEST_DATABASE_URL", "sqlite:///" + (tmp_path / "test.db").as_posix()))
    if os.getenv("TEST_DATABASE_URL"):
        from approvalflow.storage import audit, decisions, jobs, publications
        with instance.engine.begin() as db:
            for table in (publications, audit, decisions, jobs):
                db.execute(table.delete())
    yield instance
    instance.engine.dispose()


@pytest.fixture
def settings(policy):
    return Settings(database_url="unused", webhook_secret="w" * 32, operator_token="o" * 32,
                    reviewers={"maintainer": "m" * 32, "contributor": "c" * 32},
                    repositories={"example/project"}, policy=policy)
