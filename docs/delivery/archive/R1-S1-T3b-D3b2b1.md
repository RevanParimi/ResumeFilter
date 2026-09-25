# R1-S1-T3b-D3b2b1 - Report erasure after interrupted screening

Status: done (2026-09-23). Parent: [D3b2b](R1-S1-T3b-D3b2b.md).

## Acceptance and design

Trigger: a batch report saves, then the worker exits before completion (or
between failed completion rollback and cleanup). Report-only erasure currently
leaves the private resume reference retryable and recovery creates a new report.

- Saving a batch report must atomically bind its private retry reference to
  report erasure. Deletion removes retry capability even with no worker cleanup;
  the surviving candidate/resume and unrelated tenants remain intact.
- Lost leases, deleted batches, erased/swept retry input or a different tenant
  cannot save an abandoned batch report. Binding and report save roll back
  together. Stale input cannot restore an erased reference.
- Ordinary failures/recovery retain exact-resume retry while the report/input
  survives. Preserve completed anonymous counts/scalars, public fields and TTL.
- Migration preserves existing input without guessing historical report links;
  populated upgrade/downgrade/upgrade preserves surviving references and cannot
  restore erased ones. No migration or cleanup on working storage.

Use a nullable CASCADE report FK on the existing private input table and a
before-commit callback in report save. No new public linkage, inferred identity,
consent change or UI change. Earlier unresolved and legacy input is D3b2b2.

## Validation plan

Red/green process interruption and rollback-to-cleanup regression; two tenants,
lost lease, erased/swept reference, ordinary retry, completion-first, transaction
rollback. Controlled SQLite/PostgreSQL connections, PG deletion lock inspection,
populated migration round trip and schema drift. Real migrated HTTP/worker exit/
restart on both backends, full pytest, compilation, bindings and diff self-review.

## Implementation and self-review

Migration 0025 adds a nullable, indexed report CASCADE FK to the private input
table. Report save flushes and invokes the optional callback before committing;
screening binds only a surviving tenant-owned input under the current lease,
with the report and resume naming the same candidate. A missing association
rolls back the new report. The item lock precedes the input update, matching
completion. Existing non-batch report saves retain their call contract.

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus this session's
report store diff and screening diffs against saved starting files; also new
migration, regressions, updated 0024 migration test sequence and scratch smoke.
Specification review covered interruption on both sides of rollback, ordinary
retry, tenant ownership, migration preservation and unchanged completion/TTL.
Correctness review traced callback rollback, FK deletion ordering, replaced
leases, batch deletion, erasure/sweep during evaluation, unrelated constraints
and historical unlinked records. No acceptance-blocking findings remain in this
scope. This is self-review, not independent review or live-provider validation.

Validation setup corrections: the older 0024 round-trip test must now also
downgrade/upgrade 0025; its initial failure was a stale-schema test fixture.
The first scratch smoke stopped after eight checks because its parent-process
eraser lacked organization/authorship ORM metadata imports. Added the imports;
no application change was needed for either setup issue.

## Commands and evidence

Commands run from the project root (all database validation uses scratch storage):

```powershell
.resume/Scripts/python.exe -m pytest -q tests/test_screening_report_input.py --tb=short
.resume/Scripts/python.exe -m pytest -q tests/test_screening_report_input.py tests/test_screening_ingest.py tests/test_screening_durable_input.py tests/test_migrations.py --tb=short
.resume/Scripts/python.exe -m pytest -q tests/test_screening_report_input.py tests/test_screening_durable_input.py --tb=short
.resume/Scripts/python.exe -m pytest -q tests/test_screening_report_input.py tests/test_screening_durable_input.py tests/test_report_store.py tests/test_report_erasure_concurrency.py tests/test_screening_erasure_concurrency.py tests/test_screening_ingest.py tests/test_migrations.py --tb=short
.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3b2b1.py
.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3b2b1_postgres.py
.resume/Scripts/python.exe -m pytest -q --tb=short
.resume/Scripts/python.exe -m py_compile src/app/reports/store.py src/app/screening/models.py src/app/screening/store.py src/app/screening/service.py src/app/screening/ingest.py alembic/versions/0025_screening_input_report.py tests/test_screening_report_input.py tests/test_screening_durable_input.py scripts/smoke_r1_s1_t3b_d3b2b1.py
git diff --check
node scripts/check_ui_bindings.js
```

- Red: **2 failed**, 1 warning, 5.20s; both interrupted report cleanup cases
  left the private input reference behind after report-only erasure.
- Initial focused: 1 stale-schema migration fixture failure, 44 passed,
  23 skipped, 16 warnings, 32.03s. Corrected sequence as described above.
- Expanded SQLite focused: **95 passed, 56 skipped**, 19 warnings, 86.57s.
  The final extra unrelated-integrity regression is included in the full suite.
- PostgreSQL runner focused: **306 passed, 12 skipped**, 23 warnings, 443.78s.
  All PostgreSQL variants passed; skips are SQLite variants of PG lock inspection.
  Controlled erase-first and binding-first orderings passed, including observed
  report deletion blocked on the binding transaction. Populated 0024/0025
  downgrade/upgrade tests and the migration chain up/down/up passed.
  Disposable PostgreSQL cluster stopped cleanly: pg_ctl exit 0, 31.81s.
- Migrated HTTP/worker exits/restarts: **19/19 on each backend**. Real worker exit 71
  before completion and exit 72 after rollback, then erasure/recovery/restart;
  report deletion through the production store (there is no report-delete HTTP
  route), other-tenant HTTP denial, surviving resumes and no recreated report.
- Full SQLite pytest: **2317 passed, 105 skipped**, 44 warnings, 474.80s.
  Skips: 93 unconfigured PostgreSQL variants and 12 SQLite variants of PG lock
  inspection. No full PostgreSQL suite claimed.
- Compilation, tracked diff whitespace and new-file whitespace passed. Attempted
  Node binding check unavailable (Node not installed); no frontend/public-field
  changes, so no browser execution is required or claimed.

Local logs: `.pytest_cache/r1-s1-t3b-d3b2b1-{red,initial,focused-initial,focused,full,smoke-sqlite}.txt`
and `r1-s1-t3b-d3b2b1-pg-*.txt`. Local portable-PG runner is an ignored artifact;
no deployed migration, full PostgreSQL suite or live-provider claim.

Next: **R1-S1-T3b-D3b2b2**, unresolved/failed-first-ingest and historical input.
D3b2b/D3b2/D3b/D3/D/T3b/T3/F05/R1-S1-Q remain open. Working data/veritas.db
SHA256 is unchanged: `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
