# Backend audit and goal assessment

## Verdict

The local portfolio product and its core review-workflow goals are met after the fixes in this audit. The application is not yet validated as a production GitHub approval service. It remains a deterministic, evidence-based workflow agent with human oversight, not an LLM or semantic code analyzer.

The earlier 119-test suite missed important failure cases. Twelve newly written regression cases failed against the earlier implementation. Those failures were reproduced before fixes; the expanded suite now contains 144 passing backend cases on each of SQLite and PostgreSQL. Additional cases cover transaction rollback, interleaved refresh/write races, supported repository names, database readiness, and engine-version invalidation.

## Issues found and fixed

| Priority | Original problem | Correction and evidence |
| --- | --- | --- |
| P1 | An expired worker could insert a visible recommendation before its job-completion write was rejected. A crash between saving the recommendation and finishing the job could also leave partially committed work. | `Store.complete` fences the lease and commits the recommendation, audit event, current-review pointer and job result in one transaction. Expired-owner and rollback tests verify there is no visible partial decision. |
| P1 | A previously approved recommendation could still be published after a newer recommendation for the same PR had been rejected. Version checks protected one record, not the sequence of reviews. | A small `review_heads` table provides a current-decision pointer and a per-PR write lock. Recommendation creation, resolution, and publication reservation serialize through that row. Superseded records remain readable but cannot start new decision actions. Tests also create a newer record during GitHub refresh, before the final database write. |
| P1 | Silent truncation of GitHub file patches could be treated as inspected evidence. The added-line parser also skipped lines beginning with `+++` and split Unicode separators as if they were physical diff lines, hiding credential markers in those cases. | The GitHub adapter compares visible addition/deletion counts with reported counts and sets an explicit completeness flag. Available text is retained for risk scanning, so a visible secret still blocks an incomplete patch. Added-line parsing now follows physical newline boundaries and scans plus-prefixed additions. |
| P2 | Database failures during job claiming or retry recording could terminate the worker. `/health` returned success even when the database was unavailable. | Database exceptions are logged safely without stopping the polling loop. Failed completion transactions leave work available for lease-based recovery. Readiness now queries the database and returns HTTP 503 on a database failure. |
| P2 | A malformed event action could trigger HTTP 500. Boolean and oversized PR numbers could pass validation or overflow the database. Legitimate `.github` repository names were rejected. | Actions are type-checked, PR numbers are strict positive integers bounded by the database representation, and repository validation allows dot names while rejecting traversal segments. Repository identity is canonicalized to lowercase. |
| P2 | Equivalent file/check lists in a different order invalidated an otherwise identical recommendation. Configuration version alone did not explicitly bind a recommendation to evaluator code revisions. | Fingerprints normalize unordered evidence/configuration lists, retain all content, and include a separate policy-engine version. Reordered content remains equivalent; changed CI, patches, policy, or engine versions invalidate the earlier binding. |
| P2 | The newest 100 records were selected before filtering allowed repositories. Unrelated repositories could crowd authorized reviews out of the inbox. | Repository filtering happens in the database before the result limit. A regression fills the history with 101 unrelated records and verifies the allowed record is still returned. |
| P2 | Renaming a source file into a non-source or test classification could bypass the source-change review signal. | Original source filenames now produce an explicit source-rename review finding. |

The frontend also recognizes `is_current: false`, labels historical recommendations and disables their decision controls. The backend remains authoritative; the UI cannot override these guards.

## Verification performed

- Backend: **144 passed on SQLite; 144 passed on PostgreSQL 18.6**, without skipped cases.
- Frontend: **13 passed**, including historical-review action controls and the existing product/workspace flows.
- Actual local HTTP smoke check after restart: database health passed, the demo worker completed a queued review, the new recommendation was current, its predecessor was historical, and approving the predecessor returned HTTP 409. Engine version was `2026-10-28.2`; GitHub publication stayed disabled.
- The original **40/40** synthetic policy scenarios remain a separate, reproducible regression evaluation. They are not independent evidence of real-world safety or measured team savings.
- PostgreSQL reliability rerun uses the actual atomic completion path: **1,000 deliveries → one job**, **100 approval races × 32 attempts → one winner per race**, **20/20 restarted jobs recovered**, and **20 expired-worker recommendation writes prevented**.
- GitHub reads and writes were simulated with HTTP mock transports. No real GitHub approval was posted.

Full details are in `evaluation/verification.json`, `evaluation/results.json`, and `evaluation/reliability-results.json`. Timing varies by environment and is not a production throughput claim.

## App goals: reached or not?

| Goal | Status | Practical meaning |
| --- | --- | --- |
| Useful PR triage with clear explanations | Reached locally | Checks combine exact-commit CI, configured producers, sensitive changes, test-update signals and limited risk/credential patterns. |
| Human control and accountable decisions | Reached locally | Named reviewer credentials, author separation, fresh evidence, current-review checks, reasons and audit history are implemented and tested. |
| Durable processing and conflict prevention | Reached in controlled tests | Atomic completion, delivery deduplication, leases, retries, current-review locking and resolution concurrency passed on both databases. |
| Usable full-stack demonstration | Reached locally | The React console and isolated, credential-free demo exercise the real policy and database code. |
| Live GitHub end-to-end integration | Partially reached | The adapter, signed webhooks and explicit publication path exist. Actual installation permissions, required check names/app IDs, event deliveries and live review creation still need sandbox verification. |
| Independent evidence of review quality | Not reached | The 40 labeled scenarios were authored with the implementation. An independent reviewer and real sandbox PRs are needed to estimate unsafe readiness and unnecessary escalation rates. |
| Hosted production deployment | Not reached | Docker and CI configuration are supplied; hosted operation and remote CI success have not been demonstrated. |
| Internship shortlisting | Not verifiable from the app | This now supplies stronger engineering examples and reproducible resume claims. It cannot establish a hiring outcome. |

## Limits and next acceptance checks

1. Connect an intended sandbox repository, configure its actual check names/producers, and test open, synchronize, CI completion, conflicting changes, token expiry, API rate limits, and explicit review publication.
2. Independently label real PRs before measuring review quality. Track unsafe ready recommendations, unnecessary escalations, disagreement and actual reviewer time. Do not relabel the existing fixtures as independent validation.
3. Before production, introduce an explicit migration/rollback process, backup/restore checks, deployment monitoring and appropriately managed credentials/HTTPS. Environment-provisioned tokens are the current single-team scope, not a multi-tenant identity system.
4. The API returns the newest 100 authorized recommendation records. High-volume inbox/history pagination and retention are not implemented.
5. Test-name matching and credential/risk patterns are limited heuristics. They do not prove meaningful tests, full code safety, or comprehensive secret detection.
6. The database and GitHub cannot commit one transaction together. Publication is authorized at its current-review reservation and pinned to the inspected commit. A later push, new review or rejection cannot cancel a write already in flight or revoke an earlier GitHub review. Keep stale-approval dismissal and branch protection enabled. Uncertain/sending publication attempts require manual inspection; there is no automatic resubmission or reconciliation endpoint.
7. Worker leases are bounded. A very slow evidence fetch may lose its lease and need another attempt. Rate-limit scheduling and automatic GitHub App token renewal are not implemented.

## Upgrade notes

- This change adds the `review_heads` table. It is created through the existing initial-schema mechanism; pointers for earlier records are initialized lazily. A deployed service should adopt explicit migrations before further schema evolution.
- The new engine revision and fingerprint normalization invalidate earlier evidence bindings. Queue fresh reviews after upgrading rather than trying to publish earlier approvals.
- Increment `POLICY_ENGINE_VERSION` whenever evaluator logic changes. Operator configuration versions and evaluator versions are separate.
- `/health` checks API/database readiness. It does not prove that a separate live worker is running or that GitHub is reachable.
- Failed API requests and worker database errors do not expose connection strings, tokens, source patches or raw exception messages in persisted error fields.

## GitHub reference checked

The adapter and its conservative behavior were checked against the official [pull-request files API](https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files) and [check-runs API](https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference). These references describe API behavior; they do not substitute for a real installation test.
