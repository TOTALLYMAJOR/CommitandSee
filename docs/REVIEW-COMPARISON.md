# Review regression comparison

Compared November 5, 2026, before publishing v0.1.0.

Input: `test_review_regressions.zip`, SHA-256
`af5c4b75bcc37175e1d2c8656bd51cdd8d3ea523cacfc3a46f1c7c097d6a3a04`.
It contains five tests, a supplied browser-results JSON, and `git_dashboard.py`.
That dashboard file is byte-identical to baseline `1c3f931`; it is not a fixed
implementation. Its SHA-256 is
`f792cb3ff324dd07d81cdb8075b6eb29b6220c16ef811a3bfb67b0ac8ceada38`.

## Independently reproduced results

The supplied tests were run alongside a copy of our baseline modules and fixture
helpers, in an isolated temporary directory. All five failed before correction.
All marker scripts and Git mutations were confined to disposable repositories.
No owner project scripts or credentials were involved.

| Added regression | Baseline observation | Correction |
| --- | --- | --- |
| GIT_CONFIG bypass of filter guard | A temporary config override concealed a configured clean filter; its fixture marker was written | Scrub GIT_CONFIG and temporary parameter/count/key/value overrides before both guard and measurement commands |
| Signature-display callback | A repository-configured verifier wrote its fixture marker during observation | Disable signature display in the observer Git command prefix |
| Root-commit churn | log.showRoot=false changed three real added lines into zero | Explicitly select root display for full-history metrics |
| Shallow-boundary churn | A depth-one clone reported 101 additions where full history proved one recent addition | Omit parentless line deltas in shallow histories; retain commit observations and partial coverage |
| Malformed saved state | A JSON array caused AttributeError during startup | Validate the top-level object before accessing schema fields; retain a recoverable warning |

The five supplied tests are retained as `test_review_regressions.py`. With the
corrections, all five and all 21 original tests passed together: **26 tests**
in 3.302 seconds. This is local fixture evidence, not proof of universal safety.

Shallow-history totals intentionally remain incomplete. No objects are fetched
to reconstruct missing parents, and the UI's existing partial-total qualification
remains in place. A full history still includes genuine root-commit deltas.

## Browser report boundary

The ZIP's `browser-results.json` records a synthetic demo inspection, including
responsive-width and tab/filter observations. It is supplied historical evidence,
not a fresh execution in this workspace. Its stale-flag observation was not
promoted into a new UI requirement or a passing freshness check. Our release
verification separately records actual local live-data and browser inspection.
