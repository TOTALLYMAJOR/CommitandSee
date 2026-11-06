<div align="center">
<div align="center">
<img width="1280" height="640" alt="social-preview" src="https://github.com/user-attachments/assets/135ef777-dcdb-4661-b20f-12f177a5af85" />
# CommitandSee

### See the work GitHub can't see.

A local-first Git dashboard for uncommitted changes, unpublished branches,
linked worktrees, stashes, and commit history across your repositories.

**[Download for Windows x64 — portable ZIP](https://github.com/TOTALLYMAJOR/CommitandSee/releases/download/v0.2.0-rc.1/CommitandSee-0.2.0-rc.1-Windows-x64-929746ee8170.zip)**

**v0.2.0-rc.1 prerelease · Python included · Git required · MIT license**

[Get started](#get-started-on-windows) · [Add repositories](#add-and-remove-repositories) · [Stop or restart](#stop-restart-and-update) · [Run from source](#run-from-source) · [Troubleshooting](#troubleshooting)

</div>

## Get started on Windows

1. Install [Git for Windows](https://git-scm.com/install/windows) if you do not already
   have it. Git 2.37 or newer must be available to the app; **you do not need to
   install Python** for the portable ZIP.
2. Download the ZIP above and choose **Extract All**. Keep the extracted folder
   together, including its `_internal` directory. Do not run the app inside the ZIP.
3. Open **`CommitandSee.exe`**. A console opens, followed by the dashboard in your
   default browser. Keep the console open while using the app.
4. Choose **Add repository → Local checkout**, paste the absolute path to an
   existing Git checkout, and choose **Add repository**. For example:
   `C:\Users\you\projects\my-app`.

The first launch starts with an empty repository list. It does not search your
computer automatically. For a public GitHub project, leave the source set to
**Public GitHub repository** and paste its URL instead.

The launcher selects an available local port. If no browser tab opens, copy the
**Dashboard URL** printed in the console. That URL can change after a restart.

This is an **unsigned Windows x64 prerelease**, tested on Windows 11. The native
process-control path requires Windows 10 / Server 2016 or newer; clean-machine
compatibility and SmartScreen reputation have not been qualified. There is no
signed installer, background service, or automatic updater. See the
[release page](https://github.com/TOTALLYMAJOR/CommitandSee/releases/tag/v0.2.0-rc.1)
for the ZIP, checksum, build information, and verification limits.

## What you can see

![CommitandSee dashboard showing repository metrics and commit-history charts](docs/images/dashboard-live.png)

*Earlier local capture during collection. Pending sources and partial totals
remain visible; upstream comparisons use locally cached Git information.*

| Your question | What the dashboard shows |
| --- | --- |
| What changed today? | Commit activity and lines added/deleted over time |
| What have I not committed? | Staged, unstaged, untracked, and conflicted paths |
| Where did I leave work? | Linked worktrees, local branches, and stashes |
| What might not be pushed? | Branches ahead of their locally cached upstream refs |
| What might not be merged? | Git ancestry against your selected comparison ref |
| How complete is this picture? | Observation times, pending sources, failures, and partial history |

Filter by repository, product, and history window. Expand a worktree's changed
paths to investigate it in your editor. **Export JSON** saves the complete current
snapshot, including repositories outside the active filters. Line counts describe changes; they are not a productivity
or completion score.

GitHub remains the source for hosted pull requests, reviews, checks, and releases.
CommitandSee adds visibility into work that has not reached GitHub. It does not
stage, commit, push, merge, reset, or delete your repository work.

Want to explore before setting up repositories? Download the source from the
[release page](https://github.com/TOTALLYMAJOR/CommitandSee/releases/tag/v0.2.0-rc.1)
and open [`demo.html`](demo.html) locally. Its data is clearly labeled synthetic.

## Add and remove repositories

The portable app supports saved additions and removals immediately. The source
server needs a `--config` file to save these actions; see [source setup](#run-from-source).

| Source | Enter | What it can observe |
| --- | --- | --- |
| **Local checkout** | Existing absolute path, such as `C:\Users\you\projects\app` or `/home/you/projects/app` | Local history, working files, branches, linked worktrees, and stashes |
| **Public GitHub repository** | `https://github.com/owner/repository` | Published default-branch history downloaded anonymously into an app-owned bare cache |

**Add repository** defaults to the public GitHub option. Choose **Local checkout**
for a folder already on your computer. You can supply a display name and product
label. Registered linked worktrees are included automatically; duplicate paths
sharing the same Git common directory are rejected.

![Repository source choices in the Add repository dialog](docs/images/add-repository.png)

To stop monitoring a repository, choose **Remove** in its table row and confirm
its name. This removes it from the dashboard and survives a restart. **It does
not delete checkout files, Git history, observation history, or downloaded public
caches.** You can add it again later. Removing a combined row removes its saved
linked-worktree aliases together. On a narrow screen, scroll the repository table
horizontally to reach its actions.

Private GitHub repositories and other remote hosts need a local checkout; there
is no GitHub sign-in or private-repository import. Local observation works offline.
Public sources require Internet access and cannot reveal local changes, stashes,
unpublished commits, PR status, or CI results.

New sources appear as pending while collection runs. Large repositories and
Windows-mounted WSL checkouts can take longer than the refresh interval. Pending
or failed observations remain unknown; they do not mean zero activity.

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
`~/.git-activity-dashboard/observations.json`; public caches sit beside that file.
`--state` overrides the state path. Paths, branch names, commit metadata, and
exports can contain private project information, even though file contents and
patches are not retained.

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
filesystem-monitor callbacks, and signature display. Public collection uses an
isolated app-owned bare cache, anonymous HTTPS, and no checkout or execution of
public repository files. This is a local dashboard, not a hosted team service.

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
| **A public repository cannot be added** | Check the public GitHub URL, Internet access, and reported rate-limit/availability error. Private repositories need a local checkout. |
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
BROWSER_ENGINE=chromium node test_dashboard_browser.cjs
BROWSER_ENGINE=firefox node test_dashboard_browser.cjs
BROWSER_ENGINE=webkit node test_dashboard_browser.cjs
```

Run engines sequentially. `PLAYWRIGHT_MODULE`, `BROWSER_EXECUTABLE`, and the
Chromium-only `CHROMIUM_EXECUTABLE` support tools installed outside the project.
An installed `axe-core` or `AXE_CORE_MODULE` enables accessibility scans; absence
is reported as skipped. Fixtures are synthetic or disposable. Passing these
checks does not establish complete accessibility conformance or production readiness.
[`CHECKSUMS.sha256`](CHECKSUMS.sha256) records source-package integrity.

If CommitandSee helps you find unfinished work, a star helps other developers
find the project. Bug reports and clear reproductions are welcome too.
