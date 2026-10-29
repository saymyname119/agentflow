import json

import httpx
import pytest
from fastapi.testclient import TestClient

from approvalflow.api import create_app
from approvalflow.llm import AuditOutput, LLMAuditor, audit_input, audit_key
from approvalflow.policy import evaluate


def output(findings=None):
    return {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps({"findings": findings or []})}]}]}


def finding(**updates):
    return {"path": "README.md", "line": 1, "severity": "medium", "title": "Check this",
            "explanation": "Potential defect", "suggestion": "Inspect the behavior", **updates}


def test_provider_request_is_bounded_tool_free_and_not_stored(snapshot):
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert body["store"] is False
        assert body["max_output_tokens"] == 2500
        assert "tools" not in body
        assert body["text"]["format"]["strict"] is True
        return httpx.Response(200, json=output([finding()]))
    report = LLMAuditor("test-key", "configured-model", httpx.MockTransport(handler)).audit(snapshot)
    assert len(calls) == 1
    assert report.findings[0].line == 1


@pytest.mark.parametrize("value", [finding(path="other.py"), finding(line=99), finding(line=True),
    finding(severity="approve"), finding(command="merge"), finding(title="ghp_" + "x" * 32)])
def test_invalid_or_unsafe_model_findings_are_rejected(snapshot, value):
    gateway = LLMAuditor("test", "model", httpx.MockTransport(lambda _: httpx.Response(200, json=output([value]))))
    with pytest.raises(ValueError):
        gateway.audit(snapshot)


@pytest.mark.parametrize("data", [{"status": "incomplete"}, {"status": "completed", "output": []},
    {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]}])
def test_incomplete_refused_or_empty_responses_fail_closed(snapshot, data):
    with pytest.raises(ValueError):
        LLMAuditor("test", "model", httpx.MockTransport(lambda _: httpx.Response(200, json=data))).audit(snapshot)


def test_timeout_is_not_retried(snapshot):
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("private data")
    with pytest.raises(httpx.ReadTimeout):
        LLMAuditor("test", "model", httpx.MockTransport(handler)).audit(snapshot)
    assert len(calls) == 1


@pytest.mark.parametrize("mutation", ["missing", "large", "secret"])
def test_input_guardrails_prevent_model_call(snapshot, mutation):
    if mutation == "missing":
        snapshot.files[0].patch_complete = False
    elif mutation == "large":
        snapshot.files[0].patch = "+" + "x" * 60001
    else:
        snapshot.files[0].patch = "+ghp_" + "x" * 32
    with pytest.raises(ValueError):
        audit_input(snapshot)


def test_response_byte_limit(snapshot):
    with pytest.raises(ValueError, match="budget"):
        LLMAuditor("test", "model", httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 65000))).audit(snapshot)


def test_added_line_anchors_follow_hunks_and_context(snapshot):
    snapshot.files[0].patch = "@@ -10,2 +10,3 @@\n context\n-old\n+new\n+another\n@@ -40 +41 @@\n-x\n+y"
    snapshot.files[0].additions = 3
    snapshot.files[0].deletions = 2
    _, anchors = audit_input(snapshot)
    assert anchors == {("README.md", 11), ("README.md", 12), ("README.md", 41)}


def test_audit_gate_acknowledgement_and_duplicate_budget(settings, store, snapshot, policy):
    settings.llm_audit_enabled = True
    settings.llm_model = "test-model"
    calls = []
    class Gateway:
        def snapshot(self, *_):
            return snapshot
    class Auditor:
        def audit(self, current):
            calls.append(current)
            return AuditOutput(findings=[])
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    headers = {"Authorization": "Bearer " + "m" * 32}
    payload = {"action": "approve", "expected_revision": 1, "reason": "I inspected all supplied evidence"}
    with TestClient(create_app(settings, store, Gateway(), Auditor())) as client:
        assert client.post(f"/decisions/{key}/resolve", headers=headers, json=payload).status_code == 409
        response = client.post(f"/decisions/{key}/llm-audit", headers=headers)
        assert response.status_code == 200
        assert response.json()["state"] == "completed"
        assert client.post(f"/decisions/{key}/llm-audit", headers=headers).json()["id"] == response.json()["id"]
        assert len(calls) == 1
        payload["expected_audit_id"] = "different"
        assert client.post(f"/decisions/{key}/resolve", headers=headers, json=payload).status_code == 409
        payload["expected_audit_id"] = response.json()["id"]
        assert client.post(f"/decisions/{key}/resolve", headers=headers, json=payload).status_code == 200


@pytest.mark.parametrize("changed", [False, True])
def test_unavailable_or_stale_audit_never_allows_approval(settings, store, snapshot, policy, changed):
    settings.llm_audit_enabled = True
    class Gateway:
        def snapshot(self, *_):
            return snapshot
    class Auditor:
        def audit(self, current):
            if changed:
                snapshot.head_sha = "d" * 40
                return AuditOutput(findings=[])
            raise RuntimeError("secret-key-never-expose")
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    headers = {"Authorization": "Bearer " + "m" * 32}
    with TestClient(create_app(settings, store, Gateway(), Auditor())) as client:
        response = client.post(f"/decisions/{key}/llm-audit", headers=headers)
        assert response.status_code == 503
        assert "secret-key" not in response.text
        report = store.llm_audit(key, audit_key(settings.llm_model))
        assert report["state"] == "unavailable"
        assert report["report"] is None
        assert client.post(f"/decisions/{key}/resolve", headers=headers, json={"action": "approve",
            "expected_revision": 1, "expected_audit_id": report["id"], "reason": "Reviewed all available evidence"}).status_code == 409


def test_demo_cannot_call_model_even_if_settings_enable_it(settings, store, snapshot, policy):
    settings.demo_mode = True
    settings.llm_audit_enabled = True
    settings.reviewers["demo-reviewer"] = "d" * 32
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    with TestClient(create_app(settings, store, object())) as client:
        assert client.post(f"/decisions/{key}/llm-audit", headers={"Authorization": "Bearer " + "m" * 32}).status_code == 403


def test_enabling_audit_also_gates_previously_approved_publication(settings, store, snapshot, policy):
    settings.llm_audit_enabled = True
    settings.github_write_enabled = True
    class Gateway:
        def snapshot(self, *_):
            return snapshot
        def publish_approval(self, *_):
            pytest.fail("Missing required audit must not reach GitHub")
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    assert store.resolve(key, 1, "maintainer", "approve", "Legacy approval before enabling LLM")
    with TestClient(create_app(settings, store, Gateway())) as client:
        response = client.post(f"/decisions/{key}/publish", headers={"Authorization": "Bearer " + "m" * 32})
        assert response.status_code == 409
    assert store.publication(key) is None


def test_concurrent_audit_reservations_allow_only_one_paid_attempt(store, snapshot, policy):
    from concurrent.futures import ThreadPoolExecutor
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    with ThreadPoolExecutor(max_workers=8) as pool:
        winners = list(pool.map(lambda _: store.reserve_audit(key, audit_key("model"), "maintainer"), range(8)))
    assert sum(winners) == 1
    assert [e["action"] for e in store.events(key)].count("llm_started") == 1


def test_model_cannot_bypass_deterministic_blockers(settings, store, snapshot, policy):
    settings.llm_audit_enabled = True
    snapshot.checks = []
    class Gateway:
        def snapshot(self, *_):
            return snapshot
    class Auditor:
        def audit(self, *_):
            pytest.fail("Blocked evidence must never reach the model")
    key = store.record(snapshot, evaluate(snapshot, policy), policy)
    with TestClient(create_app(settings, store, Gateway(), Auditor())) as client:
        assert client.post(f"/decisions/{key}/llm-audit", headers={"Authorization": "Bearer " + "m" * 32}).status_code == 409
    assert store.decision(key)["resolution"] is None
