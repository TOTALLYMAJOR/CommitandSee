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
