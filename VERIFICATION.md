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

## Five review fixes and repository removal — November 5, 2026

Changes are based on `56d1eb05310df1a83e1d0d7d5779c8f812762d21`. The owner
authorized the five reproduced fixes and selected repository removal only.
No OAuth integration, deployment, or publication was performed.

- `python3 -B -m unittest -v`: **55 tests passed in 13.850 seconds** in the
  final full run with loopback socket access. Tests use disposable Git checkouts,
  offline helpers, and mocked public responses, not the owner's monitored data.
- Added twelve backend regressions for linked-worktree containment, local/public
  calendar rollover (including UTC fallback), persisted removal, aliases,
  CLI-controlled sources, public cache preservation, failed writes, request
  validation, external config edits during identity checks, and stale scan results.
  Containment, calendar rollover, and the external-config race failed before their
  corrections and passed afterward.
- Added three actual-process cancellation regressions. Timeout, output overflow,
  and an exited parent retaining descendant pipes all failed on the baseline and
  passed after correction. The offline Git fetch reproduction stopped its helper
  after the fix, with no network requests. This establishes ordinary POSIX process
  group cleanup; deliberately detached hostile processes are outside that proof.
- `test_dashboard_browser.cjs`: six Chromium regression cases cover retained
  chart/date and worktree disclosure focus, pending add success/failure after
  reopening, removal cancel/failure/success, selection fallback, read-only rows,
  and a stale snapshot arriving after removal. The two reviewed UI failures were
  reproduced before correction. The browser fixture intercepts HTTP responses.
- A separate actual loopback-server browser check removed a selected disposable
  repository, restarted the collector, and confirmed it stayed absent. The other
  repository and custom config metadata remained. Before/after digests verified
  that both fixtures' checkout and Git files were unchanged. Cancellation left
  the repository present. Desktop 1440x1000 and mobile 390x844 were inspected with
  no document overflow or page exceptions. Reduced motion was enabled.

The Browser plugin was not available; the existing local Playwright/Chromium
installation was used, without adding dependencies. Software-WebGL fallback and
ReadPixels warnings appeared during capture; no GPU/battery benchmark was run.
Native Windows remains unverified: its taskkill tree fallback is best effort and
does not establish cleanup after an already-exited parent. No cross-browser or
comprehensive accessibility audit, live GitHub download, or owner acceptance is
claimed. Saved configuration still has a narrow external-writer check-to-replace
interval; lengthy Git checks no longer enlarge it. Removal retains files, caches,
and observation history rather than acting as disk cleanup.

## Follow-up hardening and discovery — November 5, 2026

This section supersedes the configuration-write and Windows cancellation gaps
above for the tested working candidate. Earlier results remain historical.

- `python3 -B -m unittest -v`: **68 tests run, 65 passed and three Windows-only
  tests skipped**, in 19.626 seconds on WSL/Linux. This run precedes the portable
  launcher addition. Fixtures are disposable and public responses are mocked.
- The dashboard now leaves base JSON byte-exact and stores UI changes in an
  application-owned SQLite sidecar. Regression coverage includes independently
  running observer processes, restart merging, removal overrides, transaction
  rollback, unrelated database rejection, and linked artifact rejection.
  Independent review also injected an external edit after the final config
  guard and a database-path symlink swap before SQLite opened it: the base JSON
  and protected target were unchanged. These bounded probes are not an
  exhaustive hostile-filesystem proof.
- The actual loopback browser flow removed a selected disposable repository,
  restarted, and confirmed it stayed absent. Both checkouts and Git directories,
  the base JSON bytes, and unrelated metadata were preserved. The Chromium
  run reported no page exceptions or console warnings.
- Native Windows subprocess suite: **8/8 passed in 16.726 seconds** on Windows
  11 Pro for Workstations 64-bit (10.0.26300, build 26300), Python 3.14.3 and
  Git 2.56.0.windows.2. The tests exercised timeout, output overflow, an exited
  parent with live descendants, reader startup failure, rejected job admission,
  controller termination before resume and after startup, binary stdin, Unicode
  arguments/environment, and exit-code preservation. They used temporary
  repositories and offline helper processes, not real project repositories.
- Windows processes join a kill-on-close Job Object at process creation using
  `PROC_THREAD_ATTRIBUTE_JOB_LIST` and an explicit inherited-handle list. This
  requires Windows 10 / Server 2016 or later. POSIX retains process-group cleanup;
  deliberately detached hostile POSIX children are outside the established proof.
- PR #2's README checksum was corrected; all 21 manifest entries and nine local
  README links passed in an isolated checkout before merge. The PR was merged
  at `21fe062f98682e01fc62d71d4228822f7793dce3`. No CI checks were reported on
  that documentation PR. The description and five requested GitHub topics were
  applied and read back. These actions do not establish discovery or star growth.
- The owner selected MIT and a product-first social preview. Contributor guidance
  and release notes were added. Preview production and portable packaging have
  separate validation below when available; they are not implied by these tests.

Final browser suite: **12/12 passed in each engine, zero skips**: Chromium
151.0.7922.34 (17.923 seconds), Firefox 153.0 (37.134 seconds), and WebKit 26.5
(39.073 seconds). The 36 cases include keyboard tabs/dialog boundaries, retained
chart/disclosure state, disappearing worktrees, empty/error states, narrow
viewports, reduced motion, background visibility, and renderer fallback. Nine
axe-core scans (desktop, mobile, dialog across three engines) returned no tested
WCAG A/AA rule violations. This is bounded automated coverage, not comprehensive
accessibility conformance. Synthetic HTTP 409/503 errors and known released-context
or software-rendering messages were explicitly distinguished from unexpected
console errors. No page exceptions or document overflow were observed.

The social-preview PNG is rendered from HTML/CSS and the bundled synthetic demo,
with HTTP(S) requests blocked. The renderer verified 1280×640 and under 1 MB;
the final image was inspected for headline, demo labeling, and chart visibility.
Inherited heading colors were made explicit and preview-frame padding corrected;
the final deterministic design scan returned no findings. No suppressions were
added. The image is ready for manual GitHub Settings upload; available tools did
not provide a supported settings-image upload capability.

Native Windows end-to-end collection, hardware GPU/battery performance, complete
accessibility conformance, and human acceptance are not established by the checks
above. The earlier published v0.1.0 release has not been rewritten.

## Portable candidate validation — November 5, 2026

Final integrated source suite after launcher and path-separation fixes:
`python3 -B -m unittest -v` ran **82 tests in 16.694 seconds: 79 passed, three
Windows-only tests skipped** on WSL/Linux. The separate native Windows cancellation
suite above covers those platform-specific paths. Eleven launcher cases exercise
saved-data defaults, empty first run, Git detection, readiness before browser
launch, startup/error handling, and path separation. A newly reproduced config/state
collision was fixed in both entrypoints. Independent exact-path, symlink, and
hardlink probes all rejected the destination before startup and preserved bytes.

The final configuration-race regression injects an external JSON edit immediately
after the actual final transaction guard, allows the SQLite transaction to commit,
and confirms both the external JSON and UI addition survive restart.

Native portable artifact:
`CommitandSee-0.2.0-rc.1-Windows-x64-929746ee8170.zip`, **10,818,799 bytes**,
SHA-256 `2a2a57407bd1c55e13947d29e71fad0bb08a6823d7c1a271e374259952b409da`.
PyInstaller 6.22.3 and tzdata 2026.6 were installed only in an isolated temporary
native Windows build environment. Bundled input digest:
`929746ee8170ff7055d608c6cc91428eee4d393af134d0c32bcf98db3906402c`.
The archive contains 676 files, including Python and required third-party
licenses. The build allowlist excludes private configuration, registry, state,
Git metadata, and public caches. Final source inputs matched the built snapshot.

The extracted ZIP passed native Windows HTTP HTML/JSON, empty onboarding,
timezone loading, local repository addition, observation of an actual fixture
commit, restart persistence, removal, and a second restart. Python was absent
from the executable's PATH. Checkout/Git bytes and extracted bundle bytes stayed
unchanged. Ctrl+Break during a stalled Git process with a child exited the
launcher successfully and stopped both processes in **2.426 seconds**, before
the 30-second command timeout. Fixtures and probe launchers were stopped.

A real default-browser request ran after readiness. The browser connector was
disconnected, so the resulting native browser window was not inspected. The
earlier cross-engine UI tests establish separate browser-fixture evidence.
This is an unsigned candidate tested on the stated Windows host, not clean-machine,
SmartScreen, signed-installer, or comprehensive platform qualification. Git for
Windows remains required; Python is bundled. The host blocked the unsigned
PowerShell wrapper from a UNC path; native Python completed the same build with
no execution-policy changes. The wrapper passed the native PowerShell parser.

Codebase Memory generation `2026-11-06T01:39:21Z` matches the physical checkout
and current metadata for the reviewed runtime and regression paths. Recipe
coverage remains `GRAPH_COVERAGE_BLOCKED` for PowerShell line 19 (partial parser
coverage) and the PyInstaller spec (not tracked by the graph). The recipe and
new smoke harnesses use bounded `DIRECT_SOURCE_VERIFIED` inspection and actual
native execution instead. This is not an exhaustive graph-impact claim.
