# Independent work visibility: first implementation slice

Date: November 5, 2026. Status: local implementation; no background installation,
external publication, or owner visual acceptance.

## Intent and selected scope

OWNER INTENT: the tool is useful beyond Wale. The owner supplied the first version
and requested the proposed next step: an independent repository and the smallest
safe local snapshot command with persistent identity and freshness.

AGENT INFERENCE: establish `work-visibility` as a working repository name and retain
the starter as an independently runnable GitHub adapter. This name is not a selected
brand. Use the standard library, native Git, SQLite, and JSON output for this slice.
No external service, package install, task scheduler, or graphical direction is needed.

AGENT ADDITION: none beyond supporting safety, persistence, and validation required
for that slice. Optional subsequent features remain proposals.

## Component relationships

`work_visibility.py` dispatches local `snapshot`/`history` commands and the starter's
`collect`/`report`/`demo` commands. `local_observer.py` reads explicitly selected
clones, deduplicates common-directory observations, enumerates registered worktrees,
and reports partial/inaccessible states. `observation_store.py` stores the local
projection and transitions outside monitored repositories. History opens SQLite
read-only. No foreign task record is created or changed.

Native task systems retain task/run identity, execution, approvals, and receipts.
The monitor owns observations and their collection history only. The starter's
receipt matcher is not promoted into a shared canonical receipt store.

## First observable proof

Disposable repositories exercise edit → stage → commit, independent clones,
linked/detached/unborn/bare worktrees, non-current branches, shared stashes,
conflicts, NUL-delimited paths, partial clones, configured executable hooks/filters,
mid-scan changes, failed collection, restart, and repeated scans. Monitored file
bytes, index/config/refs included, are compared before and after a hook fixture scan.
Actual Windows behavior, owner repositories, UI rendering and visual acceptance
remain untested.

## Pending decisions and deferred scope

- Personal use versus shared distribution affects authentication, packaging, and
  access controls. No shared endpoint is implemented.
- Real repository roots are explicit configuration, not guessed from existing
  project memory. No recurring scan has been enabled.
- Visual direction and UI technology remain unselected. Before a material UI build,
  use the owner's sequential visual/technology selection checkpoints.
- Remote evidence, LOC, native adapters, attention rules, product memberships and
  background operation follow separate slices; this command does not imply they exist.

## Relevant Git references

- [Status porcelain and background index refresh](https://git-scm.com/docs/git-status)
- [Filesystem monitor compatibility](https://git-scm.com/docs/git-config/2.43.1)
- [Optional locks and lazy-fetch controls](https://git-scm.com/docs/git)

Documentation informs the safeguards. Fixture results establish only the bounded
behaviors actually exercised in this environment.
