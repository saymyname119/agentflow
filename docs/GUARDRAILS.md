# Approval guardrails

The agent recommends; an authenticated person decides. `READY` never grants approval authority. Trusted server policy, API authorization, and transactional database constraints enforce the boundary. An optional LLM audit is implemented, disabled by default and always disabled in the isolated demo.

| Boundary | Enforced behavior |
| --- | --- |
| Input | Signed, size-limited webhooks; validated PR references; repository allowlist; operator-only manual queueing. |
| Evidence | Fetched repository and PR number must match the queued request. Required CI matches name, producer and head commit. Missing evidence prevents READY. |
| Policy | Repository titles, patches and comments cannot change server policy. Secret markers and failed required conditions block sign-off. Risk signals require human inspection. |
| Authority | A named reviewer provides a reason; operators and PR authors cannot approve. The same reviewer must explicitly request publication. |
| Freshness | Approval and publication refresh evidence. Changes to head, base, checks, policy or engine invalidate the recommendation. Recommendations expire after one hour; negative age also fails closed. |
| Concurrency | Expiring worker leases, atomic recommendation writes, current-review locks and expected revisions prevent stale or conflicting mutations. |
| External action | Publication is disabled by default, bound to the inspected commit, and protected by a durable reservation. Ambiguous results require manual inspection; no automatic resubmission. No merge endpoint exists. |
| Accountability | Successful analysis, audit reservations/completions, resolution and publication transitions have persistent records. Raw patches are not persisted. Model findings are stored, so their text may reflect repository content; credential-marker checks are limited. Denied attempts are not yet a persistent security-event feed. |

`approvalflow/guardrails.py` is the shared approval boundary. API authorization, deterministic risk rules, and database constraints remain separate enforcement layers. An API preflight alone cannot replace transactional checks.

## LLM audit boundary

The optional audit validates a strict output schema and every finding's path/added-line anchor. It bounds input, response bytes and output tokens, applies HTTP timeouts, and sends no tools or GitHub credentials. Repository text is untrusted data; returned text is never executed. Prompt instructions help steer the model but do not prove resistance to prompt injection.

Enabling audit makes a completed report mandatory. The report is bound to an immutable recommendation (and thus its evidence fingerprint) and the model/prompt version. Evidence is refreshed before and after generation and again before approval/publication. Approval requires the current report ID and the UI requires explicit acknowledgement. A model report never changes the deterministic outcome or removes a blocker. The named reviewer remains responsible for deciding how to address findings.

Database reservations permit one request per recommendation/configuration, including across server restarts. Failed or interrupted requests do not retry automatically and cannot satisfy the approval gate; request a fresh recommendation. No global spending limit is implemented; configure provider budgets. See LLM_AUDIT.md for setup and limitations.

## Limits

Rules do not prove program correctness or complete secret detection. Local reviewer names are configured identities, not verified GitHub user identities. Published approvals cannot be retracted by this system, and an external write already authorized at reservation can remain in flight when a new event arrives. Live GitHub integration, production deployment, rate limiting, independent review-quality evaluation and deployment-specific access controls still need verification.
