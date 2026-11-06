# Release notes

## v0.3.0-rc.1 — GitHub sign-in and selected repository imports

- Connect the bundled CommitandSee GitHub App using a short browser authorization
  code. The app requests read-only Contents and Metadata permissions. No client
  secret, GitHub CLI installation, or hosted login server is required.
- Search the repositories accessible to both the signed-in user and the app
  installation, then add selected repositories. Public and authorized private
  repositories are labeled separately. Organization access may require approval.
- Keep tokens in memory for the running session, refresh expiring access, and
  forget credentials on disconnect or exit. Saved repository selections remain.
  Authenticated observations are cleared on disconnect; late responses and
  account changes cannot restore an earlier session's observations.
- Fetch published default-branch history into a separate, account-bound
  `github-repositories` cache. Disconnecting or removing a repository does not
  erase downloaded private objects. Remote history cannot establish local
  changes, stashes, unpublished commits, PR status, or CI results.
- Cancel an in-flight authenticated Git fetch when its account session changes,
  retaining the existing subprocess lifetime and output limits.

The Windows portable ZIP includes this feature and the public app registration.
Extract the complete new ZIP into a separate folder, stop the previous app, and
open the new `CommitandSee.exe`. Existing saved choices remain in the app data
folder; sign in again after each app restart. The older `v0.2.0-rc.1` ZIP below
does not include sign-in. See the
[v0.3.0-rc.1 prerelease](https://github.com/TOTALLYMAJOR/CommitandSee/releases/tag/v0.3.0-rc.1)
for the unsigned Windows x64 download, checksum, and build information, and
[GitHub setup](docs/GITHUB-APP-SETUP.md) for installation consent, publisher
overrides, session behavior, and cache handling. Validation and provider evidence
are recorded separately in [VERIFICATION.md](VERIFICATION.md).

The README now explains the product's concrete benefits, gives a three-step
startup path, and compares GitKraken, GitButler, GitHub Insights, and lazygit
without claiming they lack overlapping capabilities.

## v0.2.0-rc.1 — portable app, repository controls, and reliability

CommitandSee brings Git history, branches, worktrees, and unfinished local work
into one local dashboard. This update adds persistent repository removal and
repairs configuration, subprocess, cache, and keyboard interaction defects.

### Windows portable candidate

- A platform-specific ZIP bundles Python and timezone data. Extract the complete
  folder and open `CommitandSee.exe`; the launcher checks Git, starts on an
  available loopback port, waits for readiness, and opens the default browser.
- Git for Windows remains a prerequisite. Keep the console open and press Ctrl+C
  to stop collection; closing a browser tab alone does not stop the app.
- User data lives in `%LOCALAPPDATA%\CommitandSee`, separate from the program.
  Stop the app before replacing the extracted folder to update it. No installed
  service, automatic updater, or signed installer is included.
- The source CLI remains available. Source and portable entrypoints reject
  configuration/state path collisions before starting the collector.

### Repository controls

- Remove a saved repository from the table after a named confirmation. Checkout
  files, Git history, observation history, and downloaded public caches remain.
- Add and remove sources in an application-owned SQLite registry beside the
  base configuration. The dashboard leaves the JSON configuration untouched,
  including when another editor writes it during a request.
- Check configuration and registry placement against registered linked
  worktrees as well as the primary checkout.

### Reliability and interaction

- Bound Git command lifetime and output, including descendants that keep pipes
  open after the direct child exits. Windows uses a Job Object assigned at
  process creation; POSIX uses a separate process group. Startup failures also
  clean up the child. The native Windows path requires Windows 10 or later
  (Windows Server 2016 or later).
- Refresh history at the selected timezone's calendar boundary.
- Preserve chart selection, keyboard focus, and expanded worktree details
  across refreshes. An old request cannot clear a newly reopened add form.
- Preserve focus when a worktree disappears and make review tabs and chart
  controls accessible to keyboard users.
- Use the CSS background fallback when a software renderer is reported.

### Upgrade notes

Use the complete source package: `repository_registry.py` and `windows_job.py`
are runtime modules. No third-party Python package is required.

Existing JSON configurations continue to work without migration. The first
dashboard add or remove creates `<config filename>.registry.sqlite3` beside the
JSON file. Stop every observer using the configuration before backing up or
moving both files together. The JSON file remains the base;
the registry records additions and removal overrides. A removed base entry stays
removed across external JSON edits until added again through the dashboard.
Restart after editing the base JSON. Sources supplied with `--repo` remain controlled by
the launch command.

### Verification and limits

See [VERIFICATION.md](VERIFICATION.md) for exact commands, runtimes, outcomes,
and fixture boundaries. Download assets and publication status are listed in
the [v0.2.0-rc.1 prerelease](https://github.com/TOTALLYMAJOR/CommitandSee/releases/tag/v0.2.0-rc.1).
This candidate is not a production-acceptance claim.

Anonymous public GitHub history remains bounded and may be partial. Private
GitHub sign-in, authoritative PR/CI status, and automatic background-service
installation are outside this update. Browser automation and software graphics
checks do not measure hardware GPU or battery performance.

## v0.1.0 — initial release

The earlier published release is recorded at
[v0.1.0](https://github.com/TOTALLYMAJOR/CommitandSee/releases/tag/v0.1.0).
Its original verification and assets remain historical evidence; they do not
include the changes listed above.
