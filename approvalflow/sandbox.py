"""Interactive local setup. Never creates GitHub resources or stores the GitHub token."""
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import socket
import subprocess

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from .config import Settings
from .github import GitHub
from .models import Policy, REPOSITORY_PATTERN, normalize_repository


class SandboxConfig(BaseModel):
    repository: str = Field(pattern=REPOSITORY_PATTERN, max_length=256)
    sample_pr: int = Field(gt=0, le=2_147_483_647, strict=True)
    reviewer: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
    webhook_secret: str = Field(min_length=32)
    operator_token: str = Field(min_length=32)
    reviewer_token: str = Field(min_length=32)
    policy: Policy
    proxy_url: str = Field(default="", pattern=r"^(?:https://smee\.io/[A-Za-z0-9]+)?$")

    @field_validator("repository")
    @classmethod
    def canonical_repository(cls, value):
        return normalize_repository(value)

    @field_validator("reviewer")
    @classmethod
    def reserved_name(cls, value):
        if value.lower() == "operator":
            raise ValueError("operator is reserved; enter a named reviewer")
        return value


def repository_name(value):
    value = value.strip().removeprefix("https://github.com/").removesuffix("/").removesuffix(".git")
    if not re.fullmatch(REPOSITORY_PATTERN, value) or len(value) > 256:
        raise ValueError("Use owner/repository or its https://github.com URL")
    return normalize_repository(value)


def selected_checks(checks, selection):
    indexes = {int(value.strip()) - 1 for value in selection.split(",")}
    if not indexes or min(indexes) < 0 or max(indexes) >= len(checks):
        raise ValueError("Choose listed check numbers, separated by commas")
    return [{"name": checks[i]["name"], "app_id": checks[i]["app"]["id"]} for i in sorted(indexes)]


def configure(github, read=input):
    repository = repository_name(read("Sandbox repository (owner/name or GitHub URL): "))
    github.get(f"/repos/{repository}")
    number = int(read("Number of an existing sandbox PR with CI checks: "))
    if not 1 <= number <= 2_147_483_647:
        raise ValueError("Enter a positive pull request number")
    pr = github.get(f"/repos/{repository}/pulls/{number}")
    checks = github.pages(f"/repos/{repository}/commits/{pr['head']['sha']}/check-runs", "check_runs", filter="latest")
    if not checks:
        raise ValueError("No CI checks found. Run your sandbox CI once, then rerun setup.")
    print("\nObserved checks. Choose only checks from producers you trust:")
    for index, check in enumerate(checks, 1):
        print(f"  {index}. {check['name']} — {check['app'].get('name', 'GitHub app')} (app {check['app']['id']})")
    required = selected_checks(checks, read("Required check numbers (e.g. 1 or 1,2): "))
    reviewer = read(f"Reviewer GitHub login (PR author is {pr['user']['login']}): ").strip()
    if reviewer.lower() == pr["user"]["login"].lower():
        print("You can inspect this PR, but self-approval stays disabled. Use a collaborator-authored PR for sign-off.")
    print("\nFor automatic webhooks: open https://smee.io and create a channel.")
    proxy_url = read("Paste the Smee URL (Enter to use manual review requests for now): ").strip().rstrip("/")
    return SandboxConfig(repository=repository, sample_pr=number, reviewer=reviewer,
        webhook_secret=secrets.token_hex(32), operator_token=secrets.token_hex(32),
        reviewer_token=secrets.token_hex(32), proxy_url=proxy_url,
        policy=Policy(version="sandbox-v1", required_checks=required))


def save_config(path, config):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Use restrictive permissions on POSIX. Windows retains the user's directory ACL.
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(config.model_dump_json(indent=2) + "\n")
    os.replace(temporary, path)


def forwarder_command(url, port):
    if not re.fullmatch(r"https://smee\.io/[A-Za-z0-9]+", url):
        raise ValueError("Use a channel URL from https://smee.io")
    npx = shutil.which("npx.cmd" if os.name == "nt" else "npx")
    if not npx:
        raise ValueError("Node.js/npm is required for webhook forwarding")
    return [npx, "--yes", "--package", "smee-client@5.0.0", "smee", "--url", url,
            "--path", "/webhooks/github", "--port", str(port)]


def forwarder_environment():
    # The webhook relay does not need application or provider credentials.
    return {key: value for key, value in os.environ.items()
            if not re.search(r"TOKEN|SECRET|PASSWORD|API_KEY|DATABASE_URL", key, re.IGNORECASE)}


def launch(port=8000, reset=False):
    import uvicorn
    from .api import create_app
    from .storage import Store
    import uuid
    root = Path.cwd()
    path = root / ".local/sandbox.json"
    forwarder = None
    github = None
    store = None
    try:
        # Fail before asking for credentials if another app already owns this port.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
        print("\nApprovalFlow sandbox — local sign-off only; GitHub publication and LLM calls are disabled.")
        token = os.getenv("GITHUB_TOKEN") or getpass.getpass("GitHub read token (hidden; not saved): ")
        if not token.strip():
            raise ValueError("A GitHub read token is required")
        github = GitHub(token)
        if path.exists() and not reset:
            config = SandboxConfig.model_validate_json(path.read_text(encoding="utf-8"))
            github.get(f"/repos/{config.repository}")
            print(f"Reusing saved setup for {config.repository}. Use --reset to change it.")
        else:
            config = configure(github)
            save_config(path, config)
        settings = Settings(database_url="sqlite:///" + (root / ".local/sandbox.db").as_posix(),
            webhook_secret=config.webhook_secret, operator_token=config.operator_token,
            reviewers={config.reviewer: config.reviewer_token}, repositories={config.repository},
            policy=config.policy, github_token=token)
        print(f"\nWorkspace: http://127.0.0.1:{port}/#/workspace")
        print(f"Dashboard tokens and webhook secret: {path}")
        print(f"Connect with reviewer_token as {config.reviewer}; use operator_token to queue a manual review.")
        if config.proxy_url:
            print(f"\nOne-time GitHub step: {config.repository} → Settings → Webhooks → Add webhook")
            print(f"Payload URL: {config.proxy_url}")
            print("Content type: application/json; Secret: webhook_secret from the local setup file")
            print("Select Pull requests, Check runs and Check suites; keep Active enabled.")
            forwarder = subprocess.Popen(forwarder_command(config.proxy_url, port), cwd=root,
                env=forwarder_environment(),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt")
        else:
            print("Webhook forwarding skipped. Connect as operator and choose New review to test a real PR.")
        print("\nAPI and worker start together. Press Ctrl+C here to stop everything.\n", flush=True)
        store = Store(settings.database_url)
        store.enqueue(uuid.uuid4().hex, config.repository, config.sample_pr)
        print(f"Queued PR #{config.sample_pr} so you can inspect real evidence immediately.")
        uvicorn.run(create_app(settings, store=store, github=github, run_worker=True), host="127.0.0.1", port=port)
    except httpx.HTTPStatusError as exc:
        print(f"GitHub returned HTTP {exc.response.status_code}. Check repository/PR access and token permissions.")
        raise SystemExit(1) from None
    except httpx.HTTPError:
        print("Could not reach GitHub. Check your connection and try again.")
        raise SystemExit(1) from None
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, error["loc"])) for error in exc.errors())
        print(f"Invalid setup fields: {fields}. Rerun with --reset to reconfigure; no secret values are printed.")
        raise SystemExit(1) from None
    except (ValueError, OSError) as exc:
        print(f"Setup could not finish: {exc}. Rerun the same command after correcting it.")
        raise SystemExit(1) from None
    finally:
        if forwarder is not None:
            if os.name == "nt" and forwarder.poll() is None:
                subprocess.run(["taskkill", "/PID", str(forwarder.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif os.name != "nt":
                try:
                    os.killpg(forwarder.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                forwarder.wait(timeout=5)
            except subprocess.TimeoutExpired:
                forwarder.kill()
                forwarder.wait()
        if github:
            github.client.close()
        if store:
            store.engine.dispose()
