# ApprovalFlow: three-minute project walkthrough

## The problem in one sentence

Passing tests alone does not tell a reviewer whether a change touches payment logic, authentication, infrastructure, or other areas that deserve attention.

## Before recording or presenting

Run the local demo with `approvalflow demo` after building the frontend. Open `http://127.0.0.1:8000`, then choose **Open review workspace** (or go directly to `/#/workspace`). The sample repository and PRs are fixtures, labeled as a demo. No GitHub account or model API key is needed. Restarting creates a fresh session.

## Show the workflow

1. **Explain the inbox (20 seconds).** Open PR #142, a sample checkout change. The required checks pass, yet the recommendation asks for human review because payment logic changed. This is the useful distinction from simply checking whether CI is green.
2. **Show the evidence (40 seconds).** Inspect the risk finding, Files changed and Checks tabs. Point out that evidence is tied to a specific commit and trusted GitHub check producer. The service does not execute untrusted PR code or save source patches.
3. **Make a decision (30 seconds).** Add a concrete reviewer reason and approve. Open Activity to show the named actor, reason, time and policy version. The demo saves a real local decision; GitHub publication stays disabled.
4. **Show a blocked case (20 seconds).** Select #145. The failing required check disables approval, while rejection stays available with a reason. A failed safety condition cannot be bypassed by the approval endpoint.
5. **Show a fresh review (30 seconds).** Use the account menu to switch to operator access. Queue #143, observe processing, then return to reviewer access. Explain that the demo worker and live worker share the same processing function; only the GitHub evidence source differs.
6. **Show the evidence for the project (40 seconds).** Open Measured results. Explain the CI-only baseline, the synthetic scope of the 40 scenarios, and the PostgreSQL concurrency/recovery experiments. Do not present them as production savings.

## Technical questions worth preparing

**Why a database queue?** Jobs need durable state, deduplication and retries. PostgreSQL already provides transactions and conditional updates, so a separate broker would add operational cost without evidence that this workload needs one.

**How do you stop double decisions?** Update a decision only when its revision matches and it is still unresolved. The winning update and audit event commit in the same transaction. The measured experiment used 100 races with 32 simultaneous update attempts per race.

**How does crash recovery work?** A job has an expiring worker lease and a lease token. Another worker can reclaim expired work; an old worker cannot finish using its earlier token. The experiment simulates connection restarts and lease expiry, not OS failures.

**What if the PR changes?** Before approval, collect a fresh snapshot and compare its fingerprint, including head, base, CI, policy content and patch content. Mismatches require another recommendation. The GitHub adapter also checks for torn reads while collecting evidence.

**What if GitHub accepts a publication but the response times out?** A durable publication reservation prevents automatic resubmission for that decision. The outcome stays uncertain for manual inspection. GitHub and PostgreSQL do not share a transaction, so this version deliberately does not claim exactly-once remote delivery.

**Where is the AI?** The core workflow is deterministic. A configurable OpenAI audit provides structured, line-anchored advisory findings in live mode; the fixture-backed demo disables it. When enabled, a completed and acknowledged report is required for approval, but cannot remove rule-based blockers. Model quality has not been independently benchmarked.

**What would you improve next?** Independently label real sandbox PRs, measure unnecessary escalations and reviewer disagreement, add explicit database migrations for schema evolution, and validate the live GitHub integration. Avoid claiming those steps are already complete.

## What is ready and what remains external

The local full-stack demo, backend, UI workflows, evaluation scripts and repository documentation are implemented. Docker and GitHub Actions configuration are supplied. A public repository URL, hosted demo, successful remote CI and real GitHub publication still require connection to the intended account/environment; none are claimed here.
