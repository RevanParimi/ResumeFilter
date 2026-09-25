# R1-S1-T3a-V1 - PostgreSQL feature timestamp compatibility

Status: done (2026-09-21). Validation prerequisite for [R1-S1-T3a](../tasks/R1-S1-T3a.md).
Finding: F03 residual discovered during the PostgreSQL validation gate.

## Behavior and acceptance

FeatureStore stripped UTC tzinfo before binding to timezone-aware columns.
PostgreSQL interpreted those naive values in its session timezone, shifting
feature cuts/materialization times and emptying search/match/dashboard pools.
The prior full log (9 failed, 2192 passed, 32 warnings, 1150.32s) was recovered
from `.pytest_cache/r1-s1-t3a-pg-suite.txt`; the old handoff had missed it.

Removed `_key_dt`; existing `as_utc` now normalizes all six write/equality/cutoff
bindings without stripping tzinfo. SQLite drops tzinfo from normalized UTC
values and restores UTC on read. No scoring, consent, snapshot selection,
schema or UI contract change. Existing user records were not rewritten.

| Acceptance | Final evidence |
|---|---|
| Preserve cut/materialization instants on SQLite and PostgreSQL UTC/non-UTC | Six new cases: equivalent UTC/offset/naive inputs, microseconds, upsert identity; all pass with PostgreSQL configured |
| Keep newest, partial-refresh and historical pools consistent | Store and existing matching/dashboard/materialization/search API tests pass |
| Preserve erasure, T3a concurrency and defined API refusals | All T3a focused cases pass; real erasure HTTP/restart 19/19 |
| Validate actual application persistence and restart | New feature HTTP/restart 12/12 on SQLite and PostgreSQL Asia/Calcutta |

## Runs and reproducible commands

| Run | Result |
|---|---|
| Red PostgreSQL focused | 11 failed, 82 passed, 2 warnings, 123.60s: original nine failures plus two new Asia/Calcutta cases |
| Final SQLite focused (first five files below) | 28 passed, 4 PostgreSQL skips, 1 warning, 7.58s |
| Final PostgreSQL focused (all files below) | 93 passed, zero skips, 2 warnings, 79.17s |
| Full SQLite | 2198 passed, 10 PostgreSQL skips, 32 warnings, 663.66s |
| Full PostgreSQL | 2208 passed, zero skips, 32 warnings, 1431.51s |
| Feature HTTP/restart, final isolation rerun | 12/12 on each database; public schema stayed empty and owned schemas were cleaned |
| T3a erasure HTTP/restart | 19/19 on migrated scratch SQLite |
| PostgreSQL migration up/down/up | Passed; schema teardown and cluster shutdown exited 0 |

Focused command uses `.resume/Scripts/python.exe -m pytest` with these files,
in this order, followed by `-q --tb=short`:

```text
tests/test_feature_timestamps.py tests/test_feature_store.py
tests/test_features_materialize_api.py tests/test_dashboard_api.py
tests/test_talent_search_api.py tests/test_report_erasure_concurrency.py
tests/test_report_store.py tests/test_report_cascade.py
tests/test_portal_service.py tests/test_portal_api.py
tests/test_screening_ingest.py tests/test_flywheel_retention.py
```

Full command: `.resume/Scripts/python.exe -m pytest -q --tb=short`, once with
DEE_TEST_DB_URL set to the new disposable PostgreSQL cluster and once unset.
Providers disabled and test settings isolated in the child environments.
Feature journey: `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3a_v1.py`
(with `--postgres` for PostgreSQL); T3a journey:
`.resume/Scripts/python.exe scripts/smoke_r1_s1_t3a.py`.

Local orchestrators actually run: `.resume/Scripts/python.exe
.pytest_cache/run_r1_s1_t3a_v1_postgres.py` (also `--red` before the fix), and
`.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3a_v1_journeys.py` for final
smoke isolation. The red diagnostic invoked pytest.main with the focused list
and `-q --tb=short -vv -s -p no:faulthandler`, plus periodic stack dumps. Two
silent startup attempts and an extra collection diagnostic were stopped and
are not test results; stack traces showed filesystem reads during imports.

Logs in `.pytest_cache/`: `r1-s1-t3a-v1-pg-{red,focused,suite,migrations}.txt`,
`r1-s1-t3a-v1-sqlite-{suite,erasure-smoke}.txt`, and final
`r1-s1-t3a-v1-journey-{postgres,sqlite}-smoke-final.txt`. Earlier feature smoke
runs also passed; the final reruns cover the reviewed isolation fix.

## Self-review and environment

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus feature-store,
new timestamp regressions and smoke. Specification review mapped every criterion
above to final evidence. Correctness review traced all bindings, read conversion,
view/version predicates, CASCADE and materialize/context/search/match/board
callers. Existing consent/scoring policy and historical user data are preserved.

Review findings in the new smoke setup: URL query encoding conflicted with
Alembic interpolation, and inherited URL `options` could override its owned
schema. Fixed by passing schema/timezone through child PGOPTIONS and removing
URL options. Final real journeys deliberately supplied `search_path=public`,
then verified public candidates remained zero and owned schemas were gone.
No unresolved acceptance-blocking findings. Same-agent self-review only.

Reviewed feature-store SHA256:
`683C0A4133903832BAF3CAC69E57915A4A4369B7A1BF25D2F30BFDCD0E33BD16`.
Final smoke SHA256:
`C62676FA3E0983A3AB03D5DD3558804A39F3FF686B262D7087F1CB4105A542BF`.
Report-store and shared-fixture hashes match T3a's prior review. Compile,
whitespace, local documentation links/status consistency and
`git -c core.safecrlf=false diff --check` passed. Working `data/veritas.db` SHA256
remained `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

Restored the missing matching CPython 3.13.11 base from the signed
[Python installer](https://www.python.org/downloads/release/python-31311/),
retaining .resume/dependencies. Restored portable PostgreSQL 18.6 with the same
archive SHA256 recorded in T3a; random loopback ports/passwords, new disposable
clusters, no Windows PostgreSQL service or .env changes. Runtime metadata:
`.pytest_cache/r1-s1-t3a-v1-pg-runtime.json`. Remote credentials were not rechecked.

## Handoff and limits

V1 is done and closes T3a's remaining validation gate. Next task: **R1-S1-T3b**
in a separate chat. Parent T3, F05 and R1-S1-Q remain open. Historical feature
timestamps written under non-UTC PostgreSQL may still be shifted; repair needs
an explicit policy, not a guessed timezone. No user-data/legacy-file cleanup,
browser execution, independent review or live-provider validation claimed.
