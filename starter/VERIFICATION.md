# Verification record

**Verified:** November 4, 2026, during this request.  
**Runtime:** Python 3.12.14 on Linux.  
**Package:** standalone Wale product visibility prototype.

## Checks actually executed

| Check | Result |
| --- | --- |
| `python3 -m unittest -v test_wale_visibility.py` | 43 tests passed; zero failures or errors |
| `python3 wale_visibility.py demo --output-dir demo` | Synthetic manifest, snapshot, receipt, and static HTML generated |
| `python3 wale_visibility.py report --manifest product.json --snapshot github-snapshot.json --output wale-github-visibility.html` | Real-data static report generated successfully |
| `python3 -m py_compile wale_visibility.py test_wale_visibility.py` | Exit 0 |
| Real GitHub connector response replay through `collect_snapshot` | 12 endpoint responses normalized; all requested source collections complete |
| CI interpretation assertions against real responses | Wale NOT PASSING; AgentFlow PASSING OBSERVED; Traffic Control PASSING OBSERVED |
| Integration evidence assertion against real snapshot | UNKNOWN; no integration receipt supplied |
| GitHub main-ref recheck before report finalization | All three heads unchanged from the initial collection |

The test output is preserved in `test-results.txt`.

## Important failure cases covered

- Empty or unselected workflow data cannot become passing.
- The selected workflow must match the exact commit and selected event.
- A newer unrelated success cannot hide selected CI failure.
- A later manual dispatch cannot hide a failed selected push run.
- A failed newer attempt or a pending newer run supersedes an older successful result.
- Skipped, cancelled, and neutral conclusions do not become success.
- Future-dated execution, stale observations, partial pagination, inaccessible sources, and GitHub's filtered 1,000-run ceiling remain visible.
- Receipt bindings must match product, manifest/criteria, exact acceptance-scope component set, SHAs, capability scope, and dates.
- An unused optional component outside acceptance scope does not block matching.
- Contradictory source state cannot support a positive receipt or complete PR total.
- Duplicate repository slugs are rejected to prevent double-counting in this version.
- Script-like text is escaped and unsafe URL schemes do not become links.
- Credentials and underlying HTTP response bodies do not leak through tested error paths.
- A snapshot cannot be relabeled after editing its manifest.

An independent review identified the workflow-event, source-state, future-date, duplicate-repository, and malformed-enum cases. The implementation agent reproduced these with failing tests before fixing them. The parent reran the final 43-test suite and independently asserted the real-data interpretation.

## Real-data collection method

The authenticated GitHub connector fetched the repository metadata, main commit, open pull requests, and exact-SHA workflow runs. These actual response bodies were supplied to the Python collector through its injectable transport. The normalized snapshot and its source provenance are included.

This exercised normalization and report behavior with real GitHub data. It did **not** exercise a direct authenticated HTTP request from the standalone Python process. The fixed-origin HTTP transport was tested with offline fakes. The user must exercise that connection in their Windows or WSL environment using its authorized credentials.

Source queries occurred over an interval. The main SHAs were reread before finalization and were unchanged; this remains a collected version set rather than an atomic product release. Timestamps in the machine-readable files are UTC ISO 8601. User-facing local date is November 4, 2026 in America/Chicago.

## Not established by these checks

- Native Wale or AgentFlow integration.
- Execution of the repositories' native test suites.
- Cause or repair of Wale's failed CI.
- Authenticity/content of a supplied integration receipt.
- Cross-repository compatibility or product acceptance.
- Production deployment, customer usage, or business outcomes.
- Direct live transport behavior on Windows/WSL.
- A rendered browser screenshot or visual accessibility audit.

No GitHub repository file, branch, issue, pull request, workflow, deployment, or existing tracker was changed.

## Prototype provenance

Code Tytor: Python was used to initialize a CLI project scaffold. Its returned structure contained no implementation source. The runnable code in this package was then implemented and tested in the working environment; the scaffold response was not treated as working software.

