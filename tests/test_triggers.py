import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from approvalflow.api import create_app


@pytest.mark.parametrize("event", ["check_run", "check_suite"])
def test_ci_completion_queues_each_associated_pr(settings, store, event):
    body = json.dumps({"action": "completed", "repository": {"full_name": "example/project"},
                       event: {"pull_requests": [{"number": 7}, {"number": 8}]}}).encode()
    headers = {"X-Hub-Signature-256": "sha256=" + hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest(),
               "X-GitHub-Delivery": uuid.uuid4().hex, "X-GitHub-Event": event}
    with TestClient(create_app(settings, store, object())) as client:
        first = client.post("/webhooks/github", content=body, headers=headers)
        assert first.status_code == 202
        queued = first.json()["jobs"]
        assert len(queued) == 2
        assert all(x["status"] == "queued" for x in queued)
        second = client.post("/webhooks/github", content=body, headers=headers).json()["jobs"]
        assert all(x["status"] == "duplicate" for x in second)
