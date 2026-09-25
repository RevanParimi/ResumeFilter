# R1-S1-T3b-D2b - Post-ingest fingerprint persistence

Status: done. Parent: [D2](../tasks/R1-S1-T3b-D2.md). Date: 2026-09-22.

Trigger: erasure commits after ingest but before fingerprint persistence, or
two fingerprint inserts race. Before: foreign-key/unique errors escape as HTTP
500 or generic batch errors. Intended: safe candidate_erased/resume_erased
refusal for missing parents, idempotent duplicate writes, no retained orphan.

Acceptance:
- Controlled competing connections cover candidate/resume deletion before
  fingerprint flush and after commit on SQLite and PostgreSQL; stale retries
  refuse, cascades remove fingerprints, and another candidate stays intact.
- Sequential and concurrent duplicates preserve one fingerprint and return
  False; unrelated integrity errors propagate. Reject mismatched ownership.
- Admin/org uploads return HTTP 422 with a safe reason, batches record that
  reason, and refused ingest does not proceed to comparison/evaluation.
- Full pytest, focused PostgreSQL, migrated scratch HTTP/restart, migration
  up/down/up, and recorded self-review of the final diff.

No schema/UI/consent change. No permanent ban on fresh uploads after erasure.
Short texts with no fingerprint, later screening completion/audits and broader
cross-store ordering remain D3/parent scope. Browser/live-provider checks do not
apply to this backend-only task. Existing user data and prior work are preserved.

Implementation: validate candidate/resume existence and ownership before the
duplicate shortcut. Existing foreign keys prevent orphan inserts and cascade
committed fingerprints on deletion. On IntegrityError, roll back and recheck
parents; missing parents raise safe domain exceptions. Return False only for
a unique violation with the same resume/algo now present; unrelated integrity
failures propagate. Shared ingest maps erasure to HTTP 422/failed batch codes
before comparison/evaluation. No auto-retry or identity recreation.

Self-review (2026-09-22): HEAD `9f2f6cd` plus the candidate store/shared ingest
diff and new fingerprint concurrency/HTTP smoke files. Specification review
mapped all acceptance checks to regressions: both parents/orderings, retries,
duplicates, unchanged survivor, ownership mismatch, safe route/batch responses.
Correctness review traced the sole production save_fingerprint caller through
shared ingest and existing route/batch refusal handling. Rollback clears stale
state before rechecks; uniqueness handling excludes NOT NULL failures even when
a competing valid duplicate exists. Resume ownership is assigned at creation;
no production reassignment path was found. Database constraints, not existence
checks alone, enforce write/delete ordering. No remaining blocking finding in
this scope. This was self-review, not independent review.

Limits: erasure after successful fingerprint commit can still race subsequent
comparison/evaluation/response or screening completion. Batch inputs retained
before candidate linkage remain D3. No whole-ingest or whole-erasure guarantee.

Final evidence:
- Before fix: 13 failed, 1 passed, 8 unconfigured PostgreSQL skips, 1 warning,
  12.40s. Real FK/unique failures, wrong-owner acceptance, four HTTP 500s and two
  generic internal_error batch results reproduced the defects.
- Migrated SQLite HTTP/restart: 18/18. Separate-session erasure injected before
  fingerprint save, with admin/org duplicate uploads and both batch refusal
  types. Restart inspects resumes/extractions/fingerprints and surviving identity.
  This is real HTTP, not concurrent HTTP/browser execution; thread races are pytest.
- Focused SQLite: 79 passed, 22 skipped, 1 warning, 36.01s. Skips are 18
  unconfigured PostgreSQL cases and four SQLite variants of PG lock inspection.
- Focused PostgreSQL runner: 97 passed, four SQLite-only lock-inspection skips,
  1 warning, 126.07s. All PostgreSQL cases passed, including observed blocking
  via pg_blocking_pids for candidate/resume deletion until fingerprint commit.
- PostgreSQL migrated HTTP/restart: 18/18; migration up/down/up and disposable
  cluster shutdown passed. No full PostgreSQL suite claimed.
- Full SQLite: 2250 passed, 45 skipped, 42 warnings, 261.29s. Skips are 41
  unconfigured PostgreSQL cases and four SQLite variants of PG lock inspection.
- Compilation, whitespace and local links across eight handoff/PI/task documents
  passed. Node binding check attempted: executable unavailable on PATH. No UI
  assets/handlers changed; no browser or binding-pass claim.

Commands:
```
.resume/Scripts/python.exe -m pytest tests/test_fingerprint_erasure_concurrency.py -q --tb=short
.resume/Scripts/python.exe -m pytest tests/test_fingerprint_erasure_concurrency.py tests/test_ingest_erasure_concurrency.py tests/test_candidate_store.py tests/test_fingerprint_store.py tests/test_screening_ingest.py tests/test_screening_api.py tests/test_screening_batches_api.py tests/test_screening_retry.py -q --tb=short
.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d2b.py
.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d2b_postgres.py
.resume/Scripts/python.exe -m pytest -q --tb=short
.resume/Scripts/python.exe -m py_compile src/app/candidates/store.py src/app/screening/ingest.py tests/test_fingerprint_erasure_concurrency.py scripts/smoke_r1_s1_t3b_d2b.py
git diff --check
node scripts/check_ui_bindings.js
.resume/Scripts/python.exe .pytest_cache/check_d2b_docs.py
```

Logs: `.pytest_cache/r1-s1-t3b-d2b-{red,focused,smoke,suite}.txt`, plus
`r1-s1-t3b-d2b-pg-{runner,focused,migrations,smoke,stop}.txt` there. Local PG runner
derives from D2a, creates/stops a disposable PostgreSQL 18.6 cluster, uses
Asia/Calcutta timezone, migration up/down/up, the focused command above, then
HTTP smoke with `--postgres`. These ignored artifacts are not portable setup.

No live-provider validation. Existing user data/uncommitted work preserved;
working data/veritas.db SHA256 remains
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Next: **R1-S1-T3b-D3**, separate chat. D2b and D2 done. D/T3b/T3/F05/R1-S1-Q
remain open; screening completion, audits and cross-store ordering are unresolved.
