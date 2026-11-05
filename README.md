# Work Visibility

An independent, local-first work observer. Git observations work without Wale,
AgentFlow, a task system, or GitHub credentials. Wale is an optional future adapter.

This first slice provides a local snapshot command and persistent observation
history. The supplied GitHub collector and static reports are preserved under
`starter/` and remain available through the same entry point. There is no new
dashboard, background service, or automatic repository discovery.

## Run

Requires Python 3.11+ and Git 2.36+. No third-party packages or installation.
Local validation used WSL/Linux and Git 2.43.0; Windows execution is not qualified.

From this directory:

```bash
python3 -B work_visibility.py snapshot --root /absolute/path/to/a/clone
python3 -B work_visibility.py history --limit 20
```

Repeat `--root` for independent clones. A clone's registered linked worktrees are
enumerated automatically. Subdirectories are accepted by Git, but a parent folder
containing many repositories is not recursively scanned. Only configure repositories
you want observed. Reports and the database contain private paths and branch names.

The default SQLite database is
`$XDG_STATE_HOME/work-visibility/observations.sqlite3`, falling back to
`~/.local/state/work-visibility/observations.sqlite3`. Override with `--database` on
both commands. Database writes inside any observed worktree or common Git directory
are rejected. Snapshot JSON goes to stdout; if redirecting it, keep your output
outside monitored repositories too. The observer cannot control shell redirection.

Exit status: `0` for complete local inventory in the declared scope; `2` for partial
coverage (JSON is still delivered and observations persist); `1` for failure to
initialize or persist. A `complete` local inventory does **not** imply remote,
task, LOC, submodule-content, deployment, or acceptance coverage.

Existing starter commands:

```bash
python3 -B work_visibility.py collect --help
python3 -B work_visibility.py report --help
python3 -B work_visibility.py demo --output-dir /tmp/work-visibility-demo
```

`collect` makes GitHub requests only when explicitly invoked. `demo` writes clearly
synthetic data. The supplied Wale manifest is a historical example, not an enabled
monitoring configuration. Consult `starter/README.md` for those command options.

## What snapshots observe

- Per configured clone: canonical common Git directory, all local branch refs and
  heads, upstream/cached push tracking ref when available, shared stash identities.
- Per registered worktree: path, current HEAD and branch, detached/unborn status,
  staged/unstaged/untracked/conflicted paths, registration flags, and coverage.
- Independent clones remain distinct; linked worktrees share clone observations.
- Each worktree and shared-ref observation has its own collection time. The scan
  has a start, finish, and measured elapsed duration.
- SQLite retains first seen, last seen, last state change, last successful
  observation, last known successful state, and deduplicated transition history.
  Unchanged polls update freshness without adding transition events.

Identity is path-bound within this monitor database: a persisted installation UUID
and canonical common directory identify a clone; the clone and worktree path
identify a worktree. Moving a clone or replacing the database creates new identities.
Renames, cross-machine aggregation, and replacement-at-the-same-path detection are
not implemented. A gap recovery updates the original configured-root entity.

Files are never ingested: only path/status metadata and stat fingerprints are
stored. Fingerprints help detect concurrent changes; they are not content digests
or proof that nothing changed between scans. A metadata-only file touch can also
produce a transition. No inactivity or abandonment rule is implemented. A long
interval without observations establishes neither inactivity nor absence of a run.

## Read-only observation boundary

The observer issues no fetch, prune, checkout, index update, configuration write,
commit, remote query, or native task operation. Monitor state belongs outside the
repositories. It removes inherited Git override variables, disables optional locks,
filesystem monitoring, hooks, untracked-cache use and automatic maintenance, and
blocks transport protocols. Diagnostics, timeouts and output-budget failures become
coverage gaps; raw Git stderr and configured command values are not persisted.

Git older than 2.36 is rejected: older versions can interpret `core.fsmonitor=false`
as a hook pathname. Any configured clean/process filter makes worktree status
unavailable rather than executing it. Partial-clone configuration similarly blocks
content-sensitive observation. Shared refs can still be observed. These are
conservative limitations, not evidence that those repositories are clean.

Each command has a 10-second timeout and 8 MiB combined-output budget. Large scans
can still take several commands per worktree; no portfolio-wide latency guarantee
is claimed. Status, HEAD/index and changed-path fingerprints are checked twice,
with one bounded retry for inconsistency. This is not an atomic snapshot or a
security boundary against an adversary concurrently replacing repository files,
configuration, executables or monitor storage.

Submodule paths are identified but their content is not scanned; such worktrees
are partial. Bare repositories expose shared refs with an explicit no-worktree
state. Inaccessible and prunable registrations remain visible. Symlinked path
components and OS permissions follow the host's filesystem behavior.

## Still to build

Fresh publication/ancestry comparisons, full PR head/base and merge binding, task
and journal adapters, LOC with named baselines, portfolio memberships, attention
policies, an updating UI, and background operation. All local publication states
remain `unknown`; a clean worktree does not hide its local branch observations.
The starter receipt is a supplied JSON format, not a native authority record.

## Validate

```bash
python3 -B -m unittest discover -s tests -v
python3 -B -m unittest discover -s starter -p test_wale_visibility.py -q
```

Tests use disposable Git repositories and offline API fakes; they do not scan
your projects. See [verification](docs/VERIFICATION.md) and
[design scope](docs/DESIGN.md). Original package integrity can be checked with
`sha256sum -c CHECKSUMS.sha256` from `starter/`.

## Provenance

The supplied `wale-product-visibility.zip` was imported unchanged under `starter/`.
Archive SHA-256: `e0df749c07486a290abadc7427c312c540cbd3b1bd7f3ee277bc81eb9c5c7d4a`.
Its dated reports and verification claims remain historical, not current checks.
No license grant has been invented for the supplied material; determine distribution
terms before external publication.
