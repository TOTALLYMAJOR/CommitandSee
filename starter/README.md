# Wale product visibility — runnable Python starter

A local, read-only view of a product assembled from several GitHub repositories.

This starter collects published GitHub evidence, binds each observation to an exact commit, and renders a self-contained HTML report. It includes a proposed Wale product manifest, a report collected from GitHub on November 4, 2026, a synthetic demo, and offline tests.

It is a standalone prototype for a future product view. It has not been integrated into Wale or AgentFlow, deployed, or used to accept a product release.

## Start with the included report

Open `wale-github-visibility.html` in your browser. It contains the real GitHub snapshot collected during this request, with links back to the repositories, selected workflow runs, and open pull requests.

The snapshot is dated. It does not update itself. The generated report assesses freshness at export time; regenerate it to reassess freshness and recollect to obtain current GitHub data.

The separate demo is deliberately synthetic and is labeled as such.

## Requirements

- Python 3.11 or newer.
- No third-party Python packages.
- Network access to `https://api.github.com` for a new live collection.
- A token is optional for public repositories, subject to GitHub's anonymous rate limit. Private repositories require an authorized credential.

## Run on WSL / Linux / macOS

From this extracted directory:

```bash
python3 wale_visibility.py --help
python3 wale_visibility.py demo --output-dir demo
python3 wale_visibility.py collect --manifest product.json --output snapshot.json
python3 wale_visibility.py report --manifest product.json --snapshot snapshot.json --output report.html
python3 -m unittest -v test_wale_visibility.py
```

Open `report.html` locally in a browser. A web server is unnecessary.

## Run on Windows

From PowerShell in the extracted directory:

```powershell
py -3 wale_visibility.py demo --output-dir demo
py -3 wale_visibility.py collect --manifest product.json --output snapshot.json
py -3 wale_visibility.py report --manifest product.json --snapshot snapshot.json --output report.html
Start-Process .\report.html
py -3 -m unittest -v test_wale_visibility.py
```

The same files work in Windows or WSL. Do not copy tokens into the manifest, the report, source control, or a chat.

## Authentication

The collector reads `GH_TOKEN` first, then `GITHUB_TOKEN`, from the process environment. Supply a credential through your normal local secret-management process. If supported by your installed GitHub CLI session, the collector's explicit `--use-gh-auth` option can reuse that session; see `collect --help`.

For a fine-grained token, select only the repositories you want to inspect. The planned endpoints need repository metadata, **Contents: read**, **Pull requests: read**, and **Actions: read**. A recurring team installation should use a read-only GitHub App rather than a broadly scoped personal credential.

The program performs GET requests only. It does not merge PRs, create issues, rerun workflows, publish sites, edit repository files, or execute repository code.

The GitHub connector used to collect the included report is separate from authentication available to a script on your computer. Downloading the package does not transfer that connection or its credentials.

## Configure your product

Edit `product.json`:

- `product.id`: stable identity of the product.
- `membership_status`: `proposed` until you have confirmed the composition; `confirmed` is an operator assertion, not an approval mechanism.
- `components`: component ID, repository, ref, role, required/optional status, selected workflow names, and a workflow event (default: push).
- `dependencies`: declared, typed relationships between components.
- `capabilities`: user-facing capabilities and their component/acceptance-criterion mappings.
- `max_age_hours`: the collection freshness window.

The supplied composition uses Wale and AgentFlow for the proposed “Verify one approved change” journey. Traffic Control Pilot appears as an optional related component. It is not required for the base journey.

`required_workflows` means “selected for this report's CI observation policy.” The starter does not read GitHub branch-protection settings or prove that these are enforced merge requirements.

The optional `workflow_event` field selects the exact event to assess; its default is `push`. The example explicitly selects `push`, so a later manual dispatch cannot hide a failing push run.

Refs can be branches, tags, or full commit SHAs. Branches and tags are resolved to immutable commit SHAs before collecting workflow observations. A collection of branch heads is an observed version set; it is not automatically a selected release candidate.

The current example selects:

| Component | Selected workflow |
| --- | --- |
| Wale | Design Intelligence CI |
| AgentFlow | AgentFlow CI |
| Traffic Control Pilot | Traffic Control CI |

These names were observed in GitHub. A newer successful dependency-update job cannot substitute for a failed selected CI workflow.

## Receipt binding

To inspect a supplied integration receipt:

```bash
python3 wale_visibility.py report --manifest product.json --snapshot snapshot.json --receipt receipt.json --output report.html
```

The demo command supplies a synthetic example of the receipt format. Matching requires the correct product, manifest digest, exact participating component SHAs, capability scope, result, and time window.

The participating set is the union of required components and components referenced by declared capabilities. Optional display-only components outside that set do not prevent matching. If a capability uses the optional governor, include it in that capability and create a distinct candidate/receipt for that scope.

“Matched supplied receipt” means the provided JSON matches those bindings. The starter does not authenticate the producer, fetch the evidence URL, verify an artifact digest, execute integration tests, or prove human acceptance. The receipt is not a native Wale or AgentFlow receipt and grants no authority. A future adapter should consume and independently audit native receipts.

## Data and visibility limits

The first version collects repository metadata, an exact ref resolution, open PRs, and GitHub Actions workflow runs. It preserves source errors and incomplete collection as unknown/partial evidence.

It does not collect:

- Local-only commits, dirty worktrees, or unpushed branches.
- AgentFlow's local database, live run state, or native receipts.
- Existing Markdown/JSON backlog tasks or a GitHub Project.
- External CI providers, required check configurations, or semantic compatibility.
- Deployed versions, artifact digests, production telemetry, customer acceptance, or business outcomes.
- A complete code dependency graph or automatic capability discovery.
- A multi-product shared-component catalog or path-level ownership within a monorepo.

Those are separate adapters described in `SOLUTION.md`. The starter models one component per repository and rejects duplicate repository slugs. It does not yet model multiple components in one repository, a component shared across product records, or path-level change impact.

A fresh collection can contain an old successful run at an unchanged SHA. The report keeps collection freshness separate from when the test ran. Neither implies that runtime dependencies, deployment configuration, or the product environment remain unchanged.

## Verification and provenance

`VERIFICATION.md` records the checks actually run for this package. `github-observation-provenance.json` records the GitHub source URLs, collection timestamps, observed main SHAs, and boundaries for the included real report.

The included live data was fetched through the connected GitHub service, then normalized with this starter using an injected transport. This verifies report generation with real GitHub response data. Direct authenticated HTTP collection from your Windows or WSL machine remains to be exercised in your environment.

The source package includes no token and no full repository clone.

## Recommended next integration

Keep the manifest and viewer as a read-only projection. Reuse Wale's native evidence and authority records, AgentFlow's existing repository/build records and receipts, and whichever backlog is already canonical. Add a local AgentFlow/worktree adapter before building a large hosted dashboard.

See `SOLUTION.md` for the design and `IMPLEMENTATION-PROMPT.md` for a repository-aware handoff.

