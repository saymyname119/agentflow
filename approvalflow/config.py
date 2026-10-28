import json
import os
from dataclasses import dataclass
from pathlib import Path

from .models import Policy


@dataclass
class Settings:
    database_url: str
    webhook_secret: str
    operator_token: str
    reviewers: dict[str, str]  # GitHub login -> secret bearer token
    repositories: set[str]
    policy: Policy
    github_token: str = ""
    github_write_enabled: bool = False
    demo_mode: bool = False

    @classmethod
    def load(cls):
        settings = cls(
            database_url=os.getenv("DATABASE_URL", "sqlite:///approvalflow.db"),
            webhook_secret=os.environ["WEBHOOK_SECRET"],
            operator_token=os.environ["OPERATOR_TOKEN"],
            reviewers=json.loads(os.environ["REVIEWER_TOKENS"]),
            repositories={r.strip().lower() for r in os.environ["ALLOWED_REPOSITORIES"].split(",") if r.strip()},
            policy=Policy.model_validate_json(Path(os.getenv("POLICY_FILE", "policy.json")).read_text()),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            github_write_enabled=os.getenv("GITHUB_WRITE_ENABLED", "false").lower() == "true",
        )
        secrets = [settings.webhook_secret, settings.operator_token, *settings.reviewers.values()]
        if not settings.repositories or not settings.reviewers or any(len(s) < 32 for s in secrets):
            raise ValueError("Configure allowed repositories, reviewers and separate secrets of at least 32 characters")
        if len(secrets) != len(set(secrets)):
            raise ValueError("Webhook, operator and reviewer secrets must be different")
        if any(not name.strip() or name.lower() == "operator" for name in settings.reviewers):
            raise ValueError("Reviewer names must be nonempty GitHub logins; operator is reserved")
        return settings
