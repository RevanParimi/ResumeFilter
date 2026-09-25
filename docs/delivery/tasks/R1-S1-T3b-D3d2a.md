# R1-S1-T3b-D3d2a - Report-only erasure before evaluation response

Status: done (2026-09-24). Parent: [D3d2](R1-S1-T3b-D3d2.md).

Trigger: report deletion commits after save but before response assembly while
candidate/resume survive (or standalone evaluation has no candidate). Before:
admin/org upload and standalone `/evaluate` return the erased report body.
Batch completion already refuses deleted reports, but shared ingest itself does
not. After: a fresh report lookup observes absence and refuses with `report_erased`;
HTTP returns 422 and batches use existing failed-item cleanup/retry semantics.

Acceptance:
- Check report existence after successful save in shared ingest and standalone
  evaluation. Keep candidate/resume refusal precedence in shared ingest; preserve
  evaluate=False, short text, successful report fields, tenant redaction and
  independent candidate/resume lifetime after report deletion.
- Cover all three HTTP doors, unrelated subjects/tenants, outcome cascade,
  duplicates/fresh uploads, batch refusal before completion and no retained retry
  capability. Unrelated store/provider errors must propagate, not become erasure.
- Controlled competing connections cover erase-before-response and response-first
  on SQLite/PostgreSQL. Explicitly document/test the snapshot boundary: deletion
  after the final read can still leave a delivered snapshot, with no durable row.
- Reuse current report-store `get`, refusal handling and schema; no locks,
  tombstones, new response shape, frontend changes or retention/consent policy.
- Required: meaningful red/green, focused/full pytest, migrated real HTTP/restart
  on scratch SQLite/PostgreSQL, migration up/down/up, diff self-review, compilation,
  whitespace and documentation checks. Synthetic providers only. Browser checks
  do not apply to this backend-only reuse of existing error handling.

Other erasure ordering, sources and login state remain D3d2b/c/d. This child
cannot close D3d2/D3d/D3/D/T3b/T3/F05/R1-S1-Q.

## Diff self-review and evidence

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus the bounded changes
against `.pytest_cache/d3d2a-start`: two existence checks in routes.py/ingest.py,
new report-response regressions/HTTP runner and SCREENING.md. Existing changes
were preserved. Specification review maps all doors, batch refusal, report-only
lifetime, unrelated errors and both ordering/snapshot limits to behavioral tests.
Correctness review traced store session closure, candidate/resume precedence,
original org redaction, report/outcome cascade, existing batch scrub/retry codes
and fresh-request permission. No lock or policy change; no new exception catch
that could swallow unrelated failures. No acceptance-blocking finding remains
in this child. This is self-review, not independent review.

- Red: `.resume/Scripts/python.exe -m pytest -q tests/test_report_response_erasure.py --tb=short`:
  **14 failed, 3 passed, 2 skipped**, 1 warning, 7.02s. Stale HTTP 200 on all
  three doors, no ingest refusal and absent final lookup reproduced. An initial
  missing-provenance outcome fixture was corrected before this red run.
- Focused: `.resume/Scripts/python.exe -m pytest -q tests/test_report_response_erasure.py tests/test_ingest_response_erasure.py tests/test_screening_report_input.py tests/test_screening_ingest.py tests/test_candidates_api.py tests/test_api.py --tb=short`:
  **117 passed, 17 skipped**, 2 warnings, 31.43s. PostgreSQL fixture variants
  require a configured disposable connection.
- `.resume/Scripts/python.exe -m py_compile src/app/api/routes.py src/app/screening/ingest.py tests/test_report_response_erasure.py scripts/smoke_r1_s1_t3b_d3d2a.py`
  and `git diff --check` passed. `node scripts/check_ui_bindings.js` was attempted
  but Node remains unavailable. No frontend assets/handlers changed or browser
  execution claimed.
- Initial SQLite HTTP run: 28/29, only the final raw SQL JSON-null inspection
  failed; SQLite returns JSON text while PostgreSQL decodes JSON. Normalized
  that inspection without changing production.
- `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3d2a.py`: final SQLite
  migrated HTTP/restart **29/29**. Both uploads and standalone evaluation, short/
  long inputs, report erasure/fresh recovery, late response snapshots, unrelated
  failure/recovery, batch cleanup/no retry, tenant denial, unauthorized access
  and restart SQL inspection all passed.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3d2a_postgres.py`:
  PostgreSQL 18.6 focused **172 passed, 1 skipped**, 17 warnings, 210.82s.
  Includes the six focused files above plus screening API, report erasure
  concurrency and migrations. The one skip is SQLite's PostgreSQL-only lock
  inspection variant. Full migration up/down/up, PostgreSQL migrated
  HTTP/restart **29/29**, and clean disposable cluster shutdown passed. No full
  PostgreSQL suite claimed.
- `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2463 passed, 163
  skipped**, 44 warnings, 377.56s, on the final reviewed source/tests.
- Documentation check: `.resume/Scripts/python.exe .pytest_cache/check_d3d2a_docs.py`;
  links/IDs/status/whitespace passed across **12 documents**. Working DB
  SHA256 remains `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

Logs: `.pytest_cache/r1-s1-t3b-d3d2a-*.txt`. No live-provider validation.
No working-data migration/deletion, deployment or worker-crash claim. Next:
**R1-S1-T3b-D3d2b**. D3d2 and all higher parents remain open.
