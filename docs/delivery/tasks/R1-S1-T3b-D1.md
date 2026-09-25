# R1-S1-T3b-D1 - Feature-vector writes racing erasure

Status: done. Parent: [D](R1-S1-T3b-D.md). Date: 2026-09-21.

Trigger: erasure commits after feature computation/vector lookup and before
insert/update flush. Before: database exception becomes HTTP 500. Intended:
upsert returns None for an erased candidate; materialization counts that item
as skipped and continues other candidates. Successful writes still return IDs.

Acceptance:
- Event-controlled SQLite/PostgreSQL connections exercise insert and update,
  delete-first/write-first orderings and stale retry. No erased vector survives;
  another candidate's vector remains unchanged.
- Rollback before fresh parent lookup; unrelated integrity/stale-row failures
  remain errors. No SQL parameters or feature payload in handled refusals.
- Real API batch accounting includes erased/missing IDs and surviving candidates;
  normal same-cut updates remain compatible.
- Migrated scratch HTTP materialize/erase/retry/restart journey, focused backend
  checks, PostgreSQL migration up/down/up, full pytest and recorded self-review.

Design: reuse candidate foreign-key cascade and ORM stale-row detection. No
schema, UI, scoring, timestamp or consent policy change. Computation-time consent
audit races are D3; ingest/fingerprints are D2. No browser/provider evidence
required for this persistence-only child.

Implementation: FeatureStore rolls back IntegrityError/StaleDataError and checks
the candidate afresh. Only an absent parent returns None. The route increments
skipped on that result and continues the batch. The existing FK remains the
retention boundary; successful write-before-delete can return its saved ID while
the subsequent cascade removes the row.

Self-review (2026-09-21): HEAD `9f2f6cd` plus feature store/route additions, new
concurrency tests and the extended feature HTTP smoke. Preserved the earlier UTC
binding changes in the store. Specification: insert/update/retry and batch
accounting map to behavioral regressions; all production upsert callers traced
with rg (the materialization route is the only caller). Correctness: rollback
precedes the parent read, deleted-vector/live-parent errors propagate, other
candidates survive, and no error payload is logged on handled erasure. Existing
admin-only access and same-cut timestamp tests remain in focused coverage.
No blocking finding remains within D1. Consent audit persistence happens before
upsert and remains explicitly D3; this is not whole-materialization race closure.
No independent review, browser execution or live-provider validation claimed.

Final evidence:
- Before fix: 8 failed, 2 passed, 6 PostgreSQL skips, 1 warning, 19.10s.
  Insert/update database errors, stale retry errors and four API HTTP 500s.
- Focused SQLite: 35 passed, 10 PostgreSQL skips, 1 warning, 25.23s.
  Includes unrelated NOT NULL/stale-row errors and recovery with a live parent.
- Focused PostgreSQL: 45 passed, zero skips, 1 warning, 92.08s. PostgreSQL 18.6,
  Asia/Calcutta server timezone; competing connections for insert/update in both
  orderings, stale retries and unrelated database failures. Timestamp fixture
  also explicitly covers UTC and Asia/Calcutta sessions.
- Migrated scratch HTTP/restart: 15/15 each on SQLite and PostgreSQL. Same/new-cut
  retries skip the erased candidate, update the survivor and keep search/board
  results correct after restart. PostgreSQL migration up/down/up and cluster
  shutdown passed. No schema/data migration introduced by this child.
- Full SQLite pytest: 2223 passed, 23 PostgreSQL skips, 42 warnings, 404.17s.
  No full PostgreSQL rerun claimed; the new database paths passed focused PG.
- Compilation, git diff whitespace and task/PI documentation link checks passed.

Commands (project environment throughout):
```
.resume/Scripts/python.exe -m pytest tests/test_feature_erasure_concurrency.py -q --tb=short
.resume/Scripts/python.exe -m pytest tests/test_feature_erasure_concurrency.py tests/test_feature_timestamps.py tests/test_features_materialize.py tests/test_features_materialize_api.py tests/test_talent_search_api.py tests/test_job_store_match.py tests/test_services_features.py -q --tb=short
.resume/Scripts/python.exe scripts/smoke_r1_s1_t3a_v1.py
.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d1_postgres.py
.resume/Scripts/python.exe -m pytest -q --tb=short
.resume/Scripts/python.exe -m py_compile src/app/features/store.py src/app/api/routes.py tests/test_feature_erasure_concurrency.py scripts/smoke_r1_s1_t3a_v1.py
git diff --check
```

Logs: `.pytest_cache/r1-s1-t3b-d1-{red,focused,smoke,suite}.txt` and
`r1-s1-t3b-d1-pg-{runner,focused,migrations,smoke,stop}.txt` there. The local PG
runner derives from the interview runner, uses the existing V1 runtime metadata,
creates/stops a fresh disposable cluster and invokes the focused command above
plus `scripts/smoke_r1_s1_t3a_v1.py --postgres`. No full PostgreSQL suite claimed.
HTTP smoke is a real sequential materialize/erase/retry/restart journey with
providers disabled; controlled races are pytest store/TestClient evidence.

Compilation passed. Attempted `node scripts/check_ui_bindings.js` could not run
because Node is unavailable on PATH; no binding/browser result is claimed.
No frontend asset or UI contract changed. Existing skipped-count response field
now also accounts for erasure at vector persistence.

Working `data/veritas.db` SHA256 remained
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Pre-existing uncommitted work was preserved. Next: **R1-S1-T3b-D2** only in a new
chat; D/D3/T3b/T3/F05 and R1-S1-Q remain open.
