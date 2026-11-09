<div align="center">

<img width="1280" height="640" alt="social-preview" src="https://github.com/user-attachments/assets/135ef777-dcdb-4661-b20f-12f177a5af85" />

# CommitandSee

### Find your unfinished work. Across your Git projects.

You changed a file in one project, left a branch in another, and saved something
in a stash. **CommitandSee brings those loose ends into one local dashboard**,
alongside the commit history of the repositories you choose.

**[Download for Windows x64 — portable ZIP](https://github.com/TOTALLYMAJOR/CommitandSee/releases/download/v0.4.0-rc.1/CommitandSee-0.4.0-rc.1-Windows-x64-7e04f096605e.zip)**

**v0.4.0-rc.1 prerelease · Python included · Git required · MIT license**

Observe local checkouts without a GitHub account. No staging, committing,
pushing, or merging is performed by the dashboard.

Optional [GitHub sign-in](#connect-github) adds published history from the public
and private repositories you authorize and select.

[Get started](#get-started-on-windows) · [Compare alternatives](#alternatives-and-where-commitandsee-fits) · [Add repositories](#add-and-remove-repositories) · [Run from source](#run-from-source) · [Troubleshooting](#troubleshooting)

</div>

## A clearer place to pick up your work

- **Find changes outside the checkout in front of you.** See staged, unstaged,
  untracked, and conflicted paths across registered worktrees, plus saved stashes.
- **Bring a multi-repository product into one view.** Group repositories by
  product, filter the dashboard, and compare activity without combining their Git histories.
- **Spot branches worth reviewing.** See ahead/behind counts against cached
  upstreams and ancestry-based integration candidates, with unknown states kept visible.
- **Connect recent progress with unfinished work.** Daily commits and weekly
  additions/deletions sit beside current working state; line counts describe churn,
  not productivity or completion.
- **Keep control of your repositories.** Local checkouts are observed read-only.
  Removing a source stops monitoring; it does not delete its checkout, history,
  or downloaded cache.

## Get started on Windows

1. **Prepare Git and extract the app.** Install [Git for Windows](https://git-scm.com/install/windows)
   if needed; version 2.37 or newer is required. Download the ZIP above and choose
   **Extract All**, keeping its `_internal` directory beside the EXE. Do not run
   inside the ZIP. **Python is already included.**
2. **Open `CommitandSee.exe`.** A console opens, followed by the dashboard in your
   default browser. Keep the console open while using the app.
3. **Add your first project.** Choose **Add repository → Local checkout**, paste the absolute path to an
   existing Git checkout, and choose **Add repository**. For example:
   `C:\Users\you\projects\my-app`.

The first launch starts with an empty repository list. It does not search your
computer automatically. For a public GitHub project, leave the source set to
**Public GitHub repository** and paste its URL instead.
Or use **Connect GitHub** to select repositories from your authorized account.

The launcher selects an available local port. If no browser tab opens, copy the
**Dashboard URL** printed in the console. That URL can change after a restart.

This is an **unsigned Windows x64 prerelease**, tested on Windows 11. The native
process-control path requires Windows 10 / Server 2016 or newer; clean-machine
compatibility and SmartScreen reputation have not been qualified. There is no
signed installer, background service, or automatic updater. See the
[release page](https://github.com/TOTALLYMAJOR/CommitandSee/releases/tag/v0.4.0-rc.1)
for the ZIP, checksum, build information, and verification limits.

## Questions you can answer at a glance

![CommitandSee dashboard showing repository metrics and commit-history charts](docs/images/dashboard-live.png)

*Earlier local capture during collection. Pending sources and partial totals
remain visible; upstream comparisons use locally cached Git information.*

| Your question | What the dashboard shows |
| --- | --- |
| Where did I make progress? | Commit activity and lines added/deleted over time, across selected refs |
| What is still uncommitted? | Staged, unstaged, untracked, and conflicted paths |
| What did I leave elsewhere? | Linked worktrees, local branches, and stashes |
| What might not be pushed? | Branches ahead of their locally cached upstream refs |
| What might not be merged? | Git ancestry against your selected comparison ref |
| How complete is this picture? | Observation times, pending sources, failures, and partial history |

Filter by repository, product, and history window. Expand a worktree's changed
paths to investigate it in your editor. **Export JSON** saves the complete current
snapshot, including repositories outside the active filters. Review it for private
project information before sharing.

GitHub remains the source for hosted pull requests, reviews, checks, and releases.
CommitandSee adds visibility into work that has not reached GitHub. It does not
stage, commit, push, merge, reset, or delete your repository work.

Want to explore before setting up repositories? Download the source from the
[release page](https://github.com/TOTALLYMAJOR/CommitandSee/releases/tag/v0.4.0-rc.1)
and open [`demo.html`](demo.html) locally. Its data is clearly labeled synthetic.

### Inspect a selection and compare periods

The **About this selection** panel explains the displayed history using captured
commit details. It shows totals, the three largest contributors, and each
contributor's share of added, deleted, or changed lines. Changed lines are the sum
of additions and deletions. The panel follows the repository and history filters.

Drag horizontally across either chart to zoom both charts into that range.
Keyboard users can hold **Shift** while using the arrow keys, then press **Enter**.
**Escape** cancels a keyboard selection. **Reset zoom** returns to the previous
chart interval. Touch users can drag horizontally and scroll vertically.

The zoom interval is chosen automatically, from 15 minutes through weeks.
The interval menu can override it. For unzoomed hour and 15-minute views, select
a chart date. All times follow the dashboard timezone, including repeated
daylight-saving hours. Selections use an inclusive start and exclusive end.

The comparison uses the immediately preceding period of equal elapsed duration.
It shows the actual totals and percentage difference for the selected metric.
Comparison requires complete timestamped coverage for every selected repository
in both periods. An earlier zero is displayed without a percentage ratio.
Shallow, truncated, missing, and older aggregate-only history receive explicit
coverage messages. Current worktree, branch, and stash observations remain
separate from the chart selection.

### Follow changes to pull requests

Click a bar or point, or focus the plot and press **Enter**, to inspect its
commits. The detail view shows commit time, subject, and line counts.
A live lookup sends the repository and selected commit SHA to GitHub.
For up to four commits, the dashboard opens the PR when GitHub returns the same
single association for every commit. For other selections, use the individual
commit lookup or the selection panel's **Group by PR** button.

PR grouping processes at most 20 commits per click, largest contributors first.
The next batch is available after the first completes. Successful lookups are
cached in the browser for five minutes, scoped to the current repository and
GitHub session. Results are held in memory and kept out of exported snapshots.
**Refresh PR associations** explicitly requests fresh results. A failed lookup
pauses the batch so that remaining commits can be checked later.

Each captured commit contributes to one group. A commit with one association is
assigned to that PR. Multiple associations, an incomplete association list, no
association found, unavailable lookups, pending lookups, and missing GitHub
origins are displayed separately. Shares use all captured line counts for the
selected metric, including unresolved groups.

Local checkouts need a recognized GitHub origin for links. Private API lookups
require an imported repository and **Pull requests: read-only** permission on the
GitHub App installation. If access is unavailable, use a commit's GitHub search
link with your browser session. Static reports support selection, zoom, and
comparisons from embedded data, with browser search links for PRs.
Collect a fresh snapshot to add timestamped details to older reports.


## Alternatives and where CommitandSee fits

Other tools cover parts of this workflow, and some go much further in editing
and collaboration. Choose the one that matches the work you need to do:

| Alternative | Choose it when you want… |
| --- | --- |
| [GitKraken Workspaces](https://help.gitkraken.com/gitkraken-desktop/workspaces/) | Repository grouping, bulk fetch/pull, and shared workspace or pull-request workflows. It also [shows pending changes across worktrees](https://help.gitkraken.com/gitkraken-desktop/worktrees/), so there is meaningful overlap. |
| [GitButler](https://docs.gitbutler.com/overview) | To organize and commit changes across parallel branches, or publish dependent work as [stacked pull requests](https://docs.gitbutler.com/features/branch-management/stacked-branches). |
| [GitHub Insights / Pulse](https://docs.github.com/en/repositories/viewing-activity-and-data-for-your-repository/using-pulse-to-view-a-summary-of-repository-activity) | Repository-level summaries of published commits, pull requests, and issues directly on GitHub. |
| [lazygit](https://github.com/jesseduffield/lazygit/blob/master/README.md) | A terminal interface for hands-on Git work, including staging individual lines, committing, and interactive rebasing. |

**Choose CommitandSee for a read-only overview of local work and published Git
history across repositories, alongside the Git tools you already use.** It is
useful when the immediate task is to see where work stands and decide what to
inspect next. Use your editor or Git client to make the changes.

## What is available and what has been checked

This README describes **v0.4.0-rc.1**: local checkout visibility, anonymous public
GitHub history, and an optional [GitHub picker](#connect-github) for authorized
repositories. The Windows ZIP bundles Python and has passed native startup and
offline smoke checks. It is unsigned and remains a prerelease.

Current source validation includes 145 Python tests run (141 passed, four
platform-specific skips), 78 browser cases passed across Chromium, Firefox, and
WebKit, and 27 scoped automated accessibility scans. A separate live source
preview completed GitHub device sign-in and collected one authorized private
repository's history. These are bounded engineering checks, not user counts,
complete accessibility certification, or proof of every machine and organization
configuration. [VERIFICATION.md](VERIFICATION.md) records the evidence and limits.

## Add and remove repositories

The portable app supports saved additions and removals immediately. The source
server needs a `--config` file to save these actions; see [source setup](#run-from-source).

| Source | Enter | What it can observe |
| --- | --- | --- |
| **Local checkout** | Existing absolute path, such as `C:\Users\you\projects\app` or `/home/you/projects/app` | Local history, working files, branches, linked worktrees, and stashes |
| **Public GitHub repository** | `https://github.com/owner/repository` | Published default-branch history downloaded anonymously into an app-owned bare cache |
| **GitHub repository** | **Connect GitHub**, then choose repositories from the searchable list | Published default-branch history for repositories authorized by your account and the configured read-only GitHub App, including private repositories |

**Add repository** defaults to the public GitHub option. Choose **Local checkout**
for a folder already on your computer. You can supply a display name and product
label. Registered linked worktrees are included automatically; duplicate paths
sharing the same Git common directory are rejected.

![Repository source choices in the Add repository dialog](docs/images/add-repository.png)

To stop monitoring a repository, choose **Remove** in its table row and confirm
its name. This removes it from the dashboard and survives a restart. **It does
not delete checkout files, Git history, observation history, or downloaded remote
caches.** You can add it again later. Removing a combined row removes its saved
linked-worktree aliases together. On a narrow screen, scroll the repository table
horizontally to reach its actions.

Private GitHub repositories can use the sign-in flow below or a local checkout.
Other remote hosts still need a local checkout. Local observation works offline. Remote sources require Internet
access and cannot reveal local changes, stashes, unpublished commits, PR status,
or CI results.

New sources appear as pending while collection runs. Large repositories and
Windows-mounted WSL checkouts can take longer than the refresh interval. Pending
or failed observations remain unknown; they do not mean zero activity.

## Connect GitHub

CommitandSee includes the public registration for the
[CommitandSee GitHub App](https://github.com/apps/commitandsee). Users do not enter
app IDs, paste tokens, or register a separate app to sign in. If you are upgrading
from v0.2.0-rc.1, sign-in was introduced in v0.3.0-rc.1. Publishers maintaining a fork
can use the [GitHub App setup guide](docs/GITHUB-APP-SETUP.md) to supply their own
registration.

1. Choose **Connect GitHub → Sign in with GitHub**. Open GitHub using the
   displayed link, enter the displayed code there, and complete authorization.
2. If no repositories appear, choose **Configure repository access on GitHub**.
   Install the app on the relevant personal account or organization and allow
   the repositories you need. Organization approval may be required. Return to
   the dashboard and choose **Refresh list** after access is granted.
3. Search the repository list, check the repositories to monitor, and choose
   **Add selected**. Only selected repositories are saved and queued for history
   collection; signing in does not add every accessible repository.

The app requests read-only repository access. A repository must be available to
both your account and the app installation. An empty list or pending organization
request does not grant access. Local checkouts and manual public URLs remain
available alongside this picker.

**Sign-in lasts for the running app session.** Access and refresh tokens stay in
memory. **Disconnect GitHub** forgets them; stopping the app also requires a new
sign-in next time. Saved repository choices remain, and authenticated rows show
**Sign in required** when disconnected. Closing the browser tab alone does not
stop the app or sign it out. Disconnecting locally does not revoke the GitHub
installation or authorization; manage those in GitHub settings when needed.

**Downloaded private history remains on disk after disconnect or removal.**
Private bare caches contain Git objects, even though no checkout is created.
Stop the app before explicitly deleting downloaded cache data if you want that
local copy removed; backups may contain it too. Never confuse the app cache with
your original repository. A live test of the source implementation completed
device sign-in and collected one authorized private repository's history. See
[verification](VERIFICATION.md) for the bounded source, browser, and native-build evidence.

## Stop, restart, and update

| Task | Portable Windows app | Source server |
| --- | --- | --- |
| **Reopen the dashboard tab** | Copy the running console's **Dashboard URL** into your browser | Open the URL printed by the server; the default is `http://127.0.0.1:8765` |
| **Stop collection** | Press **Ctrl+C** in the launcher console | Press **Ctrl+C** in the terminal running the server |
| **Restart** | Stop the app, then open the same `CommitandSee.exe` again | Stop the server, then rerun your original command with the same config and state paths |
| **Update** | Stop all instances. Extract the new ZIP into a separate folder and run its EXE; keep the entire folder together | Stop the server, update your source checkout, then rerun the same command |

Closing the browser tab does **not** stop collection. The app must remain running
and your computer awake to observe work. Restart after editing configuration
outside the dashboard. No scheduler or Windows service is installed.

## Where your data lives

The portable app uses **`%LOCALAPPDATA%\CommitandSee`**, outside its extracted
program folder. Paste that path into File Explorer's address bar.

| Item | Purpose |
| --- | --- |
| `config.json` | Base settings and any manually configured repositories |
| `config.json.registry.sqlite3` | Saved dashboard additions and removal overrides; created on the first add/remove |
| `observations.json` | Observation timing used to track dirty-work ages and gaps |
| `public-repositories` | Downloaded public Git history; removing a source does not erase this cache |
| `github-repositories` | Authenticated GitHub history, including private Git objects; disconnect and removal retain this cache |

**Back up:** stop every instance, then copy the data folder. When moving an
existing configuration, keep its JSON and registry together. The dashboard leaves
the base JSON unchanged; the registry overrides it. A base entry removed in the UI
stays removed after external JSON edits until added again through the dashboard.

**Update:** replace the program folder, not the data folder. Existing source-CLI
settings are not imported automatically into the portable app. Advanced users can
launch `CommitandSee.exe --config "C:\path\config.json" --state "C:\path\observations.json"`
to use existing files. Keep configuration, state, registry, and report outputs
outside monitored checkouts and registered linked worktrees, and use distinct
config and state paths.

The source CLI defaults observation state to
`~/.git-activity-dashboard/observations.json`; remote caches sit beside that file.
`--state` overrides the state path. Paths, branch names, commit metadata, and
exports can contain private project information. Snapshots do not include working
file contents or patches, but downloaded remote caches contain Git objects and
can hold private repository history.

## Run from source

Use **Python 3.11+** and **Git 2.37+**. The source app needs no third-party Python
packages, Node installation, or frontend build step.

```bash
git clone https://github.com/TOTALLYMAJOR/CommitandSee.git
cd CommitandSee
python3 git_dashboard.py serve --repo /absolute/path/to/your/project
```

Open **http://127.0.0.1:8765**. Replace the example path with your checkout.
On native Windows, use `py -3` in place of `python3`; use Python and Git inside
WSL for WSL repositories. The observer expects paths for the environment where it
runs: for example `/mnt/c/Users/...` when using a Windows checkout from WSL.

The `--repo` launch command controls the repository list. It **cannot save UI
additions/removals**; repeat `--repo` to monitor more checkouts, or use a config file.

### Enable saved repository controls

Create a JSON file outside your checkouts, for example
`~/.config/commitandsee/config.json`, with an empty list:

```json
{
  "title": "My workspace",
  "timezone": "America/Chicago",
  "repositories": []
}
```

```bash
python3 git_dashboard.py serve --config ~/.config/commitandsee/config.json
```

Then use **Add repository** in the dashboard. Do not overwrite an existing
configuration to follow this example. [`config.example.json`](config.example.json)
shows more settings but contains sample paths; replace its entries before use.

For product grouping, add `name`, `product`, and `ref` to each local repository
entry, such as:

```json
{"name": "API", "product": "My product", "path": "/home/you/projects/api", "ref": "main"}
```

Relative paths in JSON resolve from the config file's directory. Sources also
passed with `--repo` remain controlled by that launch command and cannot be
removed persistently through the UI.

### Options and exports

```bash
# Compare with local main and collect a 90-day history window.
python3 git_dashboard.py serve --repo ~/projects/my-app --ref main --days 90

# Choose another port and a shorter local refresh interval.
python3 git_dashboard.py serve --repo ~/projects/my-app --port 8766 --interval 10

# Write a dated offline report outside the observed checkout.
python3 git_dashboard.py scan --repo ~/projects/my-app --output ~/activity.html --json ~/activity.json
```

The HTML report opens offline. It is a snapshot; use `serve` for automatic updates.
Static reports cannot add or remove sources.

| Config setting | Default | Meaning |
| --- | --- | --- |
| `days` | `180` | History window |
| `refresh_seconds` | `30` | Delay between local collection cycles; minimum 5 seconds |
| `history_refresh_seconds` | `300` | Cache unchanged history between collections |
| `max_commits` | `20000` | Local history bound; truncated totals remain partial |
| `stale_days` | `14` | Highlight old branch tips for review |
| `timezone` | `America/Chicago` | Chart calendar buckets; falls back to UTC if unavailable |
| `exclude_globs` | `[]` | Exclude matching paths from line metrics; pending files remain visible |

Refresh intervals are targets, not completion or freshness guarantees. Public
history collection has a 2,000-commit depth limit and 30-second Git command timeout;
these are not byte or disk quotas. Large downloads, unavailable repositories, and
GitHub rate limits produce partial results or explicit errors.

## Understand the numbers

- **History** counts non-merge commits reachable from the selected ref, grouped by
  committer date. It is not an all-branches action ledger. Missing objects, shallow
  history, exclusions, and commit limits affect completeness.
- **Working changes** compare HEAD to the working tree. Staged and unstaged
  comparisons are separate; adding them can double-count or cancel changes.
  Untracked paths are listed without counting their contents as tracked churn.
- **Ahead/behind** uses locally cached upstream refs. Local-checkout observation
  does not fetch; missing upstreams remain unknown publication status.
- **Unmerged candidates** use Git ancestry. Squash/rebase merges and reused
  branches need interpretation; this is not authoritative GitHub PR status.
- **Old work** is a review hint. Dirty ages start when this tool first observes the
  work. An old branch or observation gap does not prove abandonment.
- **Portfolio totals** are per configured source. Independent clones or overlapping
  local/public sources can count the same commits more than once.

The server binds to **127.0.0.1**. Local Git observation disables optional locks,
filesystem-monitor callbacks, and signature display. Public URL collection uses
anonymous HTTPS; authenticated GitHub collection uses the running app's session
credentials. Both use app-owned bare caches without checking out or executing
repository files. This is a local dashboard, not a hosted team service.

## Troubleshooting

| What happened | What to do |
| --- | --- |
| **Git was not found** | Install Git for Windows, then close and reopen the launcher. In a terminal, `git --version` should report Git 2.37 or newer. |
| **No browser tab opened** | Keep the console open and copy its printed **Dashboard URL**. The portable port is chosen at startup; do not assume it is 8765. |
| **The EXE cannot find bundled files** | Extract the complete ZIP again. Keep `_internal` beside the EXE and run it from the extracted folder. |
| **Windows warns about an unknown publisher** | The prerelease is unsigned. Verify its GitHub source and checksum against the release assets, and follow your device's security policy. |
| **The local path is rejected** | Select **Local checkout** and enter an existing absolute Git-checkout path for the environment running the observer. A GitHub URL belongs in the public-source option. |
| **Add or Remove is unavailable** | Use the portable app or launch the source server with `--config`. Static reports and `--repo`-controlled sources cannot save registry changes. |
| **The page shows pending, partial, or unknown data** | Allow the first scan to finish and inspect observation coverage. Large repositories, missing worktrees, shallow history, or unavailable refs can limit results. |
| **A public repository cannot be added** | Check the public GitHub URL, Internet access, and reported rate-limit/availability error. For private repositories, use a local checkout or the GitHub picker. |
| **GitHub sign-in is not configured** | Use the complete v0.4.0-rc.1 package or current source, which includes the public app registration. Check any publisher overrides. The older v0.2.0-rc.1 ZIP has no sign-in feature. See the [setup guide](docs/GITHUB-APP-SETUP.md). |
| **Signed in, but a repository is missing** | Check your account access and the app installation's allowed repositories. Obtain organization approval if required, then choose **Refresh list**. |
| **A device code expired or was declined** | Choose **Retry sign-in** to start a fresh authorization. Never send the code or tokens in a support report. |
| **Configuration changed outside the dashboard** | Stop and restart with the same configuration. Keep the JSON and its registry together. |
| **The source server's port is already in use** | Stop your earlier server or choose another port with `--port 8766`. The portable app selects an available port by default. |

If the problem remains, [open an issue](https://github.com/TOTALLYMAJOR/CommitandSee/issues)
with the app version, OS, Git version, startup command, and redacted error text.
Use a small disposable reproduction; do not attach private configuration or exports.

## Contribute and verify

Read [CONTRIBUTING.md](CONTRIBUTING.md), [release notes](RELEASE-NOTES.md), and
[VERIFICATION.md](VERIFICATION.md) for scope and recorded evidence. The application
is [MIT licensed](LICENSE). [Packaging instructions](packaging/README.md) explain
how the native Windows ZIP is built.

```bash
python3 -B -m unittest -v
```

Optional browser regressions use an existing Node, Playwright, and browser
installation; these are development tools, not app dependencies:

```bash
BROWSER_ENGINE=chromium node --test --test-concurrency=1 test_dashboard_browser.cjs test_github_browser.cjs
BROWSER_ENGINE=firefox node --test --test-concurrency=1 test_dashboard_browser.cjs test_github_browser.cjs
BROWSER_ENGINE=webkit node --test --test-concurrency=1 test_dashboard_browser.cjs test_github_browser.cjs
```

Run engines sequentially. `PLAYWRIGHT_MODULE`, `BROWSER_EXECUTABLE`, and the
Chromium-only `CHROMIUM_EXECUTABLE` support tools installed outside the project.
An installed `axe-core` or `AXE_CORE_MODULE` enables accessibility scans; absence
is reported as skipped. Fixtures are synthetic or disposable. Passing these
checks does not establish complete accessibility conformance or production readiness.
[`CHECKSUMS.sha256`](CHECKSUMS.sha256) records source-package integrity.

**Start with one repository and see what is still waiting.**

[Download the Windows portable ZIP](https://github.com/TOTALLYMAJOR/CommitandSee/releases/download/v0.4.0-rc.1/CommitandSee-0.4.0-rc.1-Windows-x64-7e04f096605e.zip)
— Python included; Git required. For other platforms, [run from source](#run-from-source).
