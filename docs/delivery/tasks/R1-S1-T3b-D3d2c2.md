# R1-S1-T3b-D3d2c2 - Challenge issuance across erasure

Status: done 2026-09-27. Parent: [D3d2c](R1-S1-T3b-D3d2c.md). Prerequisite: D3d2c1.

## Acceptance before implementation

Trigger: send starts, portal/admin erasure commits, then issue_code saves its
non-FK challenge and restores login capability. Preserve send-before-activation:
a send failure must leave any previous code, attempt budget and cooldown intact.

Register a short-lived issuance token before sending; erasure deletes tokens and
existing challenges atomically. Activate only a surviving exact token in the same
transaction as challenge replacement. Short per-address transaction locks order
registration/activation against cleanup (PostgreSQL advisory lock; SQLite writer
lock). Never hold a database lock during provider I/O. Registration after cleanup
is fresh issuance, including legitimate signup; no permanent address tombstone.

- All planes/purposes for the erased stored hash are cancelled; unrelated hashes
  and org/admin principals survive. Already-sent mail cannot be recalled, but its
  cancelled token cannot create a redeemable challenge or debug-echo the code.
- Failed/unknown provider exceptions preserve the prior valid challenge and
  remove only their own reservation. Retry and fresh signup work. Public known/
  unknown/refused-by-erasure responses remain generic 202; no contact ban.
- Competing activation and cleanup commit in a consistent order. Rollback keeps
  both reservations/challenges; retry erases both. Expired/abandoned reservations
  cannot authorize activation and use existing opportunistic/retention cleanup.
- Migration 0027 adds only issuance ID, scope and expiry (no raw address, code or
  payload), preserves existing challenges, and supports scratch up/down/up.
- Validate meaningful red/green, SQLite/PG controlled connections, both API doors,
  migrated HTTP/process interruption/restart, focused/full pytest and diff review.

Redemption after an already-committed consume remains c3. No browser/UI change,
working-data migration, external mail or whole-response delivery guarantee.

## Evidence

Project Python throughout: `.resume/Scripts/python.exe`. Validation ran during
26-27 September; closure recorded 27 September. Providers were synthetic capture/
null; migrations and destructive tests used disposable databases only.

- Red: `-m pytest tests/test_login_issuance_erasure.py -q --tb=short`:
  **6 failed**, 1 warning, 5.81s. Every plane through both erasure doors restored
  a challenge after deletion. Log: `.pytest_cache/d3d2c2-red.txt`.
- Initial focused: `-m pytest tests/test_login_issuance_erasure.py
  tests/test_login_erasure_atomic.py tests/test_auth_service.py
  tests/test_auth_store.py tests/test_migrations.py -q --tb=short`:
  **95 passed, 8 skipped**, 16 warnings, 26.38s. Expanded issuance/retention check:
  `-m pytest tests/test_login_issuance_erasure.py tests/test_retention_sweep.py
  -q --tb=short`: **36 passed, 8 skipped**, 1 warning, 14.34s. Final additions
  (fresh registration blocked behind erasure and retention-plan coverage) are
  included in the following full/focused runs.
- Full SQLite: `-m pytest -q --tb=short`: **2517 passed, 188 skipped**,
  44 warnings, 494.45s. `.pytest_cache/d3d2c2-full.txt`. Skips remain qualified;
  this is not a full PostgreSQL or live-provider run. Warnings concern Starlette/
  httpx, SQLite expression-index reflection and Chroma legacy embedding config.
- PostgreSQL: `.pytest_cache/run_r1_s1_t3b_d3d2c2_postgres.py` created its own
  PG 18.6 cluster (Asia/Calcutta), ran complete migration **up/down/up**, focused
  pytest **167 passed, 2 skipped**, 16 warnings, 223.22s, both HTTP smokes below,
  and stopped the cluster cleanly. Runner/runtime are ignored local artifacts.
  Focused command: `-m pytest tests/test_login_issuance_erasure.py
  tests/test_retention_plan.py tests/test_retention_sweep.py
  tests/test_login_erasure_atomic.py tests/test_portal_sessions.py
  tests/test_auth_service.py tests/test_auth_store.py tests/test_portal_service.py
  tests/test_portal_api.py tests/test_migrations.py -q --tb=short` with a disposable
  `DEE_TEST_DB_URL`. Two skips are SQLite variants of PG-only lock inspection.
  Controlled PG connections observed actual blocking through `pg_blocking_pids`:
  activation-first, erasure-first and fresh reservation behind erasure, each with
  commit/rollback. Other pending hashes survive. Populated 0027 round trips
  preserve active code ID/hash/payload; expiry, retention and failed sends pass.
- `scripts/smoke_r1_s1_t3b_d3d2c1.py --issuance`: migrated SQLite **34/34**;
  with `--postgres --issuance`: **34/34**. Real HTTP on all three planes through
  both erasure doors, held send, cancelled activation/echo, stale-code refusal,
  unrelated session survival, restart and fresh login. Process exit after delivery
  leaves one token; restart + erasure cancels it and replay cannot activate.
  Existing c1 `scripts/smoke_r1_s1_t3b_d3d2c1.py --postgres`: **24/24**.
  Logs: `.pytest_cache/d3d2c2-smoke-sqlite.txt` and
  `.pytest_cache/r1-s1-t3b-d3d2c2-pg-{focused,migrations,smoke,issuance-smoke,stop}.txt`.
- `node scripts/check_ui_bindings.js`: **402 bindings / 9 states passed**.
  No screen/handler change; no browser or independent-review claim.
  `git diff --check` passed. `.pytest_cache/check_d3d2c2_docs.py` checked local
  links across 155 Markdown files, 22 active task records, next/parent status,
  compiled all 11 changed Python files and confirmed the unchanged DB hash.
  No new Markdown file; reused this brief and the prior HTTP harness.

## Diff self-review

Reviewed HEAD `4c83cad` plus this task's uncommitted auth model/store/service,
candidate deletion, retention, migration 0027, regression and smoke changes.
Preserved earlier documentation cleanup. Traced both erasure routes, issuance
callers, standalone challenge cleanup, session transactions and retention targets.

Specification: exact scoped token consumption and challenge replacement share a
commit; the same short address lock orders candidate cleanup and reservations.
Send failure cancels only its token; active code attempts/cooldown survive.
No lock spans email I/O; cleanup has no permanent address tombstone. Migration
stores no raw address/code/payload; existing API response shape and fresh signup
remain compatible. Both backends and actual restart paths satisfy these bounds.

Correctness/maintenance finding (low): adding a retention target left the plan
contract and operator target/cap counts at two tables. Updated the regression and
OPERATING.md to three login targets (fourteen total); full/focused checks pass.
Updated stale auth/portal cleanup comments. No acceptance-blocking findings remain.
This was same-agent self-review. Already-sent mail, consume-before-erasure
redemption, aggregate response windows and curation retention are not closed here.

Next: **R1-S1-T3b-D3d2c3**. Login parent/T3/F05/sprint gates remain open.
