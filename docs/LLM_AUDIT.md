# Optional advisory LLM audit

The audit uses OpenAI's Responses API with strict structured output. Reference: [official structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

## Setup

1. Configure `OPENAI_API_KEY`, an accessible structured-output-capable `LLM_MODEL`, and `LLM_AUDIT_ENABLED=true` on the server. Do not commit credentials. No specific model or cost is assumed. Configure account/project spending limits at the provider.
2. Restart the API in live mode. The worker still produces deterministic recommendations; it does not call a model. The isolated demo forcibly disables external audits.
3. Queue a review, sign in as a named reviewer other than the author, open **LLM audit** and select **Run LLM audit**. This explicitly sends the diff to OpenAI. Blocked, stale and superseded recommendations cannot start an audit.
4. Inspect findings, acknowledge the report, and approve or reject with a reason. An empty report does not establish safety. High-severity findings require the reviewer's judgment; they are not automatically resolved by the model.

## Contract and failure behavior

`POST /decisions/{id}/llm-audit` requires a named non-author reviewer. `GET /decisions/{id}` includes the report and its state. With audit enabled, approval requires `expected_audit_id` identifying a completed report for the current audit configuration. Publication also checks the gate, including decisions approved before audit was enabled.

The adapter sends only changed-file paths, patches and added-line anchors, not full repository context or reviewer credentials. It uses a fixed HTTPS endpoint, no tools or redirects, no automatic retries, a 60,000-byte JSON input bound, a 64,000-byte response bound, a 2,500 output-token cap, and HTTP timeouts of 5 seconds to connect and 25 seconds for other operations. This is not a guaranteed wall-clock deadline or a global monetary budget.

The model must return at most 12 findings with path, positive added-line number, severity, title, explanation and suggestion. Unknown fields, malformed output, incomplete/refused responses, ungrounded line references and recognized credential markers are rejected. Recognized credential markers in input prevent the external call. These markers are not comprehensive secret detection: authorized operators must assess source confidentiality. `store=false` disables response storage for the API request; it does not promise zero provider retention under all account policies.

A durable reservation limits each recommendation/configuration to one attempt. A timeout, provider error, invalid report, changed evidence or interrupted process leaves approval blocked. Queue a fresh review to retry; no reset endpoint exists. Successful reports are persisted without patches. Finding text can still reflect code and must be treated as potentially sensitive. Prompts and schema checks constrain behavior, but do not establish semantic correctness or immunity to prompt injection.

## Verification

Tests use `httpx.MockTransport` and fake auditors to exercise the actual adapter, API gates and persistence. They cover request boundaries, invalid citations, unsupported fields, refusal, truncation, timeouts, duplicate calls, evidence changes, acknowledgement and publication gating. React tests verify disabled, successful and unavailable audit states. These are integration/guardrail tests, not a model-quality benchmark. No live model request or measured accuracy claim is included.

Independent labeled PRs and a credentialed sandbox run remain necessary to assess model usefulness before relying on it operationally.
