# Contributing to CommitandSee

CommitandSee helps people understand Git history and unfinished local work.
Useful contributions include reproducible bug reports, clearer evidence labels,
accessibility improvements, and fixes that preserve the observer's boundaries.

## Report a problem

[Open an issue](https://github.com/TOTALLYMAJOR/CommitandSee/issues) with:

- What you expected and what happened.
- Your OS, Python and Git versions, and whether you used WSL.
- The command and smallest disposable repository that reproduce it.
- Relevant errors or screenshots with private paths, repository names, tokens,
  and other sensitive information removed.

Do not attach your real repository, local configuration, observation history,
or exports unless you have checked every included value. A synthetic fixture is
usually enough. For a suspected security issue, use GitHub's private reporting
option if available; otherwise ask for a private contact without posting an
exploit or sensitive details in a public issue.

## Work locally

The application needs Python 3.11+ and Git 2.37+. It uses Python's standard
library and bundled browser assets; Node and Playwright are development tools
only. Fork the repository, create a branch, and make a focused change.

```bash
git clone https://github.com/YOUR-USERNAME/CommitandSee.git
cd CommitandSee
python3 -B -m unittest -v
python3 git_dashboard.py demo --output /tmp/commitandsee-demo.html
```

For a live check, use a disposable Git repository. Keep configuration, state,
and output files outside its primary and linked worktrees. Never use a user's
working repository to reproduce a mutating Git operation.

## Preserve the evidence model

- A missing observation is unknown, not zero or clean.
- Cached upstream refs do not establish current remote or PR status.
- Local observation must preserve checkout and Git metadata. Public and
  authenticated GitHub collection may fetch only into the application's own
  caches; credentials must never enter repository records, exports, or logs.
- Repository removal stops monitoring; it must not erase files, history, or
  downloaded caches.
- Keep subprocess time and output bounds, safe request handling, and config
  containment intact. Add a regression that fails before a behavioral fix.
- Keep the interface usable by keyboard, on narrow screens, and with reduced
  motion. Preserve the existing visual direction for ordinary fixes.

## Validate and submit

Run the Python suite above. For browser changes, run
`node --test --test-concurrency=1 test_dashboard_browser.cjs test_github_browser.cjs test_local_insights_browser.cjs`
using an existing Playwright installation; the README describes optional
environment settings. Tests use synthetic or disposable data. Record which
engines actually ran and any skipped checks. Provider fixtures do not prove a
real GitHub account authorization or private-history download.

If you change `dashboard.html`, regenerate the bundled example:

```bash
python3 git_dashboard.py demo --output demo.html
```

Update documentation with changed behavior. After the final edit, regenerate
the entries in `CHECKSUMS.sha256`, include newly shipped files, and verify with
`sha256sum -c CHECKSUMS.sha256` on systems providing that command. Do not include
private data, local caches, or generated test artifacts in the manifest.

Open a pull request explaining the trigger, the resulting behavior, and the
checks you actually ran. Mention remaining limitations. Passing fixture tests
does not establish production readiness or human acceptance. Large features
benefit from an issue describing the user problem and trade-offs first.
