# R1-S1-T3b-D3b1 - Scrub recorded screening erasure refusals

Status: done (2026-09-22). Parent: [D3b](../tasks/R1-S1-T3b-D3b.md).

## Acceptance and scope

Trigger: resolved ingest or fingerprint persistence refuses an erased candidate
or resume. Batch processing records failure but retains raw text/hash, allowing
retry to recreate the erased input. Recording an erasure failure must atomically
clear text/hash, IDs, signals and score under the original lease. Exact internal
candidate_erased/resume_erased/report_erased codes select this behavior; ordinary
failures retain retry input. Failed status and scrub commit together.

Acceptance: actual ingest/fingerprint refusal through process/queue/retry cannot
recreate input; correct failed/processed counts, advisory flags and other-tenant
404s persist. New leases/deleted batches reject stale fail calls. Ordinary
failures remain retryable and unrelated batches/tenants stay intact. Completion
and completed anonymous scalar/count retention are unchanged.

No schema, UI, consent or scoring change. Crashes before fail commits, earlier
unlinked input and identity association remain D3b2, including D3a interrupted
cleanup. This child does not claim crash-safe whole-ingest erasure.

## Validation plan

Behavioral red/green store and HTTP regressions on isolated SQLite/PostgreSQL,
controlled competing connections for lease replacement/deletion, transaction
rollback checks, focused screening/ingest/fingerprint tests, full pytest,
migrated scratch HTTP/restart with disabled external providers, PostgreSQL
migration up/down/up, and recorded diff self-review. No browser requirement:
frontend assets and wire schema are unchanged.

## Implementation and review

Only ScreeningStore.fail changes in application code. The existing UPDATE now
also clears payload for the three exact internal erasure codes; no extra write,
transaction, pre-check, abstraction or migration. Existing lease and retry
predicates apply. Code comparison uses the session-start store snapshot as well
as HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6`, preserving prior uncommitted
completion fixes. New tests and smoke_r1_s1_t3b_d3b1.py are this child's evidence.
SCREENING.md documents the erasure-refusal exception to ordinary retry retention.

Self-review specification pass traced all fail callers (IngestRefused and generic
exception), completion, process accounting, retry and tenant-scoped routes.
Correctness pass checked exact code matching before truncation, one-transaction
status/scrub, lease replacement, deleted batches, linked payload clearing,
ordinary retries, unchanged completed scalars and isolated smoke setup. No
acceptance-blocking finding remains. No independent review or live-provider
validation is claimed. Pre-commit interruption intentionally rolls back both
status and scrub; recovery of that retained input is D3b2, not solved here.

## Evidence (2026-09-22)

- Red: **8 failed, 4 passed, 9 skipped**, 1 warning, 19.65s. All failures assert
  retained payload: three direct erasure codes, new-lease owner's subsequent
  refusal, post-rollback repeat, and three actual ingest/fingerprint HTTP paths.
  The latter cover resolved candidate deletion, portal candidate erasure at
  fingerprinting, and resume deletion at fingerprinting.
- Focused SQLite: **102 passed, 47 skipped**, 1 warning, 75.36s. Skips include
  unconfigured PostgreSQL variants and PostgreSQL-only lock inspection.
- Migrated SQLite HTTP/restart: **19/19**, including refusal/queue/retry,
  other-tenant denial, unrelated success, anonymous completion and persisted
  input/hash/ID/score inspection after restarting without test hooks.
- PostgreSQL runner focused: **142 passed, 7 skipped**, 1 warning, 223.73s.
  All PostgreSQL variants passed; skips are SQLite variants of PostgreSQL lock
  inspection. Controlled separate connections cover stale refusal versus new
  lease/deleted batch on both backends. Existing ingest/fingerprint/completion
  lock regressions also passed. No full PostgreSQL suite is claimed.
- Migrated PostgreSQL HTTP/restart: **19/19**. Erasure uses separate sessions
  injected at identity resolution/fingerprint write, not simultaneous HTTP
  actors. Real competing-connection evidence is pytest, not browser evidence.
  PostgreSQL migration up/down/up and disposable cluster stop passed.
- Full SQLite pytest: **2279 passed, 70 skipped**, 42 warnings, 464.38s.
  Skips: 63 unconfigured PostgreSQL variants and seven SQLite variants of
  PostgreSQL lock inspection. No failing tests.
- Python compilation and git diff --check passed. Attempted Node binding check
  could not run (executable unavailable). No frontend assets/wire fields change;
  no browser claim. Local documentation links and new-file whitespace passed.

Commands (PowerShell, project root):

```powershell
.resume/Scripts/python.exe -m pytest -q tests/test_screening_refusal_retention.py --tb=short
.resume/Scripts/python.exe -m pytest -q tests/test_screening_refusal_retention.py tests/test_screening_erasure_concurrency.py tests/test_screening_store.py tests/test_screening_service.py tests/test_screening_batches_api.py tests/test_screening_retry.py tests/test_screening_tenancy.py tests/test_ingest_erasure_concurrency.py tests/test_fingerprint_erasure_concurrency.py --tb=short
.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3b1.py
.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3b1_postgres.py
.resume/Scripts/python.exe -m pytest -q --tb=short
.resume/Scripts/python.exe -m py_compile src/app/screening/store.py tests/test_screening_refusal_retention.py scripts/smoke_r1_s1_t3b_d3b1.py
git diff --no-index -- .pytest_cache/r1-s1-t3b-d3b1-store-before.py src/app/screening/store.py
git diff --check
Get-Command node -ErrorAction SilentlyContinue
node scripts/check_ui_bindings.js
```

Local logs: `.pytest_cache/r1-s1-t3b-d3b1-{red,focused,full,smoke-sqlite}.txt`
and `r1-s1-t3b-d3b1-pg-*.txt`. PG runner creates/stops a disposable cluster,
runs migration up/down/up, focused tests and smoke with --postgres. Runner and
runtime are ignored local artifacts, not portable environment setup guarantees.

Next: **R1-S1-T3b-D3b2**. D3b/D3/D/T3b/T3/F05/R1-S1-Q remain open.
Working data/veritas.db SHA256 remains
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
