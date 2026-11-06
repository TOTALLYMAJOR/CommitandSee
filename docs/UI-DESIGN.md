# Live dashboard UI direction

Owner selected November 5, 2026: the supplied black/navy glass dashboard,
emerald and indigo accents, six metrics, paired charts, repository table, review
tabs, and animated topographic background. The follow-up technology choice was
local CSS, inline SVG icons, and native WebGL. No CDN or new packages.

The existing collector schema, safe text rendering, independent evidence states,
accessible native selects, keyboard charts, tables, exports, and CSP are retained.
The background is decorative: reduced motion draws a static frame; hidden tabs
pause animation. Rendering is capped at approximately 30 frames/second, DPR 1.5,
and two million pixels. CSS supplies a fallback, including when a software
renderer is reported. Battery/GPU cost is unmeasured; earlier browser captures
produced WebGL ReadPixels performance warnings.

The added local repository dialog accepts an existing absolute checkout path,
optional display name, and product. Same-origin loopback POST writes only the
application-owned registry beside the fixed dashboard configuration, outside
monitored repositories. The base JSON remains unchanged. It validates Git
identity, rejects shared common-directory duplicates, preserves unrelated config
fields, and rejects externally changed config. It does not clone or fetch.
Static reports cannot add repositories. WSL users enter Linux or /mnt/c paths.

First implemented proof: actual live portfolio captured at 1440x1000 and mobile
390x844, no page overflow or external asset requests observed. Native browser
form submission inserted a disposable Git fixture, persisted it, and subsequently
showed an observed row. Repository filtering survived automatic refresh. This is
local implementation evidence, not owner visual acceptance or release proof.

The portfolio configuration selected 72 source checkouts using locally available
commits since November 5, 2025; linked worktrees were deduplicated. Independent
clones remain separate and can share history. This is not a GitHub updatedAt
query. Discovery exclusions and failures are retained in the private local
repository-discovery-12-months.json report, outside version control. Full scan
cost, especially Windows-mounted checkouts, remains an operational limitation.

## Owner correction: keep local, allow public

The owner clarified that repository insertion must also accept public remote
repositories. The existing local option remains. The same dialog now defaults
to Public GitHub repository and offers Local checkout. No visual direction was
reopened. Published default-branch history comes from an anonymous, isolated bare
Git cache outside monitored worktrees. Local work, unpublished commits, stashes,
PRs and CI remain explicitly unobserved for a public-only source.

First real public proof: browser submission of octocat/Hello-World persisted its
canonical URL and collected default branch master at
7fd1a60b01f91b314f59955a4e4d4e80d8edf11d alongside the existing local fixture.
This public sample has no commits in the selected recent window; the observed
zero history count is distinct from its unavailable local-work counts.

## Review fixes and repository removal — November 5, 2026

OWNER INTENT: fix the five reproduced review defects and add repository removal.
The owner selected removal only; GitHub sign-in/import is outside this change.
The existing visual direction and local CSS, SVG, and native WebGL technology
remain selected. No new runtime package, account, paid service, or external asset
is required.

AGENT INFERENCE: use the existing repository table for a Remove action with a
confirmation naming the source. Removing a row stops monitoring and records
removal overrides in the companion registry; it does not delete checkout files, observation
history, or public caches. Combined linked-worktree aliases are removed together.
Sources also passed with --repo remain controlled by the launch command.
AGENT ADDITION: none.

The registry transaction must succeed before removal is shown as complete.
Failed writes retain the row; a completed in-flight scan must not restore it.
Removing the selected repository returns filtering to the remaining selection.
Automatic refresh must preserve chart keyboard focus and selected dates, plus
expanded changed-path details. A delayed add response must not erase input in a
subsequently reopened form.

First implemented proof: a disposable local repository was removed through the
live page and remained absent after collector restart. The remaining repository,
unrelated configuration metadata, and both fixtures' checkout and Git bytes were
preserved. Desktop 1440x1000 and mobile 390x844 captures showed the retained row
and Remove control without document overflow. Browser regressions cover refresh
interaction continuity and delayed form completion. See VERIFICATION.md for the
execution boundaries; this is local validation, not owner visual acceptance.

Follow-up accessibility refinements preserve this direction: chart containers
are named groups around their keyboard sliders; review panels accept keyboard
focus; a disappearing worktree returns focus to its review panel; the repository
dialog wraps keyboard focus at its boundaries. Automated checks cover desktop,
mobile, and dialog states, with manual keyboard assertions in the browser suite.

## Social preview — owner direction selected November 5, 2026

OWNER INTENT: a product-first GitHub sharing image, with the CommitandSee name,
a short headline, and a labeled demo dashboard crop. Retain the existing dark
and emerald identity. This is repository presentation, not an app redesign.
AGENT INFERENCE: make the name and core promise readable at sharing-card size;
use the bundled synthetic demo so no private workspace data enters the asset.
AGENT ADDITION: none. The owner selected reproducible local HTML/CSS composition
with an actual demo screenshot. The final 1280×640 PNG shows the headline beside
the actual metrics and charts, with an uncut synthetic-data label. The renderer
blocks network requests. The PNG and source are in docs/images/social-preview.png
and docs/social-preview.html; rendering is implementation proof, not owner visual
acceptance or evidence that GitHub Settings has been updated.

## Portable startup — owner request November 5, 2026

The owner requested an installer or portable ZIP that opens the dashboard in a
browser and named PyInstaller as a bundling option. The implementation uses a
Windows-specific one-folder ZIP: Python is bundled, Git is checked as a prerequisite,
saved data is outside the extracted program, and the existing dashboard handles
repository setup. The console remains visible for errors and Ctrl+C shutdown.
This is a startup/distribution addition within the existing app direction; no
new app skin, installed service, or automatic updater is introduced. Native
executable validation is recorded separately in VERIFICATION.md.

## GitHub repository picker — owner selections November 5, 2026

OWNER INTENT: connect a GitHub account, search the repositories it can access,
select repositories, then add only that selection. The owner selected the
searchable picker first and built-in read-only GitHub App device authorization
second. This later authorization opens GitHub sign-in and private-history import;
it supersedes the earlier removal-only exclusion for this feature. It does not
change the selected glass skin, native controls, CSS/SVG/WebGL technology,
existing charts, local-checkout flow, or manual public-URL flow.

AGENT INFERENCE: a **Connect GitHub** control opens a **GitHub repositories**
dialog. **Sign in with GitHub** displays a code and a link to GitHub; credentials
are entered on GitHub, not in the dashboard. After authorization, a searchable
checkbox list and **Add selected** action allow deliberate source selection.
Signing in and discovering repositories do not automatically register or fetch
all of them. AGENT ADDITION: none.

| State | User-visible behavior and relationship |
| --- | --- |
| Publisher setup absent or invalid | Explain the missing configuration and link the setup guide; ordinary users use the bundled registration, and local/public repository controls remain usable |
| Signed out | Offer sign-in and explain that credentials last for the app session |
| Device authorization pending | Show the code and GitHub link with pending feedback and cancellation; keep the dialog usable by keyboard |
| Expired or declined authorization | Explain the result and offer a fresh sign-in |
| Signed in, loading repositories | Show a genuine loading state without invented repository results |
| No accessible repositories | Explain app installation, repository selection, and possible organization approval; offer **Configure repository access on GitHub** and **Refresh list** |
| Repositories available | Search by repository name, select explicit rows, and add only the selected sources; preserve failed additions for correction |
| Added | Persist non-secret source choices in the companion registry and show queued collection in the existing repository table |
| Disconnected or app exited | Forget session credentials; keep saved choices and mark authenticated sources **Sign in required** rather than clean or zero |

The GitHub App requests Contents and Metadata read access only, supports
installation on any account, and uses device authorization without an embedded
client secret or private key. User authorization and repository installation
grants are separate. Organization approval is external and must not be presented
as complete merely because the user is signed in. The owner supplied the official
CommitandSee registration, which is bundled as public defaults; ordinary users
do not enter Client IDs or register an app. Publisher overrides use
`github_app.client_id` and `github_app.app_slug`, with environment overrides
documented in [GITHUB-APP-SETUP.md](GITHUB-APP-SETUP.md).

Access and refresh tokens are memory-only and forgotten on disconnect or process
exit. Closing the browser tab does not end the process. Saved selections survive
restart. Disconnect clears the app's collected authenticated results, but it
does not delete downloaded private Git objects; removal also retains caches.
Explicit cache deletion after stopping the app is a separate user action.
Private source metadata and exports must not be treated as public sample data.

Remote **GitHub repository** rows provide published default-branch history,
including authorized private history. They cannot establish local changes,
stashes, unpublished commits, PR state, or CI. Local sources remain necessary for
local-work visibility. Keyboard focus, status announcements, narrow layouts,
reduced motion, cancellation, expired authorization, empty access, access failure,
and partial add results must remain usable within the existing direction.

First local integration proof: an actual loopback HTTP flow using the auth core
and a stub provider completed authorization, selected import, disconnect, and
restart in 0.579 seconds. Credentials were absent from responses and saved files.
This is local fixture evidence, not GitHub authorization. A separate public API
read matched the owner-supplied CommitandSee registration, Client ID, slug, and
read-only Contents/Metadata permissions with no subscribed events.

First provider-backed proof: the owner completed GitHub device authorization in
an isolated local source preview, selected one private repository through the
picker, and observed its collected history. Safe HTTP counters confirmed a
connected session, one authenticated repository, one private repository, history
available for that repository, and zero collection errors. This record excludes
the account identity, repository name/path, device code, and all tokens.

The source Python suite ran 145 tests: 141 passed and four platform-specific
checks skipped, in 27.224 seconds. The final browser suites passed 26 cases in
each of Chromium, Firefox, and WebKit, including cross-tab session changes,
failed status verification, keyboard controls, and a 500-repository picker at
desktop and mobile sizes. All 27 scoped axe scans reported no tested violations.
Native portable validation is recorded in VERIFICATION.md. Organization-policy
variants, complete visual acceptance, and release acceptance are not established
by the single live flow. The owner's acknowledgement resolved the reported
private repository issue; it was not full release acceptance. The older
v0.2.0-rc.1 binary does not contain this feature.
