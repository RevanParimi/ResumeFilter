# R1-S1-T3b-D3c2 - Training-label audit/export erasure

Status: done (2026-09-23). Parent: [D3c](../tasks/R1-S1-T3b-D3c.md).

## Acceptance and scope

Trigger: cached vectors/outcomes survive in a training builder while their
candidate is erased, before audit insertion/commit or before builder handoff.
Today the audit raises an IntegrityError, or audit=False emits stale data.
The builder must omit erased subjects entirely (including withheld vectors),
continue surviving subjects, and export only the resulting examples.

- Audit erasure raises a specific LookupError subtype after rollback and a fresh
  missing-subject check; unrelated integrity/lookup failures propagate. Existing
  successful audit returns None and keeps its fields and allowed/withheld meaning.
- Cover absent candidates, cached labels, before-flush and after-commit erasure,
  erasure of an earlier example while building a later one, and audit=False.
  Final existence checks apply with or without auditing. Retry must stay omitted.
- Preserve snapshot consent policy, withheld short-circuit (no outcome reads),
  strict post-as_of label cutoff, survivor data and CSV/parquet columns/types.
- Exercise SQLite and PostgreSQL competing connections and observed FK locking;
  full migration up/down/up, focused/full pytest, migrated subprocess build/export
  and restart inspection, static checks and recorded diff self-review.
- No schema/UI/API route changes. Training currently has only a library builder
  and smoke caller, not a production HTTP export route. Pure example/CSV/parquet
  serializers have no store; final per-subject existence reads exclude erasures
  visible at each read, not a lock across later checks/file delivery or revocation
  of already returned snapshots/files.
  Current-consent changes remain R1-S2-T2; matching disclosure remains D3c3.

Use the existing CASCADE FK for audit ordering and narrow error translation.
No new lock protocol, schema, serializer dependency or generalized audit wrapper.

## Evidence

- Red: `.resume/Scripts/python.exe -m pytest -q tests/test_training_audit_erasure.py --tb=short`:
  **16 failed, 1 passed, 19 skipped**, 15.98s. Raw FK failures at insertion/retry
  and erased candidates retained in returned examples reproduced the defect.
- Focused: `.resume/Scripts/python.exe -m pytest -q tests/test_training_audit_erasure.py tests/test_ledger_store_audit_training_label.py tests/test_features_build_training_set.py tests/test_features_training_export.py tests/test_features_build_label.py tests/test_features_training_schema.py tests/test_materialization_audit_erasure.py tests/test_ledger_store.py --tb=short`:
  **73 passed, 26 skipped**, 1 warning, 30.39s. An earlier command named a
  nonexistent test_features_training_label.py and collected no tests; corrected.
- Migrated journey: `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3c2.py`:
  real HTTP setup, subprocess library build/export, restart HTTP inspection;
  **3/3 outer checks and 13/13 worker checks**, with 12 allowed/withheld boundary
  scenarios and persisted vector/audit inspection. No production training HTTP
  route exists. Repeated after adding explicit worker-log capture, same result.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3c2_postgres.py`:
  PostgreSQL 18.6 focused **151 passed, 2 skipped**, 16 warnings, 177.85s.
  Includes training/materialization/ledger/vector/export callers and migrations;
  skips are SQLite variants of PG lock inspection. Controlled competing sessions
  cover delete-first/audit-first ordering; pg_blocking_pids observes the audit FK
  blocking erasure. Full migration chain up/down/up passed on disposable storage.
  PostgreSQL migrated journey **3/3 outer and 13/13 worker checks**, 28.56s,
  via the same smoke script with `--postgres`; cluster stopped cleanly (exit 0,
  20.34s). Neither backend journey simulates a worker crash. Logs use
  `.pytest_cache/r1-s1-t3b-d3c2-*.txt`; subprocess artifact directory contains
  `worker.log`, synthetic CSVs and `server.log`.
- `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2371 passed,
  142 skipped**, 44 warnings, 384.53s, on the final reviewed code/tests. Skips
  include unconfigured PG variants and SQLite variants of PG lock inspection.
  No full PostgreSQL suite claim.
- `node scripts/check_ui_bindings.js` unavailable (Node not installed). No UI
  or visible API contract changed; no browser execution or live-provider claim.
- PyArrow is absent: actual CSV rows and the parquet missing-dependency contract
  passed. No actual parquet file round trip is claimed; the regression also
  validates rows when run in a PyArrow-enabled environment.
- `.resume/Scripts/python.exe -m py_compile src/app/ledger/store.py src/app/features/training.py tests/test_training_audit_erasure.py scripts/smoke_r1_s1_t3b_d3c2.py`,
  `git diff --check`, changed-file whitespace and local documentation links passed.

## Diff self-review (2026-09-23)

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus this session's
ledger/store.py, features/training.py, new regression file and subprocess smoke.
Start copies in `.pytest_cache/d3c2-start` distinguish pre-existing changes.
Specification review mapped narrow erasure refusal, survivor continuation,
audit=False, withheld no-read behavior, cached labels, later-example erasure and
CSV/parquet contract to behavioral checks. Correctness review traced all builder
and audit callers (library tests and smoke_s44; no production route), fresh
sessions after rollback, CASCADE ordering, unchanged stored consent/cutoff policy,
unrelated NOT NULL/LookupError propagation and read-only serializers.

Review finding (documentation, FEATURES.md S4.4 export): the claim that a file
can never leak overstates stored consent and snapshot erasure semantics. Replaced
with the actual stored-decision policy and explicit per-subject final-read/file
delivery limits. Each final check uses a new session, adding one existence query
per assembled example; it does not hold candidate locks or provide an atomic
whole-export snapshot. No schema or serializer coupling needed for this scope.
Worker stdout is explicitly captured for reproducible Windows evidence.
No acceptance-blocking finding remains. This is self-review, not independent
review. Required regression/database/journey checks completed on this state.

Working data/veritas.db remains SHA256
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Pre-existing uncommitted work preserved; no working-data migration/deletion or
deployment. Exact next task: **R1-S1-T3b-D3c3** (matching
disclosure audit/response race). D3c/D3/D/T3b/T3/F05/R1-S1-Q remain open.
