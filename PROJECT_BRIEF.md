# ApprovalFlow project brief

## Goal

Build an internship portfolio project with useful behavior, a small architecture, and reproducible evidence. The target is strong backend engineering discussion for competitive software engineering internships. No project guarantees shortlisting.

## Resume writing rule

The user's requested formula, preserved verbatim:

> “Created/designed <task> with <skills> to <non domain specific term> that <numerical benefit>”

Put relevant skills early, explain what the project does in language a recruiter understands, and connect each metric to an experiment or real usage. Avoid architecture jargon without a user-visible reason. Never invent impact or present planned features as shipped.

## Scope

One Python/FastAPI service, a worker from the same package, and PostgreSQL. SQLite supports an easy local demo. A policy function combines trusted CI, change size, sensitive paths, test-update signals, and risky added operations. Human reviewers resolve recommendations with fresh evidence and a recorded reason.

This version is a deterministic workflow agent. It does not use an LLM, LangGraph or LangChain. Do not describe it as an LLM code reviewer or claim semantic bug detection. An LLM should only be added after a labeled dataset shows it adds value beyond this baseline.

## Definition of done

- Runnable local evaluation and API/worker commands.
- React/TypeScript review console, isolated credential-free demo, and a reproducible interview walkthrough.
- GitHub read adapter, signed webhook ingress and CI-completion triggers.
- Durable jobs, replay deduplication, leases, retries and dead-letter state.
- Authenticated human resolution, author separation, stale-evidence guard and audit records.
- Optional explicit GitHub review publication with fresh evidence and duplicate-submit protection.
- Tests on SQLite and PostgreSQL, a labeled synthetic evaluation and a reproducible reliability experiment.
- Recruiter-readable bullets with honest experiment scope.

## Next evidence worth collecting

Use a sandbox repository to replay real pull requests reviewed by a second person. Measure false-ready rate, unnecessary escalations, time-to-recommendation, GitHub request failures, and actual reviewer time. Keep those measurements separate from synthetic fixtures.
