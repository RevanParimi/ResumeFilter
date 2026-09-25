# R1-S1-T3b-D3b2b2 - Unresolved and historical screening input

Status: done (2026-09-23); conservative policy explicitly authorized.
Parent: [D3b2b](R1-S1-T3b-D3b2b.md).

## Acceptance boundary

Trace and reproduce erasure before first identity resolution, ordinary first
ingest failure and worker interruption before its first durable association.
Do not infer identity from text, silently delete ambiguous historical input,
change consent or lose completed anonymous counts/scalars. Preserve the batch
input retention window. D3b2a/D3b2b1's durable resume/report bindings remain done.

User selected the recommended conservative policy: "go ahead as recommeneded,
i trust your expertise" after identifying the beta records as dummy data.
Implement option 1 below; no further policy approval is needed. Preserve working
storage rather than treating dummy data as an instruction to delete it.

## Selected implementation acceptance

- Register new input with the current database erasure generation. Candidate,
  resume and report deletion (including cascades/bulk retention) advances it in
  the deletion transaction. Empty/rolled-back deletion must not invalidate input.
- Unlinked items with an older/unknown generation read as failed with a generic,
  actionable fresh-upload-required reason. They cannot claim, retry or commit
  ingest from stale worker memory. No tenant/candidate information is disclosed.
- Initial ingest must lock/check the generation before subject writes, retaining
  the lock until its resume/input binding commits. Erasure and registration must
  use compatible ordering. Preserve pinned retries already bound to a resume.
- Migration quarantines historical raw input and historical private references
  without report links, retaining text/references until the original TTL. It
  guesses no ownership. Completed scalars/counts remain intact. Downgrade must
  not silently revive quarantined input; refuse unsafe downgrade rather than
  delete ambiguous data or remove the protection unnoticed.
- Ordinary retry without intervening erasure and distinct fresh uploads remain
  allowed. Validate user-visible reason/reload and API counts, both databases,
  real worker exit/restart, concurrency, populated migrations and full pytest.

Use one singleton generation row, one nullable item generation column, database
deletion triggers and the existing failure vocabulary. No person/contact
tombstones, new worker, guessed matching or global text deletion.

## Implementation and limits

A singleton generation, nullable input stamp and deletion triggers order initial
ingest/registration with candidate, resume and report erasure. PostgreSQL takes
its generation lock before deletion statement row locks; SQLite serializes
writers. Read-only identity resolution precedes the guard; all subject writes
and private binding follow it in the same transaction. Bound retries retain
their exact surviving resume capability. Queue/count projection, claiming,
retry and stale worker commit all enforce the policy.

Migration 0026 quarantines unfinished historical raw input and private references
without report links, retaining their original TTL. Safe downgrade preserves
private children using native column removal; unsafe downgrade refuses before
changing schema/data. No working-data migration was run.

The accepted availability tradeoff applies across organizations: any subject
record deletion pauses all older unresolved input. The generic reason discloses
no subject or organization. This neither identifies nor immediately removes
unknown personal text; TTL still applies. Distinct fresh uploads remain allowed.
Consent/scoring and completed anonymous counts/scalars are unchanged. No permanent
re-upload ban or whole-ingest erasure guarantee is claimed.

## Validation (2026-09-23)

All Python commands use `.resume/Scripts/python.exe`. Synthetic isolated storage
and fake/capture providers only. Commands below are actual runs:

```powershell
.resume/Scripts/python.exe -m pytest -q tests/test_screening_unresolved_input.py --tb=short
.resume/Scripts/python.exe -m pytest -q tests/test_screening_unresolved_input.py tests/test_screening_store.py tests/test_screening_ingest.py tests/test_migrations.py --tb=short
.resume/Scripts/python.exe -m pytest -q tests/test_screening_unresolved_input.py tests/test_screening_durable_input.py tests/test_screening_report_input.py tests/test_screening_refusal_retention.py tests/test_screening_erasure_concurrency.py tests/test_screening_service.py tests/test_screening_retry.py tests/test_retention_sweep.py --tb=short
.resume/Scripts/python.exe -m pytest -q tests/test_screening_unresolved_input.py tests/test_screening_refusal_retention.py tests/test_screening_erasure_concurrency.py tests/test_ingest_erasure_concurrency.py --tb=short
.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3b2b2_postgres.py
.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3b2b2_extra_postgres.py
.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3b2b2.py --browser
.resume/Scripts/python.exe -m pytest -q --tb=short
.resume/Scripts/python.exe -m py_compile src/app/screening/erasure_schema.py src/app/screening/models.py src/app/screening/store.py src/app/screening/ingest.py src/app/screening/service.py src/app/screening/schema.py src/app/candidates/store.py alembic/versions/0026_screening_erasure_guard.py tests/test_screening_unresolved_input.py scripts/smoke_r1_s1_t3b_d3b2b2.py scripts/check_ui_screening_unresolved_browser.py
node scripts/check_ui_bindings.js
git diff --check
```

- Red: **3 failed**, 1 warning, 4.45s for the intended pre-extraction,
  failed-first-ingest and interrupted-first-ingest recreation defect.
- Initial focused: **39 passed**, 16 warnings, 14.55s. Expanded: 4 failed,
  110 passed, 70 skipped, 3 warnings, 56.44s. Four old-policy assertions expected
  unrelated pending/reclaimable input; updated to the authorized pause behavior.
  Focused rerun: **50 passed, 44 skipped**, 1 warning, 33.10s.
- Final new-file run: **15 passed, 11 skipped**, 1 warning, 18.01s. Includes
  added actual TTL dry-run/apply and unrelated-erasure bound-retry checks.
  An earlier TTL assertion expected skipped=1 after text expiry; corrected to
  require requeued=0, since expired processing input no longer counts as retained.
- PostgreSQL 18.6 focused runner: **330 passed, 13 skipped**, 23 warnings,
  335.54s. Twenty files cover screening/ingest/report/retention/tenancy/migrations
  and existing concurrency. All PG variants passed; skips are SQLite variants
  of PG lock inspection. Controlled pre-write lock blocking was observed with
  pg_blocking_pids; committed/rolled-back bulk candidate/resume/report deletion
  and empty deletion, populated safe/refused migrations and up/down/up passed.
- Supplemental PG runner for the final new-file state: **25 passed, 1 skipped**,
  1 warning, 38.83s, including the final TTL/bound-retry additions. Both disposable
  PG clusters stopped cleanly (pg_ctl exit 0). No application .env edits.
- Migrated HTTP/real worker exits and restarts: **17/17 per backend**.
  Exit 71 interrupts extraction; exit 72 interrupts after private-binding flush
  before commit. Rollback, erasure, stale recovery, second restart, two tenants,
  retained text/hash, unchanged identities and successful fresh upload checked.
- SQLite journey with real Chrome: **21/21**, including four browser checks:
  rendered re-upload instruction, reload, file upload/process success with the
  older batch still paused, no console errors/uncaught exceptions. Auth setup
  uses real HTTP and captured synthetic email. Browser uses existing CDN assets,
  so is not fully offline. Screenshot retained in smoke scratch storage.
- Full SQLite suite: **2332 passed, 115 skipped**, 44 warnings, 433.57s.
  Skips are unconfigured PG variants and SQLite variants of PG lock inspection.
  Production source was final before collection; two final compatibility tests
  added after collection passed separately in the final SQLite/PG focused runs.
  No full PostgreSQL suite or live-provider validation claimed.
- Compilation of all eleven changed/new source, migration, test and smoke files
  passed with `-m py_compile`. Node binding command unavailable (Node not
  installed); no frontend assets changed, actual browser behavior validated.
  Whitespace and task documentation link/status checks passed.

Logs: `.pytest_cache/r1-s1-t3b-d3b2b2-*.txt`; supplemental PG logs use
`r1-s1-t3b-d3b2b2-extra-pg-*`. Local runners use disposable storage and the
portable runtime recorded in `.pytest_cache/r1-s1-t3a-v1-pg-runtime.json`.
These ignored artifacts are local evidence, not portable setup guarantees.

## Recorded diff self-review

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus this session's
uncommitted candidate before-write callback, screening models/store/ingest/service/
schema, frozen trigger helper, migration 0026, new behavioral tests and both
journey scripts. Compared previously modified files with start-of-session copies
in `.pytest_cache/d3b2b2-start`; preserved preceding changes. Specification pass
mapped every acceptance check above to the tests/journeys. Correctness pass
checked lock order, lease loss, stale memory, cascade/rollback semantics,
migration preservation, tenant responses, unchanged TTL and bound retry.

Resolved findings: (1) high, store nullable error predicate could make SQL NOT
return NULL and reject valid ingest; COALESCE plus successful initial/retry tests
covers it. (2) high, rebuilding SQLite batch_items during downgrade could cascade
away private references; native DROP COLUMN and populated preservation regression
cover it. (3) medium, moving the guard before known-subject cleanup could replace
explicit erasure refusal with a retained-input reason; fresh subject existence
check after read-only resolution preserves explicit cleanup, verified by ingest/
screening concurrency regressions. Old-policy test expectations were updated
only where the newly authorized availability policy changes the result.

No acceptance-blocking finding remains. This is self-review, not independent
review. Working data/veritas.db hash remains
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Existing uncommitted work is preserved; no deployment or live cleanup.
D3b2b/D3b2/D3b now done; D3/D/T3b/T3/F05/R1-S1-Q remain open.
Exact next task: **R1-S1-T3b-D3c**, disclosure/materialization/training audit races.
