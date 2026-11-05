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

## Local UI and repository registry revision — November 5, 2026

- Local glass skin, SVG icons, and native WebGL; no new packages or external
  asset requests observed in browser resource entries. Existing CSP retained.
- Live page opens before the first repository scan finishes; pending sources
  have unknown metrics. Completed results stream into the portfolio view.
- Native browser Add repository submission against a disposable Git checkout
  returned a persisted configuration entry, queued collection, and then rendered
  observed history. Repository selection remained stable across refresh.
- Desktop 1440x1000 and mobile 390x844 had no document overflow. Reduced-motion
  emulation was recognized. Browser emitted WebGL ReadPixels performance
  warnings during capture; GPU/battery performance has not been benchmarked.
- Registry tests cover immediate startup, unknown pending metrics, retained
  timestamps, linked-worktree duplicates, metadata preservation, Git-file byte
  preservation, invalid paths, unsafe config location, failed writes, external
  config changes, request bounds, Origin rejection, creation, and retries.
- The 72-checkout live configuration remains outside this repository. Its first
  complete scan is still pending; partial aggregate totals are not complete
  workspace measurements. v0.1.0 is the earlier published release and is not
  changed by this local revision.

## Public repository correction — November 5, 2026

- Kept Local checkout and added Public GitHub repository in the existing form.
- Native browser submission added `https://github.com/octocat/Hello-World`,
  persisted the canonical URL, and observed default branch `master` at
  `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`. The sample's recent-window
  history is zero; its local work is unobserved. This is real anonymous remote
  collection alongside disposable local fixtures, not a hosted deployment.
- A subsequent browser submission using Local checkout succeeded and retained
  the public row. The source selector and modal fit 390px with reduced motion.
- `python3 -B -m unittest -q`: 40 passed. Added URL/credential rejection, config
  round-trip, isolated Git environment, bare-fixture LOC, remote-failure unknowns,
  private/rate-limit response rejection, and interruption for newly queued work.
- Public collection writes only monitor-owned bare caches and is bounded by a
  2,000-commit depth and 30-second Git command timeout. Depth is not a byte or disk
  quota. Initial public fetches require network; shallow totals remain partial.
- Public and local source histories may overlap. This revision does not dedupe
  commit history across independent configured sources or collect public PR/CI
  states. Public GitHub URLs are supported; other remote hosts are not.
- Relevant references: [Git fetch depth](https://git-scm.com/docs/git-fetch),
  [GitHub public repository API](https://docs.github.com/en/rest/repos/repos).
