import hashlib
import hmac
import json
import time
import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from .config import Settings
from .github import GitHub
from .models import REPOSITORY_PATTERN, normalize_repository
from .policy import evaluate
from .storage import Store, fingerprint


class PullRequestRef(BaseModel):
    repository: str = Field(pattern=REPOSITORY_PATTERN, max_length=256)
    number: int = Field(gt=0, le=2_147_483_647, strict=True)

    @field_validator("repository")
    @classmethod
    def canonical_repository(cls, value):
        return normalize_repository(value)


class Resolution(BaseModel):
    action: Literal["approve", "reject"]
    expected_revision: int = Field(gt=0)
    reason: str = Field(min_length=10, max_length=2000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


def create_app(settings: Settings | None = None, store=None, github=None):
    settings = settings or Settings.load()
    store = store or Store(settings.database_url)
    github = github or GitHub(settings.github_token)

    @asynccontextmanager
    async def lifespan(app):
        async def demo_worker():
            from .service import process_one
            while True:
                await run_in_threadpool(process_one, store, github, settings.policy)
                await asyncio.sleep(.5)
        task = asyncio.create_task(demo_worker()) if settings.demo_mode else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            github.client.close() if hasattr(github, "client") else None
            store.engine.dispose()

    app = FastAPI(title="ApprovalFlow", version="0.2.0", lifespan=lifespan,
                  description="GitHub analysis and authenticated human sign-off. Optional explicit GitHub publication; never merges code.")

    def identity(authorization: str = Header(default="")):
        token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        for name, secret in settings.reviewers.items():
            if hmac.compare_digest(token.encode(), secret.encode()):
                return name
        if hmac.compare_digest(token.encode(), settings.operator_token.encode()):
            return "operator"
        raise HTTPException(401, "Valid bearer token required")

    def operator(actor=Depends(identity)):
        if actor != "operator":
            raise HTTPException(403, "Operator role required")

    def allowed(repository):
        if repository.lower() not in settings.repositories:
            raise HTTPException(403, "Repository is not allowed")

    def decision_or_404(decision_id):
        decision = store.decision(decision_id)
        if decision is None:
            raise HTTPException(404, "Decision not found")
        allowed(decision["repository"])
        return decision

    def refresh_for_approval(decision):
        if not store.is_current(decision["id"]):
            raise HTTPException(409, "A newer review supersedes this recommendation")
        if time.time() - decision["created_at"] > 3600:
            raise HTTPException(409, "Recommendation expired; request a fresh review")
        try:
            current = github.snapshot(decision["repository"], decision["number"])
        except Exception:
            raise HTTPException(503, "Could not refresh GitHub evidence; retry later")
        if fingerprint(current, settings.policy) != decision["fingerprint"]:
            raise HTTPException(409, "Evidence or policy changed; request a fresh review")
        if evaluate(current, settings.policy).outcome == "BLOCKED":
            raise HTTPException(409, "Required safety checks are blocked")
        return current

    @app.get("/health")
    def health():
        try:
            store.ping()
        except SQLAlchemyError:
            raise HTTPException(503, "Database unavailable")
        return {"status": "ok"}

    @app.get("/app-config")
    def app_config():
        config = {"demo": settings.demo_mode}
        if settings.demo_mode:
            # Demo credentials only authorize the isolated fixture database.
            config["demo_tokens"] = {"reviewer": settings.reviewers["demo-reviewer"], "operator": settings.operator_token}
        return config

    @app.get("/session")
    def session(actor=Depends(identity)):
        return {"actor": actor, "role": "operator" if actor == "operator" else "reviewer",
                "repositories": sorted(settings.repositories), "demo": settings.demo_mode,
                "publication_enabled": settings.github_write_enabled, "policy": settings.policy.model_dump()}

    @app.post("/webhooks/github", status_code=202)
    async def webhook(request: Request, x_hub_signature_256: str = Header(default=""),
                      x_github_delivery: str = Header(default=""), x_github_event: str = Header(default="")):
        # Bound memory even when Content-Length is absent or dishonest.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1_048_576:
                raise HTTPException(413, "Payload too large")
        expected = "sha256=" + hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected.encode(), x_hub_signature_256.encode()):
            raise HTTPException(401, "Invalid webhook signature")
        if not x_github_delivery or len(x_github_delivery) > 128:
            raise HTTPException(400, "Valid delivery ID required")
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, "Invalid JSON object")
        action = payload.get("action")
        if action is not None and not isinstance(action, str):
            raise HTTPException(400, "Invalid event action")
        pr_event = x_github_event == "pull_request" and action in {
            "opened", "reopened", "synchronize", "ready_for_review"}
        check_event = x_github_event in {"check_run", "check_suite"} and payload.get("action") == "completed"
        if not pr_event and not check_event:
            return {"status": "ignored"}
        try:
            repository = payload["repository"]["full_name"]
            numbers = [payload["number"]] if pr_event else [p["number"] for p in payload[x_github_event]["pull_requests"]]
            if len(numbers) > 50:
                raise ValueError()
            refs = [PullRequestRef(repository=repository, number=n) for n in numbers]
        except (KeyError, TypeError, ValueError, ValidationError):
            raise HTTPException(400, "Invalid pull request reference")
        queued = []
        for ref in refs:
            allowed(ref.repository)
            job_id = x_github_delivery if pr_event else hashlib.sha256(f"{x_github_delivery}:{ref.number}".encode()).hexdigest()
            inserted = await run_in_threadpool(store.enqueue, job_id, ref.repository.lower(), ref.number)
            queued.append({"status": "queued" if inserted else "duplicate", "job_id": job_id})
        if pr_event:
            return queued[0]
        return {"jobs": queued}

    @app.post("/reviews", status_code=202, dependencies=[Depends(operator)])
    def request_review(ref: PullRequestRef):
        import uuid
        allowed(ref.repository)
        job_id = uuid.uuid4().hex
        store.enqueue(job_id, ref.repository.lower(), ref.number)
        return {"job_id": job_id}

    @app.get("/jobs/{job_id}", dependencies=[Depends(identity)])
    def get_job(job_id: str):
        job = store.job(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        allowed(job["repository"])
        return {k: v for k, v in job.items() if k != "lease_token"}

    @app.get("/decisions", dependencies=[Depends(identity)])
    def list_decisions():
        return store.recent(settings.repositories)

    @app.get("/decisions/{decision_id}", dependencies=[Depends(identity)])
    def get_decision(decision_id: str):
        decision = decision_or_404(decision_id)
        return {**decision, "is_current": store.is_current(decision_id),
                "audit": store.events(decision_id), "publication": store.publication(decision_id)}

    @app.post("/decisions/{decision_id}/resolve")
    def resolve(decision_id: str, resolution: Resolution, actor=Depends(identity)):
        if actor == "operator":
            raise HTTPException(403, "Named reviewer required")
        decision = decision_or_404(decision_id)
        if actor.lower() == decision["author"].lower():
            raise HTTPException(403, "Authors cannot resolve their own changes")
        if resolution.action == "approve":
            refresh_for_approval(decision)
        if not store.resolve(decision_id, resolution.expected_revision, actor, resolution.action, resolution.reason):
            raise HTTPException(409, "Decision superseded, already resolved or revision changed")
        return {"resolution": resolution.action, "revision": resolution.expected_revision + 1,
                "github_action": "none", "reviewer": actor}

    @app.post("/decisions/{decision_id}/publish")
    def publish(decision_id: str, actor=Depends(identity)):
        if not settings.github_write_enabled:
            raise HTTPException(403, "GitHub publication is disabled on this server")
        decision = decision_or_404(decision_id)
        approvals = [e for e in store.events(decision_id) if e["action"] == "approve"]
        if actor == "operator" or not approvals or approvals[-1]["actor"] != actor or decision["resolution"] != "approve":
            raise HTTPException(403, "Only the approving named reviewer may publish an approved decision")
        existing = store.publication(decision_id)
        if existing:
            if existing["state"] == "published":
                return existing
            raise HTTPException(409, "Publication is in progress or uncertain; inspect GitHub before any further submission")
        current = refresh_for_approval(decision)
        if not store.reserve_publication(decision_id):
            raise HTTPException(409, "Decision superseded or another request already reserved this publication")
        try:
            result = github.publish_approval(current, decision_id, actor, approvals[-1]["reason"])
        except Exception as exc:
            # Never retry a potentially accepted external write automatically.
            store.finish_publication(decision_id, actor, error=type(exc).__name__)
            raise HTTPException(503, "GitHub publication outcome is uncertain; inspect GitHub manually")
        store.finish_publication(decision_id, actor, result=result)
        return store.publication(decision_id)

    frontend = Path(__file__).resolve().parent / "web"
    # Source checkouts use Vite's build folder; packaged installations include web/.
    if not (frontend / "index.html").exists():
        frontend = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if (frontend / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def console():
            return FileResponse(frontend / "index.html", headers={"Cache-Control": "no-cache"})

    return app
