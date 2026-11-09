# Local change insights

Local change insights answers two questions on demand:

1. Which captured source changes are present in the target's current contents,
   and which still need review?
2. Where did the scan find an identical saved version of a changed file?

Open the live dashboard, choose an observed local repository in **Local change
insights**, choose a source and target, and run the inspection. Source choices
include branches, stashes (working and staged snapshots), working files, and
staged files. Staged files are a
separate choice because staged edits can differ from both HEAD and the current
working file. Targets are locally available branch refs; remote-tracking refs
are cached local information. Inspection does not contact a remote server.

## Interpret the evidence

**Present** describes matched content, not tested behavior, a merged PR, a
deployment, or a recommendation to delete anything. **Remaining** identifies
source changes not represented by the comparison. **Partial** and **Uncertain**
keep incomplete or ambiguous evidence visible. Read each file's explanation and
the report's coverage warnings before drawing a conclusion.

An identical saved file version is useful preservation evidence. Its absence
does not prove the edits are unique: the same edits might exist in a file with
other differences, an uninspected revision, an excluded location, another clone,
or an external backup. The scan does not verify remote storage or backups. It
does not claim a file is the only remaining copy or that cleanup is safe.

Branch comparison needs an identifiable change boundary. A source already in
the target's ancestry may have been reverted or superseded later. When the
original intended changes cannot be established, the app refuses a definitive
remaining-work conclusion instead of treating an empty fork diff as success.
Stashes provide their own recorded base. Shallow, unavailable, unsupported,
oversized, and ambiguous evidence is qualified rather than counted as clean.

The result is a dated observation. Run another inspection after editing files,
staging changes, moving refs, or changing the comparison. Changed or removed
selections invalidate in-flight results. Results stay in browser memory and are
not added to observation history, static reports, or **Export JSON**.

## Read-only boundary

The scanner reads only a registered local repository and its registered
worktrees. It does not create commits, refs, Git objects, temporary indexes,
worktrees, or stash entries. It does not fetch, apply patches, stage, merge,
reset, clean, or run repository code. Repository filters, external diff tools,
text conversion, and automatic object downloads must not run during inspection.
Working-file reads reject unsupported links and special files.

Inspections have explicit time, command, output, file, and saved-location limits.
Only one inspection runs at a time in a dashboard process. A capped or interrupted
scan must expose incomplete evidence; it cannot turn that into a negative-copy
guarantee. Configured path exclusions apply to the analysis. No file contents or
patch excerpts are returned to the browser.

## Why compare current contents?

Ancestry alone misses squash and cherry-pick adoption and can remain true after
a revert. Historical patch matching recognizes repeated patches but cannot
establish that their effect survives in the target today. This feature therefore
compares captured source changes with the current target content and keeps
unsupported cases uncertain. It does not attempt to prove semantic equivalence.

The first implementation prioritizes explicit, inspectable evidence. It does
not yet locate missing companion functions across stashes, warn about every
reintroduced reverted change, or reconstruct unrecorded edits from before a
reset. Those are separate proposed features.
