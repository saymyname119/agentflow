import httpx
import pytest

from approvalflow.github import GitHub


def pr(snapshot):
    return {"head": {"sha": snapshot.head_sha}, "base": {"sha": snapshot.base_sha},
            "user": {"login": snapshot.author}, "state": "open", "draft": False,
            "mergeable": True, "changed_files": 1, "updated_at": "2026-10-28T10:00:00Z"}


def adapter(handler):
    return GitHub(client=httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler)))


def test_fetch_normalizes_github_evidence(snapshot):
    def handler(request):
        if request.url.path.endswith("/files"):
            data = [snapshot.files[0].model_dump()]
        elif request.url.path.endswith("/check-runs"):
            c = snapshot.checks[0].model_dump()
            c["app"] = {"id": c.pop("app_id")}
            data = {"check_runs": [c]}
        else:
            data = pr(snapshot)
        return httpx.Response(200, json=data)
    assert adapter(handler).snapshot(snapshot.repository, snapshot.number) == snapshot


def test_paginated_files_do_not_stop_at_first_page():
    seen = []
    def handler(request):
        page = int(request.url.params["page"])
        seen.append(page)
        return httpx.Response(200, json=[{"filename": str(i)} for i in range(100 if page == 1 else 1)])
    assert len(adapter(handler).pages("/files")) == 101
    assert seen == [1, 2]


def test_head_changed_during_collection_is_retried(snapshot):
    reads = []
    def handler(request):
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=[snapshot.files[0].model_dump()])
        if request.url.path.endswith("/check-runs"):
            return httpx.Response(200, json={"check_runs": []})
        data = pr(snapshot)
        reads.append(1)
        if len(reads) == 2:
            data["head"]["sha"] = "c" * 40
        return httpx.Response(200, json=data)
    with pytest.raises(ValueError, match="changed while collecting"):
        adapter(handler).snapshot(snapshot.repository, snapshot.number)


@pytest.mark.parametrize("code", [403, 429, 500])
def test_api_errors_never_become_ready(code):
    with pytest.raises(httpx.HTTPStatusError):
        adapter(lambda _: httpx.Response(code, json={"message": "unavailable"})).snapshot("example/project", 7)
