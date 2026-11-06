# Release notes

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
