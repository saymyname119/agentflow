import json
import importlib.util
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

_launcher_spec = importlib.util.spec_from_file_location("approvalflow_launcher", Path(__file__).resolve().parents[1] / "start.py")
start = importlib.util.module_from_spec(_launcher_spec)
_launcher_spec.loader.exec_module(start)
from approvalflow.api import create_app
from approvalflow.sandbox import (SandboxConfig, configure, forwarder_command,
                                  forwarder_environment, repository_name, save_config, selected_checks)


class Repository:
    def get(self, path):
        return {"head": {"sha": "a" * 40}, "user": {"login": "author"}}

    def pages(self, *args, **kwargs):
        return [{"name": "test", "app": {"id": 123, "name": "Trusted CI"}}]


def configuration(policy):
    return SandboxConfig(repository="example/project", sample_pr=7, reviewer="maintainer",
        webhook_secret="w" * 64, operator_token="o" * 64, reviewer_token="r" * 64, policy=policy)


def test_wizard_generates_distinct_secrets_and_trusted_policy():
    answers = iter(["https://github.com/Example/project.git", "7", "1", "maintainer", "https://smee.io/abc123"])
    config = configure(Repository(), lambda _: next(answers))
    assert config.repository == "example/project"
    assert config.sample_pr == 7
    assert len({config.webhook_secret, config.operator_token, config.reviewer_token}) == 3
    assert config.policy.required_checks[0].app_id == 123
    assert "github_token" not in config.model_dump()


def test_manual_mode_requires_no_proxy_or_environment_variables():
    answers = iter(["example/project", "7", "1", "author", ""])
    config = configure(Repository(), lambda _: next(answers))
    assert config.proxy_url == ""
    assert config.reviewer == "author"  # UI and API retain the actual self-approval guard.


def test_setup_without_checks_fails_instead_of_relaxing_ci():
    class NoChecks(Repository):
        def pages(self, *args, **kwargs):
            return []
    answers = iter(["example/project", "7"])
    with pytest.raises(ValueError, match="No CI checks"):
        configure(NoChecks(), lambda _: next(answers))


@pytest.mark.parametrize("value", ["https://evil.test/owner/repo", "example/..", "example/project;command", "../repo"])
def test_repository_input_cannot_be_a_command_or_foreign_url(value):
    with pytest.raises(ValueError):
        repository_name(value)


@pytest.mark.parametrize("value", ["0", "2", "-1", "x", ""])
def test_check_selection_cannot_select_an_unobserved_producer(value):
    with pytest.raises(ValueError):
        selected_checks([{"name": "test", "app": {"id": 123}}], value)


def test_config_roundtrip_is_local_and_contains_no_github_token(tmp_path, policy):
    path = tmp_path / ".local/sandbox.json"
    config = configuration(policy)
    save_config(path, config)
    assert SandboxConfig.model_validate_json(path.read_text()) == config
    assert "github_token" not in json.loads(path.read_text())
    assert not path.with_suffix(".tmp").exists()


def test_forwarder_has_pinned_package_and_no_shell_control(monkeypatch):
    monkeypatch.setattr("approvalflow.sandbox.shutil.which", lambda _: "/bin/npx")
    command = forwarder_command("https://smee.io/abc123", 8001)
    assert "smee-client@5.0.0" in command
    assert command[-2:] == ["--port", "8001"]
    with pytest.raises(ValueError):
        forwarder_command("https://smee.io/a;othercommand", 8001)


def test_relay_does_not_inherit_application_credentials(monkeypatch):
    for name in ("GITHUB_TOKEN", "OPENAI_API_KEY", "WEBHOOK_SECRET", "DATABASE_URL"):
        monkeypatch.setenv(name, "private-value")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = forwarder_environment()
    assert env["PATH"] == "/usr/bin"
    assert not any(name in env for name in ("GITHUB_TOKEN", "OPENAI_API_KEY", "WEBHOOK_SECRET", "DATABASE_URL"))


def test_live_sandbox_integrated_worker_processes_requests(settings, store, snapshot):
    class Gateway:
        def snapshot(self, *_):
            return snapshot
    with TestClient(create_app(settings, store, Gateway(), run_worker=True)) as client:
        config = client.get("/app-config").json()
        assert config == {"demo": False}
        response = client.post("/reviews", headers={"Authorization": "Bearer " + "o" * 32},
            json={"repository": snapshot.repository, "number": snapshot.number})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = store.job(response.json()["job_id"])
            if job["status"] == "done":
                break
            time.sleep(.05)
        assert job["status"] == "done"
        assert store.decision(job["decision_id"])["recommendation"]["outcome"] == "READY"


def test_bootstrap_build_is_cached_and_invalidated_by_source_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(start, "ROOT", tmp_path)
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "dist").mkdir()
    (frontend / "dist/index.html").write_text("built")
    (frontend / "package-lock.json").write_text("{}")
    (frontend / "src/main.ts").write_text("first")
    local = tmp_path / ".local"
    local.mkdir()
    (local / "frontend.sha256").write_text(start.frontend_digest())
    calls = []
    monkeypatch.setattr(start, "run", lambda command, cwd=None: calls.append(command))
    monkeypatch.setattr(start.shutil, "which", lambda _: "/bin/npm")
    start.prepare_frontend()
    assert calls == []
    (frontend / "src/main.ts").write_text("changed")
    start.prepare_frontend()
    assert calls == [["/bin/npm", "ci", "--no-audit", "--no-fund"], ["/bin/npm", "run", "build"]]
    start.prepare_frontend()
    assert len(calls) == 2


def test_bootstrap_reuses_a_working_environment_without_installing(tmp_path, monkeypatch):
    monkeypatch.setattr(start, "ROOT", tmp_path)
    monkeypatch.setattr(start, "usable", lambda _: True)
    monkeypatch.setattr(start, "run", lambda *_: pytest.fail("Should reuse installed dependencies"))
    assert start.prepare_python().is_relative_to(tmp_path / ".venv")
