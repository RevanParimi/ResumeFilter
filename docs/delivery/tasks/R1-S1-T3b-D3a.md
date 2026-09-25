# R1-S1-T3b-D3a - Screening completion erasure refusal

Status: done (2026-09-22). Parent: [D3](R1-S1-T3b-D3.md).

## Acceptance and scope

Trigger: candidate, resume or report is deleted after ingest returns but before
the batch-item completion commits. Today completion raises IntegrityError,
leaving retained input/processing state and an HTTP 500. The process service
also counts a rejected completion lease as successfully processed.

- Existing FK transactions order completion and erasure. Erase-first completion
  returns False, stores a failed item with a safe parent_erased code, and clears
  raw input/hash, IDs, signals and score under the original lease. Retrying that
  item cannot recreate its input or candidate. Write-first retains existing
  completed anonymous counts/scalars and SET NULL behavior.
- A stale lease or deleted batch never changes another worker's result. Other
  candidates/batches/tenants remain intact. Unrelated constraint errors propagate.
- Process counts successful completion only when complete returns True; refused
  completion counts as a failed attempt, including a discarded lease.
- Preserve successful/no-report compatibility, advisory flags, tenant scoping,
  schema, consent policy and normal retry behavior for unrelated failures.

Excludes earlier ingest exceptions/unlinked input (D3b), audit persistence (D3c)
and whole-ingest/response ordering (D3d). No frontend assets or wire fields change.

## Validation plan

Reproduce failures with controlled separate connections on SQLite/PostgreSQL;
test both orderings, lease replacement, retries, unrelated errors and HTTP
process/queue/retry with another tenant. Observe PostgreSQL delete blocking.
Run focused screening regressions, full project pytest, migrated scratch HTTP
and restart inspection on both backends, migration up/down/up, diff self-review
and static checks. Record results and limits below before completion.

## Implementation and review

Existing FK enforcement orders the completion UPDATE with erasure; no migration
or pre-check/lock abstraction was added. Only a recognized FK error followed
by a missing supplied parent permits cleanup. Rollback occurs before re-reading;
cleanup rechecks the original lease and writes no candidate-linked payload.
Non-FK constraints propagate even when the candidate is also missing. Process
counts a False completion as a failed attempt, not a successful screen.

Self-review: HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus this session's
diff in screening/store.py, screening/service.py, new concurrency tests and
smoke_r1_s1_t3b_d3a.py. Specification pass traced completion, no-report ingest,
retry, queue and tenant-scoped routes. Correctness pass reviewed rollback/lease
replacement, FK ordering, safe error codes, crash limits and SET NULL retention.
No acceptance-blocking findings remain. Added tests for unrelated NOT NULL
errors with a concurrently erased candidate and for report=None after erasure.
This is self-review, not independent review; earlier uncommitted changes are
preserved and are not attributed to this task.

## Evidence (2026-09-22)

- Initial regression: 9 failed, 4 passed, 15 skipped, 1 warning, 78.30s.
  Seven direct reproductions: three FK errors, three HTTP 500s and incorrect
  processed accounting. Two additional tests timed out waiting for the absent
  explicit rollback hook; these are not counted as defect reproductions.
- Final focused SQLite: 65 passed, 16 skipped, 1 warning, 41.83s. Skips are
  13 unconfigured PostgreSQL variants and three PG-only lock inspections.
- PostgreSQL runner focused: 78 passed, 3 skipped, 1 warning, 130.57s; all PG
  cases passed. Three skips are SQLite variants of PostgreSQL lock inspection.
  Observed deletion blocked on completion for candidate, resume and report;
  release/commit allowed deletion and SET NULL. Both orderings/retries and
  cleanup lease replacement passed on both databases. No full PG suite claimed.
- Full SQLite regression: 2266 passed, 61 skipped, 42 warnings, 447.79s.
  Skips: 54 unconfigured PostgreSQL cases and seven SQLite variants of PG lock
  inspection. No failing tests.
- Migrated HTTP/restart: 19/19 on each backend. Separate-session erasure is injected at
  completion; competing-thread evidence is pytest, not concurrent HTTP/browser.
- PostgreSQL migration up/down/up and disposable-cluster stop passed.
- Python compilation, local documentation links, new-file whitespace and
  git diff --check passed. The attempted Node binding
  check could not run: Node unavailable. No frontend assets/wire fields changed;
  no browser or live-provider evidence claimed.

Commands (PowerShell, project root):

```powershell
.resume/Scripts/python.exe -m pytest -q tests/test_screening_erasure_concurrency.py --tb=short
.resume/Scripts/python.exe -m pytest -q tests/test_screening_erasure_concurrency.py tests/test_screening_store.py tests/test_screening_service.py tests/test_screening_batches_api.py tests/test_screening_retry.py tests/test_screening_tenancy.py --tb=short
.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3a_postgres.py
.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3a.py
.resume/Scripts/python.exe -m pytest -q --tb=short
.resume/Scripts/python.exe -m py_compile src/app/screening/store.py src/app/screening/service.py tests/test_screening_erasure_concurrency.py scripts/smoke_r1_s1_t3b_d3a.py
git diff --check
node scripts/check_ui_bindings.js
```

Local logs: `.pytest_cache/r1-s1-t3b-d3a-{red,focused,full,smoke-sqlite}.txt`
and `r1-s1-t3b-d3a-pg-*.txt`. PG runner creates/stops a disposable local cluster,
runs migration up/down/up, focused tests and the smoke with --postgres. Runtime
and runner are ignored local artifacts, not portable setup guarantees.

## Remaining boundaries

D3b owns earlier unlinked input, ingest exceptions and interrupted cleanup: a
crash between failed completion rollback and cleanup can still retain input.
A superseded worker must not scrub the new claimant's row. No whole-ingest,
permanent re-upload ban or atomic cross-store erasure guarantee is claimed.
D3c audits and D3d ordering remain pending; D3/D/T3b/T3/F05/R1-S1-Q stay open.
Next: **R1-S1-T3b-D3b**; create its bounded acceptance record before implementing.
Working data/veritas.db SHA256 stayed
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
