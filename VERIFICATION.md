# Release verification — v0.1.0

Recorded November 5, 2026, in WSL/Linux with Python 3.12.3 and Git 2.43.0.
This record concerns local validation, not CI, deployment, or human acceptance.

## Automated checks

`python3 -B -m unittest -v test_review_regressions.py test_git_metrics.py test_dashboard.py`
passed all **26 tests** in 3.302 seconds after the review fixes. The original
21 tests had passed independently; the added five tests reproduced failures on
unchanged baseline `1c3f931` before passing with the fixes. No project test suites
or hosted services were executed. See [review comparison](docs/REVIEW-COMPARISON.md).

Covered cases include root commits and exact text churn, timezone buckets,
selected refs, merge exclusion, cached-upstream divergence and missing upstreams,
staged/unstaged cancellation, binary and untracked files, rename/newline paths,
linked worktrees, shared stashes, shallow history, truncation, unborn repositories,
invalid refs, metric exclusions, persistence/restart and observation gaps, HTML
escaping, common-directory deduplication, loopback HTTP routes, and partial caches.
Executable fsmonitor, clean-filter and nested submodule-filter fixtures establish
bounded read-behavior checks. They do not establish a general hostile-code sandbox.

## Live workspace validation

The owner supplied `git-dashboard-quickstart.md` from Windows Downloads as the
live-data guide. Its documented SportPilot and Wale paths were verified locally
and configured outside the repository in a private monitor-owned configuration.
The AgentFlow placeholder was not treated as a real path.

Observed repository revisions during configuration:

| Repository | Local revision | Registered worktrees captured |
| --- | --- | --- |
| SportPilot | `b8e5c823122d9db39f744a860fd012f34f8dcd10` | 4 |
| Wale | `3d3bdc5b40b219ebb2fca27fa86b6795e80ac56d` | 11 |

A measured collection took 6.829 seconds. This is one portfolio observation,
not a refresh-time guarantee. Both selected histories were available. SportPilot
had partial worktree coverage because `/tmp/sportpilot-acceptance-b8e5c823` was
missing or inaccessible. That registration remains visible as unknown rather
than being removed or counted as clean. Wale's requested sources reported `ok`.
Remote comparisons remain cached local observations; no fetch or PR lookup occurred.

The live portfolio page was inspected in Chrome: charts, filters, repository
rows, lower-bound counters, and the inaccessible worktree were visible, with
no console errors or warnings on the live page. This is a functional/visual
inspection, not a comprehensive accessibility audit or owner visual acceptance.
The README image is a dated browser capture of this live view.

## Preservation and provenance

The replacement was imported from `git-activity-dashboard.zip`, SHA-256
`439e0d360ee0f6110e378633286db6b674fb9827adbdbab8c5bfe274ba8104a7`.
All 11 original manifest entries matched before README and release-documentation
edits. Dashboard HTML and demo data were retained from that archive. Runtime Python
now includes the five reviewed corrections described in the comparison. The
release checksum manifest is regenerated for the final package.

The preceding implementation remains in Git history at
`4b4b2842235df4ad6d72427ec03442a939657189` and the local preservation branch
`preserve/pre-dashboard-20261105T173325Z`. Local configuration, observation
history, logs, backups, and screenshots unrelated to the README are not release
inputs. The included `test-results.txt` is the supplied package's historical test
transcript; the current result is recorded above.

## Remaining boundaries

Native Windows execution, authenticated GitHub transport, authoritative PR/merge
status, deployments, native Wale/AgentFlow task integration, notifications, and
production readiness are not established. No background system service is
installed. This release provides a local dashboard while its process runs.
