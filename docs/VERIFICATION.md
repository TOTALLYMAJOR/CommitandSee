# Local verification — November 5, 2026

Scope: `/home/administrator/projects/work-visibility`, initial `main` branch,
uncommitted implementation. This record concerns local source and disposable
fixtures only. No project monitoring, service installation, push or deployment
was performed.

## Observed checks

| Check | Result |
| --- | --- |
| `python3 -B -m unittest discover -s tests -q` | 23 tests passed; latest observed run 6.747 seconds |
| `python3 -B -m unittest discover -s starter -p test_wale_visibility.py -q` | 43 tests passed |
| `sha256sum -c CHECKSUMS.sha256` in `starter/` | All 15 listed files matched |
| Subprocess CLI snapshot → repeat → edit → snapshot → read-only history | Passed; unchanged repeat added no transitions, edit added one |
| Delegated `demo` and historical `report` commands | Passed offline; demo labeled synthetic |
| Original downloaded ZIP digest recheck | Unchanged: `e0df749c07486a290abadc7427c312c540cbd3b1bd7f3ee277bc81eb9c5c7d4a` |

One disposable clone with one tracked file took 0.1962, 0.2066, and 0.199 seconds
for three local observations. These are measurements for that tiny fixture in
this session, not estimates for real repositories or a portfolio latency guarantee.

## Local fixture coverage

Edit/stage/commit states; local non-current branch visibility; linked-worktree
deduplication; separate independent clones; detached, unborn and bare repositories;
shared stash enumeration; missing/prunable worktrees; real merge conflict; rename,
space/newline and invalid UTF-8 filenames; binary untracked inventory; explicit
submodule-content coverage gaps; partial-clone refusal; content-filter refusal;
inherited Git environment isolation; output budget; timeout kill path; bounded
retry for a mid-scan change; continued partial state for repeated changes;
preservation of cheap worktree inventory after stash failure; persisted identities,
first-seen and last-success values; unchanged-poll deduplication; root-gap recovery;
storage exclusion from monitored trees/common directories; read-only history.

The executable fsmonitor fixture also configures external diff and textconv
commands. Its marker was absent after observation. Repository file hashes, file
modification times and modes were unchanged, including index, configuration and
refs. The content-filter fixture returned unavailable coverage and did not execute
the configured command. These fixtures are bounded evidence, not a general sandbox
against arbitrary concurrent hostile repository mutation.

## Graph boundary

Verify tier used the archive graph first, then the exact new repository graph
`home_administrator_projects_work_visibility_main`, generation
`2026-11-05T16:38:22Z`. The graph identified `main` at the physical root above;
there was no HEAD because this is an initial, uncommitted repository. Coverage
checks for the new Python modules, local tests, original collector, README and
design brief reported metadata matches with no recorded material issue. Expected
`.git` exclusion does not establish a source gap. Coverage is best effort; no
exhaustive absence or complete-impact claim is made. This verification document
was written after that graph generation.

## Not established

Windows-native execution, actual owner-repository scan cost, live authenticated
GitHub transport, publication/ancestry correctness, task binding, native receipts,
LOC accuracy, multi-product deduplication, attention policies, background lifetime,
browser accessibility/visual acceptance, CI execution, external publication, or
production readiness. Original dated GitHub exports remain historical.
