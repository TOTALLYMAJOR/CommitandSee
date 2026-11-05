# Live dashboard UI direction

Owner selected November 5, 2026: the supplied black/navy glass dashboard,
emerald and indigo accents, six metrics, paired charts, repository table, review
tabs, and animated topographic background. The follow-up technology choice was
local CSS, inline SVG icons, and native WebGL. No CDN or new packages.

The existing collector schema, safe text rendering, independent evidence states,
accessible native selects, keyboard charts, tables, exports, and CSP are retained.
The background is decorative: reduced motion draws a static frame; hidden tabs
pause animation. Rendering is capped at approximately 30 frames/second, DPR 1.5,
and two million pixels. CSS supplies a fallback. Battery/GPU cost is unmeasured;
browser capture produced WebGL ReadPixels performance warnings.

The added local repository dialog accepts an existing absolute checkout path,
optional display name, and product. Same-origin loopback POST writes only the
fixed dashboard configuration outside monitored repositories. It validates Git
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
