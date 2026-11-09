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


## GitHub authorization and repository import — November 6, 2026

This source revision starts from `785f6016e8c68728569edb2e1b67bdd95c79d111`.
The owner selected built-in GitHub App device authorization and a searchable
repository picker. The published `v0.2.0-rc.1` ZIP is unchanged and does not
contain this feature. Public publisher identifiers ship in
`github_app_defaults.json`; credentials stay in memory for the running session.

### Source and boundary regressions

`python3 -B -m unittest -v` ran **145 tests in 27.224 seconds: 141 passed and
four platform-specific tests skipped** on WSL/Linux. This includes 24 auth,
16 authenticated collector, 16 HTTP/import integration, 16 portable launcher,
and one complete offline HTTP/auth/registry flow, together with existing
local/public, storage, metric, UI-backend, and subprocess regressions.

The HTTP flow uses the real local server and auth state machine with an injected
provider. It exercises device authorization, discovery, selected-only import,
duplicate import, disconnect, and restart persistence. Captured responses and
all disposable saved files are checked for synthetic access, refresh, and device
credentials. This fixture does not download a real GitHub repository.

Other regressions cover strict provider endpoints, response limits, device
polling/backoff/expiry, revoked access, serialized refresh, account/generation
barriers, read-only installation grants, discovery truncation, transaction
rollback, stale scan/cache publication, config/cache containment, cache identity,
symlinks/hardlinks/junctions, incomplete caches, and secret-free Git arguments.
An optional cancellation predicate stops an authenticated fetch's process tree
when its account session changes, preserving existing output/lifetime bounds.

Independent review identified and verified corrections for two additional
integration defects: an expired access token was checked before refresh during
automatic collection, and browser session changes could leave stale private
picker data or observations visible. Targeted regressions reproduced the issues
before correction. Independent checks passed five Python cases and three
Chromium session-race cases. This was a bounded review, not an exhaustive
security or hostile-same-user filesystem assessment.

Native Windows collector validation ran **16 tests: 15 passed, one POSIX-only
link test skipped**, including an actual Windows junction fixture, in 26.035
seconds. Native subprocess cancellation passed **9/9**. The earlier full native
launcher run passed **15/15**; the subsequently added bundled-default checks
also passed natively. Native runtime was Python 3.14.3 and Git
2.56.0.windows.2 on Windows 11 Pro for Workstations build 26300.

### Actual GitHub provider evidence

An unauthenticated public GitHub API read verified the owner-supplied
CommitandSee registration, matching App ID `5638377`, Client ID and slug. Its
reported repository permissions were exactly Contents: read and Metadata: read,
with no subscribed events. The live source preview then obtained a real GitHub
device code without logging it. The owner completed authorization and selected
one private repository through the dashboard. Safe status counters subsequently
showed a connected account, one authenticated private source, available history,
and zero repository collection errors.

These observations establish one actual sign-in and selected private-history
collection on the tested source preview. They do not establish every account,
organization policy, live revocation/refresh path, clean-machine compatibility,
or general release acceptance. Repository identity, paths, user/device codes,
and tokens are omitted from the evidence record. Disconnect and removal retain
already-downloaded private Git objects; saved selections persist without tokens.

### Final browser validation

Both browser suites ran sequentially within each engine using
`node --test --test-concurrency=1 test_dashboard_browser.cjs test_github_browser.cjs`.
All **26/26 cases passed in each engine, zero skips**: Chromium in 54.692 seconds,
Firefox in 95.358 seconds, and WebKit in 152.451 seconds (**78 cases total**).
The 27 scoped axe scans (nine per engine) reported no tested violations.

The auth fixtures cover code/cancel/retry states, repository search and selection,
partial imports, stale responses, cross-tab disconnect and failed verification,
keyboard focus, and 500-row picker scrolling at 1440×1000 and 390×844. Requests
use synthetic local API responses; external origins are blocked. No page
exceptions or unexpected console warnings were observed. Known released-context
and software-rendering messages remain separately classified. These checks do
not establish comprehensive accessibility, a native user browser appearance, or
owner visual acceptance.

### GitHub-enabled Windows portable artifact

Final artifact: `CommitandSee-0.3.0-rc.1-Windows-x64-cd56dec4f860.zip`,
**10,980,028 bytes**, SHA-256
`6643544b7ad6338cd2bf4a76d0234e1560589b31f040ab3d30b0b9c97be529c7`.
Its 21-input digest is
`cd56dec4f86016475e222b28172dc0a86c6131f7e6a8d11e87fb823aeef81749`.
All 21 captured inputs matched the final source. The archive has 681 entries,
passed ZIP CRC validation, and contains no settings, observation-state, or
SQLite entries. BUILD-INFO records Python 3.14.3, PyInstaller 6.22.3, and
tzdata 2026.6 on the native Windows host identified above.

The extracted final ZIP passed empty onboarding, local repository addition,
observation of a fixture commit, restart persistence, removal, and another
restart. Python was absent from the launched executable's PATH. Checkout/Git
bytes and extracted bundle bytes were unchanged by the smoke workflow.

Bundled public defaults configured GitHub without environment overrides. The
installation URL and locally served setup guide were verified. The actual
provider issued a device code, cancellation returned to disconnected state,
shutdown stopped a second pending authorization, and restart began without a
session. An explicit empty configuration override correctly disabled the
defaults. Device codes and tokens were not logged; checked saved settings and
logs contained none of the issued code values.

Ctrl+Break during a stalled Git command with a child exited the launcher with
code zero and stopped both processes in **2.428 seconds**, before the command
timeout. An initial probe used the wrong extracted executable path and failed
before app startup; the corrected invocation produced the recorded passing
result. No host PowerShell execution policy was changed.

The native check did not complete user authorization or collect actual private
GitHub history; that proof belongs to the separate source-preview flow above.
Native browser appearance, clean-machine compatibility, SmartScreen reputation,
signed-installer behavior, and complete accessibility remain unqualified. This
is an unsigned prerelease, with Git for Windows still required.

## Chart selection and insights source verification — 2026-11-06

The source preview on feature/chart-pr-drilldown was checked in Ubuntu-24.04
WSL, with browser tests running in native Windows Chromium. The checks cover
the selection panel, pointer and keyboard zoom, touch interaction, preceding
equal-duration comparisons, and on-demand PR grouping.

- The Python unittest suite ran 148 tests with 144 passes and four skips.
  The skipped checks require native Windows behavior.
- The dashboard and GitHub browser suites ran 37 tests with 35 passes and
  two optional axe-core skips, using Node's test runner with concurrency 1.
- Regression fixtures cover a 125,000-line spike, repeated daylight-saving
  hours, mouse and touch drag, keyboard range selection, reset and refresh,
  complete and partial baselines, a zero baseline, older snapshots, static
  reports, shared and ambiguous PRs, provider failures, bounded 20-commit
  batches, in-memory caching, and stale responses after repository changes.
- The live local preview reconciled 12 captured commits with 16,493 additions.
  Its three largest addition contributors accounted for 70.8% of additions.
  Desktop and 390-pixel mobile rendering were visually inspected. The mobile
  document had zero horizontal overflow and the live browser check reported
  zero page errors.
- The bundled demo was regenerated. The source checksum manifest was
  regenerated and checked, and Git's diff whitespace check passed.

PR grouping was exercised with controlled provider responses. The prior
commit-to-PR endpoint smoke check also resolved a real public GitHub commit.
Private installation permission changes and a new Windows portable build
are outside this source-preview verification.

### Commit preparation recheck — 2026-11-07

The unchanged implementation passed the Python suite again with 144 passes and
four Windows-specific skips. In the full Chromium run, one GitHub sign-in
fixture exceeded the existing 10-second page-load timeout before its assertions.
The dashboard suite passed all 22 enabled tests. Rerunning the complete GitHub
browser suite passed all 13 enabled tests. Two optional axe-core tests were
skipped across the browser suites. No timeout settings or application behavior
were changed for the rerun.

Windows Git fetched the remote after WSL DNS failed. The remote main tip still
matched the feature branch's base. The final checksum and diff checks passed.

## Windows chart-insights release verification - 2026-11-08

The v0.4.0-rc.1 candidate packages the chart features merged in PR #6. Release
changes update the package version and documentation and repair two native test
fixtures; application runtime code is unchanged from the merged feature tree.

Final artifact: `CommitandSee-0.4.0-rc.1-Windows-x64-7e04f096605e.zip`,
**11,232,100 bytes**, SHA-256
`b19a252445b36b3dc4eac56d79bc1714f71ca28f6c5c9937da2d139bdc9b1f89`.
The 21-input digest is
`7e04f096605e8045add66205c1b6fdb8342ca00e808bedba43b79c8045a9277e`.
All 21 source input hashes matched the final checkout. All 685 ZIP entries
passed CRC validation; no configuration, observation-state, SQLite, or Git
metadata files were included.

The build used isolated native Windows x64 Python 3.14.3 from the CPython NuGet
distribution, PyInstaller 6.22.3, and tzdata 2026.6. An initial attempt using the
host's split Python 3.13 installation stopped at the required-license check and
produced no ZIP. The final build used a complete distribution inside build
scratch space, with no global Python installation or execution-policy changes.

Validation performed:

- `python -B -m unittest discover -v` under the isolated native build environment:
  148 tests run in 175.074 seconds, zero failures/errors, 13 skip reports for
  POSIX fixtures, Windows-invalid filenames, or unavailable symlink privileges.
  Native subprocess containment and binary input/output checks passed. The first
  host-Python attempt exposed a Linux-only null-device expectation and unclosed
  SQLite fixture connections; those fixtures were corrected. The host Python
  warning also polluted a subprocess stderr assertion; the complete build
  environment resolved that issue. No runtime behavior was changed.
- WSL regression recheck of `test_public_repositories test_registry_regressions`:
  30 tests passed after the fixture corrections.
- `node --test --test-concurrency=1 test_dashboard_browser.cjs test_github_browser.cjs`
  using native full Chromium: 37 cases, 35 passes, two optional axe-core skips,
  zero failures. These use controlled provider responses.
- `packaging/smoke_portable.py --github-checks --github-device-probe` against the
  extracted final ZIP: empty onboarding, HTTP HTML/JSON, bundled timezone data,
  repository add/remove and restart persistence, and graceful Ctrl+Break exit
  passed with Python absent from the child PATH. Fixture checkout and extracted
  bundle bytes were unchanged. Bundled GitHub settings and setup guide worked;
  actual device-code issuance, cancellation, shutdown while pending, and an
  explicitly disabled publisher override passed. Issued codes were not written
  to the checked settings or logs.
- `packaging/smoke_shutdown.py` against the extracted executable: the launcher,
  a stalled Git command, and its child stopped in 2.393 seconds after Ctrl+Break,
  before the 30-second command timeout.
- Additional browser checks against the actual frozen server reconciled three
  disposable fixture commits, opened a chart point's commit details, exercised
  keyboard range zoom/reset and hour/15-minute controls, and found zero page or
  console errors. Desktop 1440-pixel and mobile 390-pixel captures were inspected;
  the mobile document had no horizontal overflow. This did not inspect the
  user's default browser window or complete a private GitHub login.

The publisher's public GitHub App metadata still reported only `contents: read`
and `metadata: read` during this release check. Private commit-to-PR lookup is
implemented and fixture-tested but remains unverified against a real private
installation. It needs `pull_requests: read`, installation-owner acceptance,
and a fresh signed-in end-to-end test. Device-code issuance alone does not
establish user authorization or private access.

This remains an unsigned prerelease requiring Git for Windows. Clean-machine
compatibility, SmartScreen reputation, signed installation, full accessibility,
and real private PR access are not qualified by these checks.

## Local change insights - 0.5.0-rc.1 candidate (2026-11-09)

This change adds on-demand content comparison and bounded saved-file-version
lookup for registered local repositories. The candidate is built and checked
locally; it is not a published release and does not replace the 0.4.0 download.

Final WSL `python3 -B -m unittest discover -v`: **183 tests run, 4 platform
skips, zero failures/errors**, in 36.418 seconds. The engine has 25 focused
regressions, and the HTTP/registration integration has 9. Coverage includes
squash/cherry-pick content adoption, partial overlap, ambiguity, mode changes,
working versus staged versions, stash staged/untracked snapshots, reflog
recovery evidence, truncation, shallow history, sparse files, exclusions,
unsafe paths, cancellation, concurrency, and stale results.

Final native Windows run of the same full suite: **183 tests run, 16 platform
skips, zero failures/errors**, in 235.533 seconds, using the isolated Python
3.14.3 build environment. Skips cover POSIX-only fixtures, Windows-invalid
filenames, and unavailable symlink privileges; native subprocess containment
and the inherited-trace regressions passed.

The combined Chromium browser run exercised **49 cases: 47 passes, 2 optional
axe-core skips, zero failures**, in 67.662 seconds. Twelve new cases cover
inspection controls, mixed results, missing options, errors, source removal,
late responses, changed identities, escaped filenames, mobile layout, and
export exclusion. An existing chart comparison fixture now waits for each
asynchronous refresh before checking results.

Independent review reproduced and verified fixes for a POSIX ancestor symlink
race, an omitted stash index snapshot, expired reflog evidence during a scan,
capability preflight outside the scan budget, and inherited Git trace-file
writes. A separate 56-test review run passed, with additional adversarial
fixtures checking both scanner entry points. The shared observer trace
regression failed on the pre-fix implementation and passed after Git trace
environment variables were removed. Fixture file hashes and modes remained
unchanged in the fixed scanner tests. This is evidence from the tested cases,
not a general hostile-code sandbox proof.

The local Windows x64 artifact is
`CommitandSee-0.5.0-rc.1-Windows-x64-5f3b9dd1c459.zip`, **11,262,611 bytes**,
SHA-256 `a220a882aae08c1ab3c8d72046cc736bb95f2dce11310f5d050696c51de85f65`.
All **22 source-input hashes** match the checkout; all **685 ZIP entries** pass
CRC validation. No checked configuration, observation-state, SQLite, or Git
metadata paths were included. Build environment: isolated native Windows
Python 3.14.3, PyInstaller 6.22.3, tzdata 2026.6. No global installation or
execution-policy changes were made.

The extracted candidate passed `packaging/smoke_portable.py --github-checks`:
empty onboarding, HTTP HTML/JSON, bundled timezone data, add/remove persistence
across restarts, and graceful Ctrl+Break exit, with Python absent from its child
PATH. Repository and extracted-bundle bytes were unchanged. Bundled GitHub
settings, setup guide, cleared session state, and disabled-publisher override
passed; this run did not request device authorization or verify private access.

Browser checks against both source and the actual extracted executable used a
disposable repository. They verified partial adoption and remaining changes,
exact saved-version detection, distinct staged and working contents, and
qualified missing-match results. Repository and Git metadata bytes remained
unchanged. Desktop 1440px and mobile 390px captures were inspected; no horizontal
mobile overflow or browser page/console errors were observed.

Limits: inspection is textual evidence, not semantic equivalence, backup
verification, or a safe-delete recommendation. Saved-copy checks cover bounded
local states only, and cached refs may be stale. CPU deadlines are cooperative:
the reviewer measured about one second for a worst-case bounded text comparison,
so the nominal 18-second budget is not a strict real-time guarantee. Privileged
Windows symlink/reparse races were not independently exercised; those platform
fixtures remain skipped. Clean-machine compatibility, signing, SmartScreen,
full accessibility, and real private GitHub PR lookup remain unqualified.
