# Repository-aware implementation prompt

## Goal

Add a read-only product visibility capability for a product assembled from multiple repositories, using the existing Wale and AgentFlow systems.

This prompt describes proposed implementation work. It is not a claim that the standalone prototype has already been integrated or that native task/release authority has been granted.

## Starting evidence

The Wale product visibility package contains a runnable Python prototype, a proposed `product.json`, a real dated GitHub report, a synthetic demo, tests, and `SOLUTION.md`.

Current inspected documentation gives Wale responsibility for intent investigation, handoff preparation, and evidence audit; AgentFlow owns execution, worktrees, validation, integration, and build receipts. Traffic Control Pilot is optional within eligible runs. Wale Director is a future-state interface in the inspected feature matrix. Recheck current repository truth before acting.

## Scope and defaults

- Preserve existing canonical tasks, backlogs, approvals, receipts, execution ownership, and UI conventions.
- Treat product composition and selected evidence requirements as explicit reviewed data.
- Start with Wale and AgentFlow for the “Verify one approved change” capability.
- Display Traffic Control Pilot as optional context. A capability that uses it must include it explicitly in its evidence scope.
- Do not assume DecisionIntelligence is a Wale alias.
- Use read-only GitHub and local/native adapters.
- Keep implementation isolated from active user work. No deployment, merge, workflow rerun, or other consequential external action is implied.

## First inspect

Read the governing instructions, current branch/worktree status, native task model, Wale feature matrix and ecosystem contracts, existing Wale operator-shell read models, and AgentFlow repository/build/receipt interfaces.

Identify the smallest existing UI and schema surface that can host the product projection. Verify exported APIs or modules from source; do not invent endpoints. Check whether equivalent product membership or cross-repository evidence records already exist.

Report any material conflict between this design and current authority or implementation. Continue safe read-only discovery and reversible local work within the granted scope; clarify only choices that materially change architecture, authority, or outcome.

## Implement one bounded slice

1. Define or reuse a product composition record with stable IDs, source locations, typed required/optional relationships, capability mapping, native source links, selected references, and evidence requirements.
2. Collect exact GitHub revision and selected CI observations with timestamps and per-source coverage. Preserve workflow identity, path, event, run/attempt, and tested SHA.
3. Read existing AgentFlow repository/build/receipt information through a verified native interface or export. Treat absent access as unknown.
4. Render product composition, capabilities, source coverage, open work, exact versions, failing checks, and missing integration evidence in the existing interface.
5. Keep observed heads, explicitly selected candidates, and deployed versions separate.
6. Use native evidence audit for any acceptance claim. Prototype receipt field matching alone is unauthenticated and cannot establish acceptance.
7. Add local worktree visibility only through explicitly configured local locations. Show the freshness of cached remote refs.

The projection must not become a new scheduler, backlog, approval system, or independent execution authority.

## Required acceptance cases

- A failed push CI result remains visible beside a newer successful dependency-update or manual workflow.
- No configured CI, skipped/cancelled CI, missing permissions, incomplete pagination, stale data, and malformed evidence cannot become passing.
- Two independently passing repositories with no integration evidence remain unverified as a product combination.
- A receipt for another manifest, component set, criteria set, repository identity, or SHA cannot satisfy the candidate.
- A displayed optional component outside acceptance scope does not block core-scope evidence matching.
- A shared repository or component cannot silently double-count PRs or inflate product coverage.
- Local-only work is labeled unavailable until a local adapter observes it.
- A merged or tested candidate cannot become deployed or human-accepted by inference.
- Untrusted issue titles, PR content, workflow text, source errors, and evidence URLs render safely.

## Delivery

Return the smallest working local change, the affected native interfaces, meaningful tests and fresh results, remaining proof boundaries, and a rollback path. Clearly distinguish proposed, implemented, tested, observed, and deployed states.

Use existing repository conventions for retaining the design and implementation evidence. Do not create parallel governance records merely to satisfy this prompt.

