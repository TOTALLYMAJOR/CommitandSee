# Wale: one product view across multiple repositories

**Design and read-only observation: November 4, 2026**  
**Recommendation:** create a small product-composition and evidence view above the existing repositories, with Wale Director as its eventual interface. Keep native repository backlogs, authority, execution, and acceptance records in their existing systems.

## The job this solves

A repository view answers questions about one source tree. A product view must answer a different set of questions:

1. Which components belong to this product, and what does each contribute?
2. Which user capability spans more than one repository?
3. Which exact versions are being assessed together?
4. What changed since the selected baseline, and which other components might be affected?
5. What is blocked, untested, or missing evidence?
6. What was integrated, deployed, and accepted—and what evidence establishes each state?

The central record is a **product manifest**. It declares composition and evidence expectations. Collection produces observations. A report connects those observations to capabilities and versions. None of these records grants execution or release authority.

A repository need not be merged into another repository to participate in this view. Repository layout is a separate engineering decision.

## Enhanced execution specification

Act as a product-platform architect, Python implementer, and evidence reviewer. Design a read-only view of one product assembled from multiple GitHub repositories, using Wale as the example. Read current repository documentation and GitHub observations. Map product capabilities to component repositories and typed relationships. Preserve existing Wale and AgentFlow ownership. Compare GitHub Projects, a small Python projection, and Backstage. Deliver a working local collector/report prototype, an honest observed snapshot, a proposed manifest, and a repository-aware integration prompt. Verify meaningful failure cases. Distinguish declared, observed, integrated, deployed, and accepted states. Keep missing, inaccessible, stale, and incomplete data explicit. Treat a supplied receipt as unauthenticated until its producer and underlying evidence are independently verified.

### Confirmed intent and reversible assumptions

**Confirmed:** the user needs visibility across repositories that collectively deliver a product. Wale is the motivating context. The selected app is Code Tytor: Python.

**Assumptions for this starter:** start with a local read-only tool; use the documented Wale/AgentFlow relationship; display Traffic Control Pilot as optional; select the current `main` references and observed named CI workflows; retain the proposed composition until the operator confirms it.

**Not assumed:** these three repositories form a fully accepted release, all relevant work is pushed, current main branches are the intended integration baseline, or DecisionIntelligence is an alias for Wale.

## What the current repository evidence says

| Repository or source | Observed documentation | Design implication |
| --- | --- | --- |
| [Wale README](https://github.com/TOTALLYMAJOR/Wale/blob/a1294d62b4fb126531a2a131bcb209f4f8689067/README.md) | Describes intent, repository evidence, approved AgentFlow execution, verification, and bounded learning; links an ecosystem contract. | Reuse that contract for role and authority mapping. |
| [Wale feature matrix](https://github.com/TOTALLYMAJOR/Wale/blob/a1294d62b4fb126531a2a131bcb209f4f8689067/docs/FEATURE_MATRIX.md) | Describes the operator shell as implemented and Director as future-state; separates implemented, foundation, and proposed capabilities. | Treat a product-wide Director view as proposed integration work, not an existing feature. |
| [AgentFlow README](https://github.com/TOTALLYMAJOR/AgentFlow/blob/c5d25181a3e4f7665f38753cf374264bcc2cd69b/README.md) | Describes multi-repository planning, worktrees, validation, integration, receipts, and its dashboard. | Read its native records instead of introducing another scheduler or execution database. |
| [Traffic Control Pilot README](https://github.com/TOTALLYMAJOR/Traffic-Control-Pilot/blob/53488c86be74ae23f74fdedadcd97d8f15467d23/README.md) | Describes an optional continuation governor inside eligible AgentFlow runs. | Model a conditional relationship, not a mandatory serial stage. |
| [DecisionIntelligence README](https://github.com/TOTALLYMAJOR/DecisionIntelligence/blob/main/README.md) | Currently describes a separate Limitless Architecting OS starter. | Do not infer current product membership or aliasing from historical naming. |

These are documentation observations. This request did not audit all implementation, run native repository tests, or verify the complete integration. Where a document reports a successful historical pilot, that remains the document's reported boundary unless its underlying evidence is independently checked.

## A concrete visibility problem found during this request

The connected GitHub API returned the following current `main` observations:

| Repository | Observed main SHA | Selected CI observation | Open PRs observed |
| --- | --- | --- | --- |
| Wale | `a1294d62b4fb126531a2a131bcb209f4f8689067` | [Design Intelligence CI: failure](https://github.com/TOTALLYMAJOR/Wale/actions/runs/39741088818) | 0 |
| AgentFlow | `c5d25181a3e4f7665f38753cf374264bcc2cd69b` | [AgentFlow CI: success](https://github.com/TOTALLYMAJOR/AgentFlow/actions/runs/39885356675) | 2 |
| Traffic Control Pilot | `53488c86be74ae23f74fdedadcd97d8f15467d23` | [Traffic Control CI: success](https://github.com/TOTALLYMAJOR/Traffic-Control-Pilot/actions/runs/39156041160) | 0 |

Wale also has a [newer successful dependency-graph job](https://github.com/TOTALLYMAJOR/Wale/actions/runs/41921457862) associated with the same SHA. Selecting the most recent workflow without identifying its purpose could present a green result while the actual selected CI workflow failed.

AgentFlow's open work includes [draft PR #11, guided workflows and native Wale evidence](https://github.com/TOTALLYMAJOR/AgentFlow/pull/11), and [PR #10, dependency updates](https://github.com/TOTALLYMAJOR/AgentFlow/pull/10). These are open changes, not merged capabilities.

This snapshot establishes published GitHub observations. It does not identify the cause of Wale's CI failure, establish the state of local development, select a product candidate, or prove product compatibility. An old check result at an unchanged SHA remains an observation of that check; it does not establish current environment behavior.

## The recommended product model

### Product → capability → component → source location → evidence

A product groups capabilities. A capability describes an outcome a user can achieve. Components contribute to those capabilities. A component refers to one or more source locations, packages, services, or artifacts.

A full implementation should separate these identities:

| Entity | Important fields |
| --- | --- |
| Product | Stable ID, name, owner, composition revision, release profile |
| Capability | Stable ID, outcome, native requirement links, acceptance criteria |
| Component | Stable ID, role, owner, lifecycle, applicability |
| Source location | GitHub repository ID, current slug, path/package, exact revision |
| Relationship | Source, target, type, required/optional/conditional, evidence source |
| Observation | Source URL, collection time, tested revision, result, coverage, freshness |
| Candidate | Explicitly selected component versions, artifact/configuration bindings |
| Integration result | Candidate binding, criteria/configuration digest, run identity, result |
| Deployment | Environment, artifact/version vector, deployment identity, observation |
| Acceptance | Native authorized decision and its scope/evidence references |

A single repository may contain several components. A shared component may belong to several products. The first Python starter permits one component per repository, rejects duplicate repository slugs, and does not yet supply path-level ownership or a reusable multi-product catalog.

Stable GitHub repository IDs are useful because names can change. A repository with a familiar name is not sufficient evidence that it is the same repository previously registered. The starter records IDs and can compare them in a supplied receipt; a production registry should pin and reconcile identities explicitly.

### Typed relationships

The graph should distinguish:

- **Build dependency:** a package or artifact is needed to build another component.
- **Runtime dependency:** a component calls or needs another running component.
- **Contract dependency:** two components exchange a schema, protocol, or API.
- **Delivery coordination:** changes must be integrated or released in a compatible order.
- **Evidence exchange:** a handoff, result, or receipt moves between systems.
- **Guidance reference:** a knowledge source informs reasoning.
- **Optional extension:** the relationship applies only to a selected capability or run profile.

For Wale, an approved handoff and returned receipt are evidence/delivery relationships with AgentFlow. Traffic Control's relationship is conditional on an eligible, opted-in AgentFlow run. AI Leverage Library and Cognitive Strategy Utility should not become required runtime services simply because their guidance is relevant.

The current [affiliate contract](https://github.com/TOTALLYMAJOR/Wale/blob/a1294d62b4fb126531a2a131bcb209f4f8689067/docs/ecosystem/affiliate-contract.md) explicitly preserves these role boundaries and says an absent optional relationship is not a failed dependency.

## Keep three version views separate

| View | Question it answers | Evidence required |
| --- | --- | --- |
| Observed heads | What is published at the references I inspected? | GitHub ref resolution and collection timestamps |
| Selected candidate | Which versions do I intend to assess together? | An explicit immutable component version set |
| Deployed environment | Which artifacts are actually running here? | Deployment/runtime records bound to artifacts and environment |

Moving branch names are inputs to collection. Resolve them to exact SHAs and retain that vector. Do not silently move a candidate as new commits arrive.

The starter reports observed heads only. A file containing several current main SHAs is not an atomic product release. Collection occurs over an interval; the report preserves that boundary. A future candidate selector should freeze a reviewed set and detect relevant changes before claiming it still matches current integration inputs.

If built artifacts are the subject of testing or deployment, their digests matter too. A source SHA alone does not identify build tools, external dependencies, generated assets, configuration, or the deployed binary.

## The useful interface

### 1. Product overview

Lead with product/capability questions:

- Which components are included, optional, missing, or proposed?
- Which candidate, if any, is being assessed?
- Which blocking observation requires attention?
- What evidence has not been collected?
- When was each source checked?

Show repository activity and PR counts as supporting facts. Avoid a single “85% healthy” or “90% complete” number unless the denominator and evaluator have been defined.

### 2. Capabilities and blockers

A capability row might read:

> Verify one approved change — Wale + AgentFlow — handoff observed; implementation receipt unavailable; cross-repository acceptance unknown.

Every state should link to its source. A native task or acceptance record remains canonical. A dashboard summary should never become a second editable truth.

### 3. Changes and potential impact

Compare a selected baseline with the candidate. Show changed components and paths, linked tasks/PRs, declared downstream relationships, and the tests that cover those relationships.

Label graph traversal as “potentially affected through a declared dependency.” It does not prove that a code change broke a consumer. Static dependency discovery, schema comparison, contract tests, and runtime observation provide different strengths of evidence.

The first starter lists declared relationships and current open PRs; baseline comparison and path-level impact analysis are future additions.

### 4. Release evidence

Show the selected version set, per-component check results, integration evidence, environment, and native acceptance decisions separately.

A green repository check answers a narrower question than a passing cross-repository journey. A matching JSON receipt answers a narrower question than an authenticated test run. A successful integration run answers a narrower question than production deployment or customer acceptance.

### 5. Local work and execution

For this local-first ecosystem, a GitHub-only report will miss important work. The next adapter should read local repository registration, worktree state, ahead/behind references, and existing AgentFlow run/receipt data. It should state when remote tracking references were last refreshed; cached refs do not prove current remote state.

Local inspection should use configured locations and existing documented APIs/exports. Do not scrape arbitrary files or invent an AgentFlow endpoint. Preserve native schema and ownership boundaries.

## Architecture and implementation

A minimal design is:

- **Composition file:** user-reviewed JSON initially; a schema-backed native record later.
- **GitHub reader:** GET-only metadata, refs, PRs, selected workflow evidence.
- **Native adapters:** read-only Wale and AgentFlow records; optional local Git and deployment adapters.
- **Normalization:** preserve identities, exact revision/configuration bindings, source timestamps, and unknown states.
- **Evidence evaluator:** conservative deterministic rules, with explicit criteria and scope.
- **View:** static HTML first; integration into an existing Wale or AgentFlow interface after the value is clear.
- **History:** timestamped snapshots first; SQLite when comparing snapshots or retaining change history becomes necessary.

A graph database, vector database, new execution engine, always-on service, and new approval workflow are unnecessary for the first version.

### Why the first artifact is static

A self-contained report is easy to inspect, run locally, and keep private. It demonstrates whether the composition and evidence model answer the operator's questions before a service is built.

The tradeoff is explicit: it is a dated export. It does not refresh itself, receive webhooks, send alerts, manage authentication for a team, or persist a live application session.

### Collection behavior

The Python collector:

- Resolves each configured ref to a full commit SHA.
- Collects open PRs and Actions workflow runs for that SHA.
- Uses pagination with a configured cap.
- Records incomplete, inaccessible, and failed sources explicitly.
- Uses selected workflow identity, a selected event (push by default), and the applicable run/attempt rather than an unrelated recent job.
- Retains timestamps and evidence links.
- Escapes untrusted content in the static report.
- Reads credentials from the local process environment or an explicitly selected existing GitHub CLI session.

GitHub's [workflow-run API](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-repository) supports filtering by `head_sha`, with fine-grained **Actions: read** permission. [Open pull requests](https://docs.github.com/en/rest/pulls/pulls#list-pull-requests) need **Pull requests: read** for private repositories. Ref/commit reads need the appropriate **Contents: read** access. Public endpoint access can be anonymous, subject to [rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).

A private multi-repository installation needs access to each selected repository. A workflow's default repository-scoped token should not be assumed to grant private cross-repository access. Use an appropriately scoped GitHub App or fine-grained token; keep credentials out of reports.

### Integration receipt boundary

The starter's receipt format binds product ID, manifest digest, participating component SHAs, optional repository IDs, capability set, time window, integration environment label, result, and evidence link.

Participating components are required components plus any optional component explicitly used by a declared capability. An optional component displayed for context does not block core-scope receipt matching.

The format is a prototype binding check. It is not a replacement for AgentFlow's native receipt format or Wale's native audit. It does not authenticate the issuer or retrieve underlying evidence. A production adapter must validate the native evidence producer, contract/test configuration, artifacts where relevant, and authority records before making a stronger claim.

## Compare the alternatives

| Approach | Best fit | Strengths | Limitation for this need | Recommendation |
| --- | --- | --- | --- | --- |
| GitHub Projects | Shared planning and visibility into issues/PRs across repositories | Tables, boards, roadmaps, filters, custom fields, direct issue/PR references | Product membership, version compatibility, integration proof, local execution, and deployed state need additional modeling/data | Use where GitHub issues/PRs are already canonical; otherwise link to native tasks rather than migrate them casually |
| Thin product manifest + Python report | A small team or owner needing precise product composition and evidence visibility | Small footprint, local operation, explicit evidence, easy reuse with existing Wale/AgentFlow data | Adapters and evidence definitions are owned by the team; current starter is intentionally narrow | Best first step here |
| Backstage catalog | A larger portfolio or organization needing a maintained developer portal | Components, systems, resources, ownership, API relations and catalog graph | Requires portal setup, entity curation, plugins/adapters, and additional release/evidence logic | Consider when shared catalog and ownership needs justify the operating cost |

GitHub [Projects](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects) offers planning views and custom metadata. Backstage's [catalog model](https://backstage.io/docs/getting-started/viewing-catalog/) and [relations](https://backstage.io/docs/features/software-catalog/well-known-relations/) provide a mature way to represent components and systems. Neither documentation establishes automatic proof that a chosen cross-repository version combination delivers a product capability.

A monorepo may simplify some change and release workflows, but choosing one requires its own analysis of ownership, permissions, shared dependencies, release cadence, and build tooling. A visibility requirement alone does not establish a need to migrate code.

## Implementation order and success checks

### First: composition and published evidence

Use the supplied starter to validate the product membership and selected references. The operator should be able to answer “what is included, what is failing, and what is unknown?” with direct evidence links.

Acceptance cases include missing workflow, failed workflow beside an unrelated successful one, unavailable repository, incomplete pagination, and stale collection. Every case must remain visible.

### Next: existing local execution evidence

Read the existing AgentFlow repository/build/receipt records and optional local Git worktree state. Associate execution with component, revision, native task, and product capability. Reuse native interfaces and schemas discovered from current code.

This should answer “where is the work that has not reached GitHub?” and “which build produced this evidence?”

### Then: selected candidates and integration proof

Add an explicit candidate record and an integration verification path for one real capability. Bind the entire participating version set, accepted test contract/configuration, consuming repository, artifacts where relevant, and evidence origin.

A wrong SHA for one required component must invalidate applicability. Independent passing repository CI without integration evidence must leave product compatibility unverified.

### Finally: deployment and shared-component reuse

Read deployed versions from an authoritative deployment system; add artifact and environment identity. Expand to multiple products and shared components after the one-product model is useful.

Do not report a merge as a deployment or a test pass as human acceptance.

## Measures of usefulness

Prefer a few directly interpretable measures:

- Time needed to identify the component and evidence behind a blocker.
- Required sources successfully collected, with an explicit denominator.
- Age of the last successful observation for each source.
- Selected capabilities with applicable integration evidence, with unknowns counted explicitly.
- Differences between observed heads, the selected candidate, and the deployed version set.
- Local work awaiting publication or integration, when the local adapter exists.
- Time to resolve a mismatch between a claimed status and its evidence.

Commit count and lines changed can describe activity. They should not stand in for product value or completeness.

## Delivery status

Built artifacts and the checks actually executed are recorded in `VERIFICATION.md`. The package supplies a runnable standalone starter and current GitHub observations. Native Wale integration, local AgentFlow ingestion, a deployed service, authenticated integration receipts, and full product acceptance remain future work.

