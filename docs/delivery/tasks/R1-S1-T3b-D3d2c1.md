# R1-S1-T3b-D3d2c1 - Atomic existing login-state erasure

Status: done 2026-09-26. Parent: [D3d2c](R1-S1-T3b-D3d2c.md). Prerequisite: D3d2b.

## Acceptance defined before implementation

Trigger: portal/admin erasure deletes challenges, then candidate deletion fails
or the process stops. Currently the challenge deletion has already committed.
Candidate/session/report data remains, but the prior valid codes are lost.

Move existing challenge cleanup into CandidateStore's candidate-delete transaction.
Both routes and direct candidate deletion inherit one commit. Keep the existing
all-plane/all-purpose email-hash policy; no inferred contact, new table, schema,
permanent ban or optional-auth dependency. Explicit standalone challenge cleanup
may remain for compatibility but is not the candidate erasure transaction.

Acceptance:
- Failure after challenge SQL or during candidate deletion rolls back challenges,
  candidate and cascaded state. Retry removes them together; missing candidate
  returns False without touching any other address.
- Successful portal/admin erasure retains response shape/report count, invalidates
  candidate sessions and old codes, and preserves unrelated candidate/org/admin
  principals and sessions. Same-address challenges on every plane are removed as
  before; their org/admin principals are not erased.
- Null/empty candidate email hashes never delete unassociated challenges.
- Independent connections see the committed pre-erasure state until commit;
  interruption before commit leaves it intact after process restart.
- Fresh signup at the erased address remains permitted and ordinary signup/login
  anti-enumeration behavior remains intact.

Required: meaningful red/green regressions, controlled SQLite/PostgreSQL connections,
both API doors with synthetic actors, full pytest, migrated HTTP/interruption/restart
on both backends, migration up/down/up, static checks and recorded diff self-review.
No frontend changes planned; capture/null email only.

Exclusions: late challenge issuance and already-consumed redemption (c2/c3),
aggregate response snapshots and curation policy (D3d2d), live email validation.

## Evidence

Initial red: `.resume/Scripts/python.exe -m pytest tests/test_login_erasure_atomic.py
-q --tb=short`: **4 failed, 4 passed, 4 skipped**, 1 warning, 7.98s. Both API
doors lost all six challenge scopes after candidate DELETE failed. Direct deletion
left challenges behind after commit/retry. PostgreSQL cases skipped without URL.
Initial focused SQLite (before added survivor/lock assertions): **93 passed,
4 skipped**, 1 warning, 12.28s. Survivor/report supplement: **8 passed, 4 skipped**,
1 warning, 7.44s. SQLite migrated HTTP/process exit/restart: **24/24**.
Resumed final validation (executed 2026-09-25, recorded 2026-09-26) on the
unchanged reviewed source/tests:
- Full SQLite: `.resume/Scripts/python.exe -m pytest -q --tb=short`:
  **2497 passed, 178 skipped**, 44 warnings, 627.87s. Log:
  `.pytest_cache/d3d2c1-resume-full.txt`.
- PostgreSQL: `.resume/Scripts/python.exe
  .pytest_cache/run_r1_s1_t3b_d3d2c1_postgres.py`: fresh disposable PG 18.6
  cluster, Asia/Calcutta timezone, migration **up/down/up passed**, focused
  **113 passed, 2 skipped**, 16 warnings, 242.18s. The two skips are the
  SQLite variants of PostgreSQL-only lock inspection. Actual PG connections
  observed a blocked consume, then refusal on erasure commit or success after
  rollback. Both API doors preserve other candidate/org/admin principals and
  sessions, all six challenge scopes, report count, retries and fresh signup.
- The runner invokes `-m pytest tests/test_login_erasure_atomic.py
  tests/test_portal_sessions.py tests/test_auth_service.py tests/test_auth_store.py
  tests/test_portal_service.py tests/test_portal_api.py tests/test_migrations.py
  -q --tb=short`, then `scripts/smoke_r1_s1_t3b_d3d2c1.py --postgres` using the
  project Python and a fresh disposable DEE_TEST_DB_URL. PG logs:
  `.pytest_cache/r1-s1-t3b-d3d2c1-pg-{focused,migrations,smoke,stop}.txt`.
  Cluster shutdown completed cleanly. Runner/runtime are ignored local artifacts.
- `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3d2c1.py`:
  migrated SQLite **24/24**; the PG invocation above: **24/24**. Real HTTP,
  process exit after challenge DELETE but before candidate DELETE, restart,
  rollback recovery, retry, old-code/session refusal, unrelated-code survival
  and fresh signup. SQLite log: `.pytest_cache/d3d2c1-resume-smoke.txt`.
- `node scripts/check_ui_bindings.js`: **402 bindings across 9 states passed**.
  `git diff --check` and `.resume/Scripts/python.exe -m py_compile` on the four
  changed source files, atomic test and smoke runner passed. No frontend change;
  no browser, full-PG, live-provider or independent-review claim.
- Documentation check: local links, task IDs, parent statuses and exact next-task
  pointers passed across 14 documents; final `git diff --check` passed.

Working DB SHA256 unchanged:
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Next: **R1-S1-T3b-D3d2c2**; c1 alone does not close any parent.

## Diff self-review

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus this session's
delta against `.pytest_cache/d3d2c1-start`: CandidateStore.delete_candidate,
PortalService.erase, AuthService/AuthStore cleanup documentation, new atomic
regressions and scratch HTTP runner. Earlier uncommitted fixes preserved.
Resumed review confirmed the same delta, both route callers, session factory,
challenge schema and test/smoke assertions; no additional code change needed.

Specification: both API doors delegate to the candidate store; challenge DELETE
and candidate/cascades use one session/commit; missing and null-address guards
preserve unrelated scopes. No FK/schema/API shape or authentication policy change.
Tests cover database refusal, reader visibility, restart, retries, survivor sessions,
report count and fresh signup. PG consumes started after deletion await the commit;
this does not cover a consume that won earlier.

Correctness/maintenance: context exit rolls back SQL/flush failures; all planes
remain explicitly scoped to the existing stored email hash. Optional portal auth
no longer controls cleanup. Kept standalone cleanup compatibility (existing tests
call it), documented that it is not full erasure. No exception swallowing/new
abstraction or external calls. No acceptance-blocking findings remain at review;
late issuance and already-consumed redemption are explicitly c2/c3, and report
count/read delivery remain snapshots. Same-agent self-review, not independent review.
