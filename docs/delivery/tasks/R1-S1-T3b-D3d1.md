# R1-S1-T3b-D3d1 - Shared ingest response after subject erasure

Status: done (2026-09-24). Parent: [D3d](R1-S1-T3b-D3d.md).

## Acceptance and scope

Trigger: candidate/resume deletion after ingest/fingerprint commit, during farm
comparison or evaluation, or after report persistence before response assembly.
Currently evaluate=False returns stale success unconditionally; evaluate=True
can return stale IDs with report=null. Refuse observed missing subjects using
existing IngestRefused codes: admin/org uploads return 422, batches record a
failed item and scrub retry input under existing erasure-refusal semantics.

- A fresh store read checks candidate and exact resume ownership together.
  Candidate disappearance takes precedence; missing resume is resume_erased;
  wrong ownership and unrelated store/provider failures remain errors.
- Check before evaluation, before report persistence after evaluation, and
  before returning. Include short text with no fingerprint, both evaluate modes,
  duplicate uploads, erasure after fingerprint/comparison/report commit, both
  upload planes, batch continuation/retry and an unaffected second subject.
- Candidate erasure refuses report persistence through existing FK/store guards;
  when a report save signals SubjectErasedError, refuse the ingest instead of
  reporting stale success. This intentionally supersedes candidate-upload 200
  with report=null for erased subjects; standalone /evaluate is unchanged.
- Preserve ownership/redaction, consent, scoring, fresh-upload behavior and
  existing independent report lifetime when only one resume version is deleted.
  Checks are snapshots, not a lock across evaluation, save or HTTP delivery;
  report-only deletion/cleanup interruption and integrated ordering remain D3d2.
- Required: red/green, focused/full pytest, SQLite/PG controlled connections,
  migration round trips, migrated HTTP/restart journey, diff self-review and
  static/docs checks. No schema/frontend change or new response fields/codes;
  existing 422 refusal handling is reused. No browser/live-provider claim.

Use a small read guard in CandidateStore and the existing shared ingest caller;
do not add locks, tombstones, retry identity resolution or change erasure policy.

## Evidence

- Red: `.resume/Scripts/python.exe -m pytest -q tests/test_ingest_response_erasure.py --tb=short`:
  **36 failed, 4 passed, 2 skipped**, 1 warning, 28.82s. Stale HTTP 200 success,
  continued evaluation after observed erasure, and missing late-ingest refusal
  reproduced. Existing batch candidate-erasure completion safeguards passed.
- Broad focused: `.resume/Scripts/python.exe -m pytest -q tests/test_ingest_response_erasure.py tests/test_screening_ingest.py tests/test_candidates_api.py tests/test_screening_api.py tests/test_screening_erasure_concurrency.py tests/test_screening_refusal_retention.py tests/test_fingerprint_erasure_concurrency.py tests/test_report_erasure_concurrency.py tests/test_screening_durable_input.py --tb=short`:
  **150 passed, 70 skipped**, 2 warnings, 69.51s. Final optimization removes one
  redundant evaluate=False read.
- Final focused: `.resume/Scripts/python.exe -m pytest -q tests/test_ingest_response_erasure.py tests/test_screening_ingest.py tests/test_candidates_api.py --tb=short`:
  **66 passed, 3 skipped**, 1 warning, 30.57s.
- Migrated SQLite: `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3d1.py`:
  **36/36**, real HTTP/restart, both upload planes, short and long inputs,
  both evaluation modes, duplicate identities, late candidate/resume refusals,
  batch retry refusal/fresh batch success and persisted subject/report inspection.
  Repeated on final source: **36/36**. Synthetic providers; no worker-crash claim.
- PostgreSQL 18.6 broad runner:
  `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3d1_postgres.py`:
  **225 passed, 9 skipped**, 17 warnings, 358.54s. Includes report/fingerprint
  lock inspection, screening retry/refusal, durable input and migrations. This
  run began before the redundant-read optimization; final-source evidence follows.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3d1_final_postgres.py`:
  final source **80 passed**, zero skips, 1 warning, 142.89s, covering late-ingest,
  shared ingest, candidate and screening APIs. PostgreSQL migrated HTTP/restart
  **36/36** on final source. Both runners passed full migration up/down/up on
  isolated storage and shutdown logs confirm clean stops. The saved full SQLite
  log records **2441 passed, 161 skipped**, 44 warnings, 423.14s; the resumed
  final-state rerun below supersedes it. No full PG suite claim. Logs use
  `.pytest_cache/r1-s1-t3b-d3d1-*.txt`; scratch smoke artifacts include server.log.
- `.resume/Scripts/python.exe -m py_compile src/app/candidates/store.py src/app/screening/ingest.py tests/test_ingest_response_erasure.py tests/test_candidates_api.py scripts/smoke_r1_s1_t3b_d3d1.py`,
  `git diff --check`, changed-file whitespace and local documentation links passed.
  `node scripts/check_ui_bindings.js` unavailable (Node not installed). Existing
  refusal UI handling is reused; no frontend change or browser execution claim.

## Diff self-review (2026-09-24)

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus session changes to
candidates/store.py, screening/ingest.py, the candidates API regression, new
late-erasure tests/HTTP smoke and SCREENING.md. Start copies are saved under
`.pytest_cache/d3d1-start`; pre-existing changes remain preserved.
Specification: one fresh joined candidate/resume read, candidate-first refusal,
ownership rejection, pre-evaluation/pre-save/final checkpoints, safe API codes,
batch scrubbing and fresh-upload permission map to behavioral regressions.
Correctness: traced all three shared-ingest callers, report FK fallback, narrow
exception translation, no identity retry, no SQL/content logging, unchanged
tenant redaction and single-resume report lifetime. A redundant non-evaluating
read was removed; one final read suffices when no evaluation/save follows.
The old candidate-upload 200/report=null test was deliberately updated to 422;
standalone evaluation and successful upload fields remain unchanged.
No acceptance-blocking finding remains. This is self-review, not independent
review. Snapshot races after the final read, report-only erasure, and non-FK
cleanup interruption remain D3d2 scope; this does not close the parent.

## Resumed validation (2026-09-24)

Handoff still pointed to D3d, but this child already had implementation and
unfinished evidence in the workspace. Resumed this child only; preserved those
changes and added four regressions. Review of the saved pre-task copies versus
current source confirmed the bounded diff above. A coverage finding (medium,
`tests/test_ingest_response_erasure.py`) was resolved: erasure between the last
subject check and report save must exercise the real store refusal through both
upload routes. Two additional checks preserve unrelated evaluation/save errors.
Source needed no further change. Same-agent specification/correctness review
traced the joined read, exception mapping, both routes and batch fail/scrub;
no acceptance-blocking finding remains within this child.

- `.resume/Scripts/python.exe .pytest_cache/check_d3d1_resumed_red.py` loads the
  saved pre-task ingest in memory (no source replacement): **2 failed, 47
  deselected**, 1 warning, 5.31s. Both routes returned 200 instead of 422 after
  real report FK refusal. An initial runner import-order error was corrected
  before this reproduction and is not red evidence.
- `.resume/Scripts/python.exe -m pytest -q tests/test_ingest_response_erasure.py tests/test_screening_ingest.py tests/test_candidates_api.py tests/test_screening_api.py --tb=short`:
  **81 passed, 3 skipped**, 1 warning, 20.95s. PostgreSQL-only fixture variants
  skipped without a configured scratch connection.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3d1_final_postgres.py`:
  final tests **84 passed**, zero skips, 1 warning, 136.65s on PostgreSQL 18.6.
  Includes controlled competing connections in the response-erasure file.
  Migration up/down/up, migrated HTTP/restart **36/36**, clean cluster shutdown
  all passed. No full PostgreSQL suite claimed. Runner output:
  `.pytest_cache/r1-s1-t3b-d3d1-resumed-pg-runner.txt`; detailed logs retain the
  `r1-s1-t3b-d3d1-final-pg-*` names.
- `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3d1.py`:
  SQLite migrated HTTP/restart **36/36**; log
  `.pytest_cache/r1-s1-t3b-d3d1-resumed-smoke.txt`. Synthetic providers only.
- Compilation and `git diff --check` passed again. Node binding command was
  attempted again and remains unavailable; no frontend assets/handlers changed,
  no browser execution claimed.
- `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2445 passed, 161
  skipped**, 44 warnings, 351.33s on the final reviewed source/tests. Logs use
  `r1-s1-t3b-d3d1-resumed-{red,focused,full}.txt` under `.pytest_cache`.
- `.resume/Scripts/python.exe .pytest_cache/check_d3d1_docs.py`: local links,
  IDs, parent/next-task status and whitespace passed across **10 documents**.
  Working DB SHA256 remains
  `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

Next: **R1-S1-T3b-D3d2**, a separate session. D3d/D3/D/T3b/T3/F05/R1-S1-Q
remain open. No working-data migration/deletion, deployment or independent
review was performed.
