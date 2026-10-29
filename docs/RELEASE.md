# v0.2 delivery record

Historical record for v0.2. The current v0.3 implementation adds the optional advisory audit described below; v0.2's statements about unimplemented LLM support apply only to that earlier release.

Repository: https://github.com/saymyname119/agentflow

ApprovalFlow is the product name; agentflow is the GitHub repository name.

## Delivery phases

1. Full-stack application, product site, deterministic review workflow, PostgreSQL durability, evaluation and backend audit (`2eedf70`). Pushed on 29 October 2026. GitHub Actions passed: https://github.com/saymyname119/agentflow/actions/runs/40808460436.
2. Shared approval guardrails, wrong-PR evidence rejection, conservative clock handling, regression tests and guardrail design (`3aba435`). Local SQLite verification: 148 passed; synthetic policy evaluation: 40/40. GitHub Actions passed: https://github.com/saymyname119/agentflow/actions/runs/40808576095. Local frontend: 13 tests passed, formatting check and TypeScript/production build passed.
3. Release verification record and reproducible handoff documentation. Each push runs the frontend suite/build and SQLite/PostgreSQL suites in GitHub Actions.

## Run and demonstrate

Follow the README setup, build the frontend, then run `approvalflow demo`. Open http://127.0.0.1:8000 and enter the review workspace. Demonstrate a ready change, a blocked change, a reviewer decision with a reason, its audit trail, and an operator-requested refresh. Demo publication stays disabled and does not contact GitHub.

## Scope and acceptance

This completes the implemented v0.2 portfolio release, not a production rollout. The shipped agent uses deterministic rules. An LLM audit is not connected; its required trust boundary is documented in GUARDRAILS.md. Live GitHub approval publication requires separately configured credentials and an explicit human action. No actual PR approval or merge was performed during delivery.

Before production, verify live installation permissions and real webhook deliveries in a sandbox, introduce migrations and operational monitoring, and independently evaluate review quality. Docker configuration is supplied but container operation has not been verified. Resume numbers describe controlled synthetic experiments and must retain that scope.

## v0.3: optional guarded LLM audit

Implemented on 29 October 2026: fixed-origin OpenAI Responses adapter, strict structured findings, added-line validation, input/output budgets, credential-marker rejection, persistent once-per-recommendation reservations, refreshed evidence, mandatory report acknowledgement when enabled, and approval/publication gates. The review workspace includes an LLM audit tab with explicit disabled, running, completed and unavailable states.

The default demo still makes no external model calls. Live mode requires an API key and a chosen model available to that account; see LLM_AUDIT.md. Adapter tests use simulated provider responses and do not establish model accuracy. Deployment and live credentialed integration remain operational acceptance steps, not completed claims.

Verification: 171 backend tests, 16 frontend tests, formatting and production build passed. Remote frontend, SQLite and PostgreSQL jobs passed for `93c2231`: https://github.com/saymyname119/agentflow/actions/runs/40810463881. No live model call or live GitHub approval was performed.
