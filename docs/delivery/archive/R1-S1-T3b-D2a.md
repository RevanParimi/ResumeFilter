# R1-S1-T3b-D2a - Resolved-candidate ingest racing erasure

Status: done.
Parent: [D2](../tasks/R1-S1-T3b-D2.md). Date: 2026-09-22.

Trigger: candidate erasure commits after identity resolution, before the identity
UPDATE. Before: ORM StaleDataError becomes HTTP 500 or a generic batch failure.
Intended: rollback, confirm the resolved candidate is absent, and refuse with
`candidate_erased` (HTTP 422 / failed batch item). Never rerun identity resolution
or create a replacement candidate inside the interrupted ingest.

Acceptance:
- Event-controlled competing SQLite/PostgreSQL connections cover deletion before
  the first flush and after successful ingest commit, with new/duplicate resumes.
  Erased candidates retain no resume/extraction; another candidate is unchanged.
- The first identity UPDATE serializes subsequent resume/extraction writes with
  erasure. Verify PostgreSQL erasure waits when ingest has flushed but not committed.
- A non-erasure stale-row failure propagates; rollback precedes fresh lookup.
- Admin/org upload and batch API map the refusal without SQL/private data.
  Successful identity matching, org ownership and duplicate uploads still work.
- Full pytest, focused PostgreSQL, migrated scratch HTTP/restart journey,
  migration up/down/up and recorded self-review.

Excludes the later fingerprint transaction (D2b), screening completion/audits
(D3), new consent policy, identity repair and permanent re-upload suppression.
No frontend or schema change; browser/provider validation is not required.

Implementation: catch StaleDataError at the first flush only, roll back, then
read the resolved candidate afresh. An absent matched candidate raises a safe
CandidateErasedError; ingest_resume translates it into the existing IngestRefused
contract. Live-parent errors still propagate. No retry or new store abstraction.

Self-review (2026-09-22): HEAD `9f2f6cd` plus candidate store/shared ingest diff,
new concurrency tests and HTTP smoke. Specification: new/duplicate resume writes,
both erasure orderings, admin/org uploads, portal/admin erasure and batch error
mapping have behavioral assertions. Correctness: captured ID survives rollback;
the refresh always changes updated_at, acquiring the candidate write lock before
any resume/extraction write; rollback clears stale ORM state before lookup. The
only production CandidateStore.ingest caller is shared ingest_resume; its admin,
organization and batch callers already handle IngestRefused. Existing ownership,
duplicate and identity tests are included. No blocking finding remains in D2a.
No independent review is claimed. Fingerprint races and retained screening input
or completion after erasure remain D2b/D3, including the failed batch's input
that was not yet candidate-linked. This does not close whole-ingest erasure.

Final evidence:
- Before fix: 6 failed, 3 passed, 5 PostgreSQL skips, 1 warning, 5.13s.
  Two ORM stale errors and four actual HTTP 500s reproduce the defect.
- Focused SQLite: 64 passed, 9 skips (7 PG cases, 2 PG-only lock inspections
  on SQLite), 1 warning, 15.34s.
- Migrated SQLite HTTP/restart: 12/12. Scratch-server injection deletes on a
  separate DB session after real identity resolution; this is HTTP evidence,
  not concurrent HTTP or browser execution. Competing threads are in pytest.
- Focused PostgreSQL runner: 71 passed, 2 skips (SQLite variants of PG-only
  lock inspections), 1 warning, 79.06s. All PostgreSQL cases passed, including
  actual pg_blocking_pids evidence that erasure waits on the first ingest UPDATE
  until resume/extraction commit. Competing connections cover both orderings.
- Migrated PostgreSQL HTTP/restart: 12/12; migration up/down/up and disposable
  cluster shutdown passed. No migration/schema change introduced.
- Full SQLite: 2234 passed, 32 skipped (30 unconfigured PG cases and 2 SQLite
  variants of PG-only lock inspections), 42 warnings, 235.37s.
- Compilation, git diff --check and local links across 8 handoff/PI/task
  documents passed.

Commands (project environment throughout):
```
.resume/Scripts/python.exe -m pytest tests/test_ingest_erasure_concurrency.py -q --tb=short
.resume/Scripts/python.exe -m pytest tests/test_ingest_erasure_concurrency.py tests/test_candidate_store.py tests/test_fingerprint_store.py tests/test_screening_ingest.py tests/test_screening_api.py tests/test_screening_batches_api.py tests/test_screening_retry.py -q --tb=short
.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d2a.py
.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d2a_postgres.py
.resume/Scripts/python.exe -m pytest -q --tb=short
.resume/Scripts/python.exe -m py_compile src/app/candidates/store.py src/app/screening/ingest.py tests/test_ingest_erasure_concurrency.py scripts/smoke_r1_s1_t3b_d2a.py
git diff --check
```

Logs: `.pytest_cache/r1-s1-t3b-d2a-{red,focused,smoke,suite}.txt` and
`r1-s1-t3b-d2a-pg-{runner,focused,migrations,smoke,stop}.txt` there. The local PG
runner derives from D1, creates/stops a disposable PostgreSQL 18.6 cluster,
uses Asia/Calcutta timezone, migration up/down/up, the focused command above,
then the HTTP smoke with `--postgres`. No full PostgreSQL suite claimed.

`node scripts/check_ui_bindings.js` was attempted but Node is unavailable on
PATH. No frontend asset/handler changed; no binding/browser result is claimed.
No live-provider validation. Existing user database and uncommitted work are
preserved. Working data/veritas.db SHA256 stayed
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Next: **R1-S1-T3b-D2b**, separate chat. D2/D/T3b/T3/F05/R1-S1-Q remain open.
