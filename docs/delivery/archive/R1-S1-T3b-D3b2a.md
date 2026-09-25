# R1-S1-T3b-D3b2a - Bind retry input in the successful ingest transaction

Status: done (2026-09-23). Parent: [D3b2](R1-S1-T3b-D3b2.md).

## Acceptance and design

Trigger: candidate/resume erasure after successful ingest but before screening
completion/failure, including worker interruption and ordinary evaluation
failure. The batch currently retains unlinked text and retry recreates it.

- Successful batch ingest must atomically clear batch raw text/hash and persist
  a private item-to-resume reference. Candidate/resume and batch deletion
  cascade this reference; the public completion fields stay unchanged.
- Ordinary failure and stale-claim recovery use that exact surviving resume.
  Erasure after retry reads the input must refuse it, never resolve a new
  identity or create a replacement resume. Other tenants cannot read/retry it.
- Lost leases/deleted batches cannot acquire input or commit an abandoned
  ingest; unrelated constraint failures still propagate. Successful completion
  and explicit erasure refusal remove the private reference under the lease.
- Preserve anonymous completed scalars/counts, normal pre-ingest retries,
  consent and existing batch-input TTL. Sweeping the reference ends retry
  without deleting the resume or the completed screening record.
- Upgrade adds the private table without guessing historical ownership.
  Downgrade restores still-retained input for unfinished items before dropping
  references; it cannot restore references already removed by erasure/sweep.

One small private table holds an item ID, a CASCADE resume ID and the original
item creation time; it contains no copied resume text. The existing successful
ingest transaction supplies a before-commit callback for binding. A retry pins
the resume rather than performing identity resolution again.

Excludes pre-first-commit identity association, ambiguous legacy raw input and
report-only erasure interrupted before completion cleanup (D3b2b). No UI fields,
consent/scoring policy, deployed migration or working-data cleanup is changed.

## Validation plan

Red/green actual process failures and interrupted evaluation; candidate/resume
erasure, ordinary retry, two tenants, expired retention, lost leases, rollback
and pinned retry races. Controlled SQLite/PostgreSQL connections, PostgreSQL
lock inspection, populated migration up/down/up, ORM drift, full pytest,
migrated scratch HTTP/restart/worker termination, compilation and diff
self-review. No browser requirement because public UI contracts stay unchanged.

## Implementation and self-review

Migration 0024 adds screening_item_inputs. Ingest's before-commit callback binds
the private reference and clears raw input/hash; retries pin the surviving
tenant-owned resume. The candidate write lock precedes the resume lock, then
the lease-checked item update. Completion/refusal remove references under the
lease; candidate/resume/batch deletion uses FK CASCADE. The existing sweep class
also deletes expired references using the original item timestamp.

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus the session diff
against saved starting candidate/screening files, new migration/model, retention
targets, regressions and smoke. Specification pass traced all process/retry/
completion/refusal callers, tenant checks, populated downgrade, retention and
public queue compatibility. Correctness pass checked lock order, FK cascade,
rollback, lease loss, stale input, unexpected constraints and source text leakage.
No independent review or live-provider validation is claimed.

Review finding (medium, retain_ingested_input): a worker holding text from before
a sweep could recreate retry capability. Fixed by requiring surviving raw input
for initial binding and the same private reference for retry. Both stale-copy
cases are covered; no acceptance-blocking findings remain in the reviewed scope.
The PostgreSQL lock tests initially deleted a different identity because their
seed had no contact hash; corrected the fixture to share an explicit synthetic
identity. The separate contact-free retry regression remains unchanged.

## Evidence (2026-09-23; work started 2026-09-22)

- Red: **5 failed**, 1 warning, 2.34s: four retained-input failures after
  candidate/resume erasure (ordinary failure and interrupted evaluation), plus
  a contact-free retry creating a second candidate/resume.
- Expanded SQLite focused before final extra assertions: **190 passed,
  68 skipped**, 20 warnings, 92.58s. Final durable-input file: **23 passed,
  23 skipped**, 1 warning, 27.55s. Skips include unconfigured PG variants and
  PG-only lock inspection. Full suite below includes all final regressions.
- Initial PostgreSQL runner: **4 failed, 243 passed, 11 skipped**, 20 warnings,
  304.69s. Four lock-test fixture failures described above.
- Final PostgreSQL runner: **253 passed, 11 skipped**, 20 warnings, 312.68s.
  All PostgreSQL variants passed, including observed candidate/resume deletion
  blocked by initial and pinned-retry ingest commits, both erasure orderings,
  populated migration down/up, retention and rollback. The skips are SQLite
  variants of PostgreSQL lock inspection. Migration chain up/down/up passed.
  Shutdown wait timed out (exit 1, 33.06s); follow-up pg_ctl status returned
  "no server running" and the server log confirmed clean shutdown. No cluster
  was left running. The runner's overall exit alone is not shutdown evidence.
- Migrated HTTP/subprocess/restart: **18/18 on each backend**. Two actual scratch-worker
  exits during evaluation (exit 71), then erasure, stale claim recovery and
  another restart. Staleness is selected by backdating the scratch claim;
  ordinary retry, same contact-free identity, other-tenant denial and anonymous
  completed records are also checked. External providers disabled.
- Full SQLite pytest: **2303 passed, 93 skipped**, 42 warnings, 341.50s.
  No failures. Skips: 82 unconfigured PostgreSQL variants and 11 SQLite
  variants of PostgreSQL lock inspection.
- Compilation, git diff --check, new-file whitespace and local documentation
  links passed. Attempted Node binding check could not run: Node unavailable.
  No frontend assets/public UI fields changed; no browser claim.

Commands (PowerShell, project root):

```powershell
.resume/Scripts/python.exe -m pytest -q tests/test_screening_durable_input.py --tb=short
.resume/Scripts/python.exe -m pytest -q tests/test_screening_durable_input.py tests/test_screening_ingest.py tests/test_candidate_store.py tests/test_ingest_erasure_concurrency.py tests/test_fingerprint_erasure_concurrency.py tests/test_screening_refusal_retention.py tests/test_screening_erasure_concurrency.py tests/test_screening_store.py tests/test_screening_service.py tests/test_screening_batches_api.py tests/test_screening_retry.py tests/test_screening_tenancy.py tests/test_migrations.py tests/test_retention_plan.py tests/test_retention_sweep.py tests/test_retention_api.py --tb=short
.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3b2a_postgres.py
.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3b2a.py
.resume/Scripts/python.exe -m pytest -q --tb=short
.resume/Scripts/python.exe -m py_compile src/app/candidates/store.py src/app/screening/models.py src/app/screening/store.py src/app/screening/service.py src/app/screening/ingest.py src/app/retention/plan.py src/app/retention/sweep.py alembic/versions/0024_screening_retry_input.py tests/test_screening_durable_input.py scripts/smoke_r1_s1_t3b_d3b2a.py
git diff --check
node scripts/check_ui_bindings.js
```

Local logs: `.pytest_cache/r1-s1-t3b-d3b2a-{red,focused,durable-final,full,smoke-sqlite}.txt`
and `r1-s1-t3b-d3b2a-pg-*.txt`. The disposable PG runner is a local ignored
artifact, not a portable setup guarantee. No full PostgreSQL suite is claimed.
Next: **R1-S1-T3b-D3b2b**. D3b2 and all parent gates remain open.
Existing uncommitted work was preserved. Working data/veritas.db SHA256 stayed
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
