# ApprovalFlow - evidence-backed resume points

**Python, FastAPI, PostgreSQL, React, TypeScript, SQLAlchemy, GitHub REST API, Docker, GitHub Actions**

Use the bullets below for the implemented project. GitHub Actions passed for the foundation and guardrail releases, including frontend and SQLite/PostgreSQL jobs (see docs/RELEASE.md). Docker deployment has not been verified.

- Built a Python/FastAPI GitHub review agent with a React/TypeScript dashboard to flag risky code changes, reducing unsafe readiness recommendations from 26 to 0 against a CI-only baseline across 40 synthetic scenarios.
- Used PostgreSQL transactions and version checks to prevent conflicting reviewer decisions, recording exactly one resolution in each of 100 simulated races with 32 concurrent requests.
- Implemented Python workers and signed webhooks to process review requests reliably, deduplicating 1,000 repeated deliveries and recovering 20/20 jobs after simulated restarts.

## Evidence and exact meaning

| Claim | Evidence | What it does not establish |
| --- | --- | --- |
| 26 to 0 unsafe readiness recommendations | `evaluation/results.json`: 40 hand-authored cases; 31 expected to require review or blocking; simple CI-only baseline cleared 26; agent cleared zero | Real-world safety, independent evaluation, bugs prevented in production |
| One resolution per race | `evaluation/reliability-results.json`: PostgreSQL 18, 100 races x 32 simultaneous update attempts, 100 successful resolutions and 100 matching audit events | 3,200 concurrent users or sustained production throughput |
| 1,000 deliveries deduplicated | Same reliability report: 16 concurrent clients replayed one delivery ID 1,000 times, producing one job | 1,000 distinct requests processed or exactly-once distributed execution |
| 20/20 jobs recovered | Same reliability report: engine disposed/reopened after claim, lease expired, replacement worker reclaimed the job, stale worker was fenced | Operating-system crashes, power failures or network-partition recovery |
| Test suite | `evaluation/verification.json` records final local suite results against SQLite and PostgreSQL | Remote GitHub Actions success before a push |

## Interview explanation

The agent helps a reviewer decide which changes need attention. It checks the exact commit's trusted CI results, inspects risk signals and supporting test updates, and saves an explanation. A reviewer signs off with a reason. If the code or evidence changes before sign-off, the service requires a fresh recommendation.

The interesting engineering is handling retries, duplicate events, stale evidence and conflicting reviewer decisions. PostgreSQL is responsible for durable records and atomic updates. A separate message broker was unnecessary for this workload.

The core uses deterministic rules; an optional LLM audit has schema validation, added-line citations and human acknowledgement. Its adapter and guardrails are tested with simulated provider responses, not a live model benchmark. Optional GitHub review publication requires an explicit human request and is disabled by default. Do not claim measured model accuracy, production time savings, unattended GitHub approvals, or guaranteed internship shortlisting.

## Better future metrics

For a stronger second version, label real pull requests with a second reviewer before evaluating them. Measure unsafe readiness recommendations, unnecessary escalations, reviewer disagreement, API response time including GitHub access, and actual review time saved. Replace synthetic numbers only after collecting reproducible results.
