# ApprovalFlow

An explainable GitHub pull-request approval agent built with **React, TypeScript, Python, FastAPI and PostgreSQL**. It gathers review evidence, clears routine changes for sign-off, and sends uncertain or sensitive changes to a person.

[![Tests](https://github.com/saymyname119/agentflow/actions/workflows/test.yml/badge.svg)](https://github.com/saymyname119/agentflow/actions/workflows/test.yml)

See the [phased release record](docs/RELEASE.md) for verified results and remaining deployment boundaries.

The React console includes a searchable review inbox, commit-bound CI evidence, risk explanations, file metadata, reason-required decisions, activity history, a trusted-policy view, and a page explaining the measured results. A fixture-backed demo runs the real policy, database and decision code without GitHub credentials.

![ApprovalFlow product overview](docs/product-overview.png)

The product overview introduces the workflow and its measured results. **Open review workspace** enters the functioning console; it is also available directly at `/#/workspace`.

![ApprovalFlow review workspace](docs/review-workspace.png)

**Small architecture:** one service, one worker from the same package, one database. No Redis, vector database, microservices or agent framework.

See [the approval guardrail system](docs/GUARDRAILS.md) for the enforced input, evidence, policy, identity, freshness, concurrency and publication boundaries, plus requirements for a future advisory LLM audit.

## Open the working demo

The creation environment is ready to run. From this directory:

```powershell
..\.venv\Scripts\python.exe -m approvalflow.cli demo
```

Open **http://127.0.0.1:8000** and choose **Open review workspace**. The demo signs in automatically as a sample reviewer. Approve or reject a review with a reason, then inspect its Activity tab. Use the account menu to switch to sample operator access and queue PR #142–#149. Switch back to reviewer access to decide on the fresh recommendation.

This is a local demo, not a deployed GitHub integration. Every restart creates a separate SQLite fixture database under ignored `.demo/`. Demo credentials authorize only that demo service; publication is disabled even if the live-mode environment enables it. No real GitHub requests are made. To start over, stop the server and run the command again.

For a fresh checkout, follow setup below. See [the three-minute walkthrough](docs/DEMO.md) for an interview demonstration and the design decisions worth discussing.

## What works

- Reads live pull-request metadata, all changed-file pages, and latest check runs from GitHub.
- Verifies required CI by **check name, GitHub app ID and exact head commit**.
- Combines size limits, sensitive paths, rename history, test additions/removals, missing patches, credential markers and risky operations into an explanation.
- Accepts signed GitHub pull-request and CI-completion webhooks; repeated delivery IDs create one job.
- Stores work before acknowledging it. Workers use expiring leases, bounded retries and a visible dead-letter state.
- Separates operator and named reviewer credentials; authors cannot sign off their own changes.
- Refreshes GitHub evidence before approval. A changed commit, base, CI result or policy invalidates the earlier recommendation.
- Uses database compare-and-swap updates so simultaneous reviewers cannot create conflicting resolutions. Records the winning decision and audit event in one transaction.
- Serializes current-review changes per pull request; historical recommendations cannot start new approvals or publication attempts.
- Stores file metadata and findings, without saving raw source patches or credential values.
- Optionally publishes a human-approved review to GitHub, bound to the inspected commit, with a persistent reservation that prevents duplicate submissions.

`READY` means **eligible for human sign-off**, `REVIEW` means a person must inspect the stated risks, and `BLOCKED` means required evidence or safety conditions failed. Human approval is recorded locally. A separate explicit action can publish an `APPROVE` review to GitHub when enabled. The service never merges code.

This is a **deterministic workflow agent**, not an LLM reviewer. It does not understand arbitrary program behavior or prove test coverage. Adding an LLM is a future experiment with a measurable baseline, not a dependency needed to run the project.

## Try it without credentials

From this directory, using Python 3.11+ and Node 22.12+:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
cd frontend
npm ci
npm test
npm run build
cd ..
.\.venv\Scripts\python.exe -m approvalflow.cli evaluate examples/docs-pr.json
.\.venv\Scripts\python.exe evaluation/run.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m approvalflow.cli demo
```

On macOS/Linux, use `.venv/bin/python` instead. For the environment where this project was created, a tested virtual environment also exists at `../.venv`.

`requirements-tested.txt` records the exact dependency versions used for verification. To reproduce those versions, install that file before installing this package with `pip install --no-deps -e .`.

The sample prints a `READY` recommendation with the policy version and reason. The evaluation writes `evaluation/results.json` with every input scenario, expected result, prediction, baseline prediction and timing scope.

The production frontend build is served by FastAPI, so you do not need a second server. Full integration tests expect that build to exist. For frontend development, run `npm run dev` from `frontend/` alongside the API/demo on port 8000; Vite proxies the application endpoints to the local service.

## Run with GitHub

1. Configure `policy.json` **on the server**, not from a pull request. Replace the example required check `test` and app ID `15368` with the exact checks and producer IDs observed in your repository. Matrix jobs may have names such as `test (sqlite)` and `test (postgres)`; list each required job separately.
2. Generate separate secrets using `python -c "import secrets; print(secrets.token_hex(32))"`. Configure the variables from `.env.example`. Native commands read exported environment variables; they do not load `.env` automatically.
3. Give `GITHUB_TOKEN` read access to the intended repository's pull requests, contents and checks. Supply an installation access token or fine-grained token yourself; automatic GitHub App token minting/renewal is not implemented.
4. Start the API with `approvalflow serve` and the worker with `approvalflow worker` in another terminal. Both must use the same database and policy.
5. Open `http://localhost:8000` for the review console and connect using a configured reviewer/operator token. Tokens stay in tab memory; a reload requires reconnecting in live mode. The interactive API reference remains at `/docs`. Protected endpoints take `Authorization: Bearer <token>` in the request header.
6. For webhooks, expose the API through your own HTTPS ingress. Set `/webhooks/github` as the destination, configure `WEBHOOK_SECRET`, and subscribe to pull requests plus completed check runs/check suites. GitHub checks for forked changes may omit associated PRs; submit a manual review request in that case.
7. Optional publication: set `GITHUB_WRITE_ENABLED=true` and grant the token pull-request write permission. After local sign-off, the same named reviewer can call the publish endpoint. GitHub attributes the posted review to the configured token's account/App; its body identifies the local reviewer. No GitHub write was performed during development.

For Docker, copy `.env.example` to `.env`, fill in the values and run:

```text
docker compose up --build
```

Compose binds the API to localhost and keeps PostgreSQL private. Use a hex database password to avoid URL-escaping ambiguity. Docker startup is supplied but was not executed in the creation environment; the PostgreSQL tests were run against a native isolated PostgreSQL 18 instance.

## API workflow

| Action | Endpoint | Credential |
| --- | --- | --- |
| Queue live PR analysis | `POST /reviews` with `repository` and `number` | Operator |
| Inspect queued/retrying/dead work | `GET /jobs/{job_id}` | Operator or reviewer |
| List recent recommendations | `GET /decisions` | Operator or reviewer |
| Inspect evidence and audit history | `GET /decisions/{id}` | Operator or reviewer |
| Sign off or reject | `POST /decisions/{id}/resolve` | Named reviewer |
| Publish the signed-off review to GitHub | `POST /decisions/{id}/publish` | Same approving reviewer; publication enabled |

Resolution body:

```json
{"action":"approve","expected_revision":1,"reason":"Inspected the change and supporting test results"}
```

Approval refreshes the evidence and expires after one hour. Rejecting a recommendation does not require a successful GitHub refresh. A `REVIEW` finding can receive reasoned human sign-off; a `BLOCKED` finding cannot. Sign-off is a local attestation to the inspected snapshot. Branch protection remains necessary for any later merge.

Publication refreshes evidence again and submits a review with `commit_id` set explicitly. A database reservation allows only one submission attempt per decision. A timeout, rejected write, crash during submission or failed confirmation leaves the attempt `uncertain` or `sending`; the service refuses automatic resubmission. Inspect GitHub manually using the `approvalflow:<decision_id>` marker in the review body. This intentionally favors avoiding duplicate external writes over automatic recovery. There is no administrative reset endpoint in this version.

## Architecture and deliberate tradeoffs

```mermaid
flowchart LR
    G[Signed GitHub event] --> A[FastAPI]
    A --> D[(PostgreSQL jobs)]
    D --> W[Lease-based worker]
    W --> E[Read fresh GitHub evidence]
    E --> P[Pure policy evaluator]
    P --> R[(Recommendation and audit)]
    H[Named human reviewer] --> F[Refresh evidence and resolve]
    R --> F
    F --> R
```

Database jobs remove the need for a separate broker at this scale. Claiming a job and resolving a decision use conditional updates checked by the database. Delivery IDs deduplicate ingress; request IDs deduplicate repeated processing after a crash. An old worker cannot complete a job after another worker acquires its lease. Worker leases last 120 seconds; slow evidence collection can lose its lease and be retried rather than overwrite a newer result.

Recommendation creation, audit insertion and job completion now share one fenced transaction. A small `review_heads` table serializes recommendation creation, reviewer decisions and publication reservations for each PR. Older records remain available for audit, and the API marks them `is_current: false`. Their decision controls are disabled.

Transient GitHub failures retry at increasing delays, up to five attempts. Exhausted work is visible as `dead`; an operator can submit a fresh request after resolving the cause. Completed CI events trigger fresh analysis instead of leaving the original pending-CI recommendation as the final result. The earlier record stays available for audit.

Trusted policy is loaded once per process; restart the API and worker after a change. Policy content, not just the version label, contributes to the evidence fingerprint. Raw patch text contributes to that hash but is not persisted.

Fingerprints normalize list order and also bind the evaluator engine version. Increment `POLICY_ENGINE_VERSION` when evaluator logic changes. GitHub patches are checked against reported addition/deletion counts; incomplete patches receive a review finding while visible content still undergoes credential/risk scanning. `/health` verifies database readiness and reports 503 when that check fails; it is not a live worker or GitHub availability probe.

## Verified evidence

See `evaluation/results.json`, `evaluation/reliability-results.json` and `evaluation/verification.json` for measured results. `RESUME_POINTS.md` translates these experiments into recruiter-readable bullets. Numbers describe local synthetic experiments, not deployed users or measured team savings.

To reproduce the PostgreSQL suite, point `TEST_DATABASE_URL` to a **disposable database**: its application tables are cleared before each database test. Then run `pytest -q`. CI includes separate SQLite and PostgreSQL jobs; CI itself has not run remotely until this repository is pushed.

The [backend audit](docs/BACKEND_AUDIT.md) records reproduced issues, corrections, verification and the goals that still require live validation.

The frontend has behavior tests for search, filtering, blocked approvals, reason validation, stale-evidence conflicts, queue completion, authentication and navigation. The responsive console was also checked in the browser at desktop and phone widths. The CI workflow builds and tests the frontend, then runs backend verification on both databases using the same built console.

The reliability experiment requires its own empty database:

```powershell
$env:RELIABILITY_DATABASE_URL = 'postgresql+psycopg://user:password@localhost/approvalflow_reliability'
python evaluation/reliability.py
```

## Limits that matter

- The 40 evaluation cases are authored regression fixtures, not an independent safety dataset. Real-world false-ready and false-escalation rates remain unmeasured.
- Same-module test filenames are a test-update signal, not proof of meaningful tests, execution or coverage. Unrelated modules with identical basenames can match.
- Risk and credential patterns are limited heuristics; they can miss issues or escalate harmless text. Available patches are not full-repository analysis. Count mismatches identify incomplete patches, but matching counts do not prove complete semantic context or code safety.
- Required check runs must be configured explicitly. Legacy commit-status contexts, branch-protection discovery and organization-wide policy inheritance are not implemented.
- A shared GitHub token and environment-provisioned reviewer credentials suit a single trusted team. This is not a multi-tenant SaaS or OAuth identity service.
- GitHub reads and review creation cannot be one atomic transaction. A push can arrive between the final read and publication; the review is tied to the inspected commit. Configure stale-approval dismissal and branch protection on GitHub. Optional publication is tested with a mock GitHub transport, not a live write.
- The audit log is append-only through the API, not cryptographically tamper-proof. The database administrator can modify it.
- Runtime table creation supports this initial schema. Add explicit migrations before evolving a deployed database.

Next useful milestone: run on a sandbox repository with independently labeled real pull requests, then measure actual reviewer time and disagreement. That evidence is more valuable than adding more services.

## GitHub API references

- [Validate signed webhook deliveries](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)
- [Pull request API](https://docs.github.com/en/rest/pulls/pulls)
- [Check runs API](https://docs.github.com/en/rest/checks/runs)
- [Pull request review API](https://docs.github.com/en/rest/pulls/reviews)

## Project layout

`frontend/` contains the React/TypeScript console and behavior tests. `approvalflow/` contains the API, policy, GitHub adapter, database, worker and isolated demo. `tests/` covers unsafe decisions, signatures, stale evidence, pagination, concurrent claims, resolution races, retry limits, restarts and console integration. `evaluation/` holds labeled scenarios and reproducible experiments. `PROJECT_BRIEF.md` preserves the project goals and resume-writing rule.
