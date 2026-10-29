# Approval guardrails

The agent recommends; an authenticated person decides. `READY` never grants approval authority. Trusted server policy, API authorization, and transactional database constraints enforce the boundary. No LLM is connected today.

| Boundary | Enforced behavior |
| --- | --- |
| Input | Signed, size-limited webhooks; validated PR references; repository allowlist; operator-only manual queueing. |
| Evidence | Fetched repository and PR number must match the queued request. Required CI matches name, producer and head commit. Missing evidence prevents READY. |
| Policy | Repository titles, patches and comments cannot change server policy. Secret markers and failed required conditions block sign-off. Risk signals require human inspection. |
| Authority | A named reviewer provides a reason; operators and PR authors cannot approve. The same reviewer must explicitly request publication. |
| Freshness | Approval and publication refresh evidence. Changes to head, base, checks, policy or engine invalidate the recommendation. Recommendations expire after one hour; negative age also fails closed. |
| Concurrency | Expiring worker leases, atomic recommendation writes, current-review locks and expected revisions prevent stale or conflicting mutations. |
| External action | Publication is disabled by default, bound to the inspected commit, and protected by a durable reservation. Ambiguous results require manual inspection; no automatic resubmission. No merge endpoint exists. |
| Accountability | Successful analysis, resolution and publication transitions have persistent records. Raw patches and credential values are not persisted. Denied attempts are not yet a persistent security-event feed. |

`approvalflow/guardrails.py` is the shared approval boundary. API authorization, deterministic risk rules, and database constraints remain separate enforcement layers. An API preflight alone cannot replace transactional checks.

## Boundary for a future LLM audit

An LLM audit is advisory and is not implemented. Before connecting one, require schema-validated findings with valid changed-file and line references, bounded context and output, a deadline and request/token budget, and explicit unavailable/invalid states. Repository text is untrusted data, including instructions embedded in comments. The model receives no GitHub write credentials or tools. Do not interpret its prose as executable actions.

When an audit is configured as required, timeout, invalid output or unavailability must prevent approval; never silently skip the required audit. Bind its result to the evidence fingerprint and audit configuration so an older result cannot authorize a newer PR. Findings may increase required scrutiny; model output must never lower deterministic risk or remove a blocker. These are requirements for the future integration, not claims about present protection against LLM attacks.

## Limits

Rules do not prove program correctness or complete secret detection. Local reviewer names are configured identities, not verified GitHub user identities. Published approvals cannot be retracted by this system, and an external write already authorized at reservation can remain in flight when a new event arrives. Live GitHub integration, production deployment, rate limiting, independent review-quality evaluation and deployment-specific access controls still need verification.
