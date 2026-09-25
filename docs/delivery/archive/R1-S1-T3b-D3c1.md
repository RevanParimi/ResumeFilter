# R1-S1-T3b-D3c1 - Feature materialization consent audit after erasure

Status: done (2026-09-23). Parent: [D3c](../tasks/R1-S1-T3b-D3c.md).

## Acceptance and scope

Trigger: candidate erasure after feature context loading or after the consent
check but before feature.materialize audit insertion. Current code raises a raw
LookupError/IntegrityError, aborting the batch. The erased subject must produce
no audit or vector; materialize_candidate returns None and the existing admin
POST /features/materialize counts it as skipped while continuing other subjects.

- Cover absent subject, erased-before-audit-flush and audit-commit-before-erasure
  on isolated SQLite/PostgreSQL with controlled competing connections. Verify
  foreign-key ordering and cascade cleanup, retry and unaffected second subject.
- Preserve direct materialization_consent's LookupError compatibility, using a
  specific missing-subject refusal the orchestrator can distinguish from other
  errors. Roll back before checking disappearance after an integrity error.
- Unrelated database/lookup failures must propagate; do not falsely classify them
  as withheld consent or successful materialization. No SQL/private payload logs.
- Preserve existing allowed/withheld decisions, masking, timestamps, API fields,
  admin authorization and unknown-candidate skip semantics. Test both decisions
  and operator/portal erasure, plus migrated HTTP/restart persistence.
- No schema migration, frontend asset/contract change, scoring/consent-policy
  change, training export or matching fix in this child. Required: red/green,
  focused/full pytest, PG ordering and migration up/down/up, HTTP subprocess
  journey, diff self-review, documentation. Browser not required for unchanged
  visible contract; API response behavior must be exercised.

Use existing candidate CASCADE foreign keys and narrow error translation, not
new locking/schema machinery or general audit abstractions. Audit-first may
return the decision, but subsequent erasure removes its audit and the existing
feature-store guard refuses later persistence (D1). Cross-store review is D3d.

## Evidence

- Red: `.resume/Scripts/python.exe -m pytest -q tests/test_materialization_audit_erasure.py --tb=short`:
  **10 failed, 8 passed, 7 skipped**, 1 warning, 7.92s. Intended failures:
  raw FK errors at audit flush and HTTP 500 before/at audit for allowed/withheld
  subjects. Existing audit-first paths passed.
- Focused command: `.resume/Scripts/python.exe -m pytest -q tests/test_materialization_audit_erasure.py tests/test_ledger_store_materialize_consent.py tests/test_features_materialize.py tests/test_features_materialize_api.py tests/test_feature_erasure_concurrency.py tests/test_ledger_store.py --tb=short`:
  **59 passed, 13 skipped**, 1 warning, 9.27s. Earlier command had a wrong
  test filename and collected no tests; corrected, not counted as a defect.
- `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3c1.py`: **19/19** on
  migrated scratch SQLite. Real app/HTTP, six allowed/withheld boundary cases,
  unchanged admin-only access, retry and restart audit/vector inspection.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3c1_postgres.py`:
  PostgreSQL 18.6 focused tests **104 passed, 1 skipped**, 16 warnings, 108.36s.
  Twelve files cover the new races, ledger/materialization/vector stores, export,
  training callers, jobs API and migrations. Skip is the SQLite variant of PG
  lock inspection. Observed pg_blocking_pids proves erasure waits for the audit
  FK lock; delete-first and commit-first orderings passed. Full migration chain
  up/down/up passed on scratch storage; no new migration in this child.
- PostgreSQL migrated HTTP/restart **19/19** via the same smoke script with
  `--postgres` (runner supplies only a disposable database). Scratch cluster
  stopped cleanly: pg_ctl exit 0, 11.57s. Both backend journeys use synthetic
  separate-session erasure at controlled hooks, not worker-crash simulation.
- `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2353 passed,
  123 skipped**, 44 warnings, 277.01s, on the final reviewed source/test state.
  Skips are unconfigured PG variants and SQLite variants of PG lock inspection.
  No full PostgreSQL suite or live-provider validation claimed.
- Compilation passed:
  `.resume/Scripts/python.exe -m py_compile src/app/ledger/store.py src/app/features/materialize.py tests/test_materialization_audit_erasure.py scripts/smoke_r1_s1_t3b_d3c1.py`.
  `git diff --check`, new-file whitespace and local documentation links passed.
  `node scripts/check_ui_bindings.js` unavailable (Node not installed). No frontend
  assets or visible API contract changed; browser execution not claimed.


## Diff self-review (2026-09-23)

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus this session's
ledger/store.py, features/materialize.py, new regression file and HTTP smoke.
Start copies are in `.pytest_cache/d3c1-start`; pre-existing changes preserved.
Specification review: exact missing-subject LookupError subtype, rollback and
fresh lookup, narrow orchestrator cancellation, survivor accounting and unchanged
consent masking each map to focused regressions. Correctness review checked
CASCADE ordering, both commit orderings, retry, unrelated NOT NULL/LookupError
propagation, no new payload logging, and the existing D1 vector guard after an
audit-first erasure. No new schema/locks/general audit abstraction is needed.
No acceptance-blocking finding remains; required checks completed on this state.
This is self-review, not independent review. No live-provider validation claimed.


Logs: `.pytest_cache/r1-s1-t3b-d3c1-*.txt`. The local PG runner uses the ignored
portable runtime record `.pytest_cache/r1-s1-t3a-v1-pg-runtime.json`; this is local
evidence, not a portable setup guarantee. No .env edits or service registration.
Working data/veritas.db remains SHA256
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Existing uncommitted work preserved. No working-data migration or deployment.
Exact next task: **R1-S1-T3b-D3c2** (training-label audit/export erasure).
D3c/D3/D/T3b/T3/F05/R1-S1-Q remain open.
