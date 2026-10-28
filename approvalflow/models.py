from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChangedFile(BaseModel):
    filename: str = Field(min_length=1, max_length=1024)
    previous_filename: str | None = None
    status: str = "modified"
    additions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    patch: str | None = None


class Check(BaseModel):
    name: str
    app_id: int
    status: str
    conclusion: str | None = None
    head_sha: str


class Snapshot(BaseModel):
    title: str = Field(default="", max_length=512)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    number: int = Field(gt=0)
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    base_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    author: str = Field(min_length=1)
    draft: bool = False
    state: Literal["open", "closed"] = "open"
    mergeable: bool | None = None
    files_complete: bool = True
    files: list[ChangedFile] = Field(max_length=3000)
    checks: list[Check] = Field(default_factory=list)


class RequiredCheck(BaseModel):
    name: str = Field(min_length=1)
    app_id: int = Field(gt=0)


class Policy(BaseModel):
    version: str = Field(min_length=1)
    required_checks: list[RequiredCheck] = Field(min_length=1)
    max_lines: int = Field(default=300, gt=0)
    max_files: int = Field(default=15, gt=0)
    sensitive_patterns: list[str] = Field(default_factory=lambda: [
        "**/auth/**", "**/security/**", "**/payments/**", "**/migrations/**",
        ".github/**", "Dockerfile*", "**/Dockerfile*", "**/*.tf", "**/.env*",
        "**/*lock*", "**/requirements*.txt", "**/pyproject.toml", "**/package.json",
    ])

    @model_validator(mode="after")
    def unique_checks(self):
        if len({(c.name, c.app_id) for c in self.required_checks}) != len(self.required_checks):
            raise ValueError("Required checks must be unique")
        return self


class Finding(BaseModel):
    code: str
    message: str
    severity: Literal["block", "review", "info"]
    paths: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    outcome: Literal["READY", "REVIEW", "BLOCKED"]
    policy_version: str
    findings: list[Finding]
    changed_lines: int
    changed_files: int
