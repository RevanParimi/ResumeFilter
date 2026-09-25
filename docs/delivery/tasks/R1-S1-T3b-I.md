# R1-S1-T3b-I - Defined interview refusals during erasure

Status: done. Parent: [T3b](R1-S1-T3b.md). Date: 2026-09-21.

Trigger: candidate erasure commits after interview authorization/read and before
start/turn/completion persistence, or between turn commit and response reload.
Before: FK/StaleDataError or None dereference becomes HTTP 500. After: missing
candidate/session produces the existing LookupError/404 contract; no interview
text, assessment or audit can be recreated; other candidates remain intact.

Acceptance:
- Event-controlled competing SQLite/PostgreSQL connections cover start, turn,
  completion, retries, deletion-first and write-first ordering.
- Rollback precedes fresh parent lookup; unrelated integrity errors propagate.
- API start/answer/finish races and answer reload return 404, without private
  text or SQL parameters; ownership and normal completion remain covered.
- Real migrated scratch HTTP journey and restart preserve erasure and another
  candidate's interview. Full pytest, focused checks and recorded self-review.

Design: reuse existing foreign keys and ORM stale-update detection, translate
only verified missing-parent failures. No schema/UI/scoring changes. Derived
stores, current-consent policy and general simultaneous-answer serialization
are outside this child. No browser or live-provider claim applies.

Implementation: a store-local transaction context rolls back failed flush/commit
before checking the candidate/session afresh. It translates IntegrityError or
StaleDataError only when that parent is absent. Existing FK cascades remain the
retention boundary. Answer reload now uses the existing owned-session lookup.

Self-review (2026-09-21): HEAD `9f2f6cd` plus this session's interview store/service,
new concurrency tests and HTTP smoke diff. Specification: all three mutation
paths share the refusal boundary, including start's explicit flush; completion
and its audit remain one transaction. Correctness: rollback expires stale ORM
state before lookup; unrelated constraint failures propagate; no rejected SQL
parameters are logged; existing ownership checks and scoring remain unchanged.
The response can still reflect a successful write committed before erasure, but
the cascade removes its retained data. Review found no remaining blocking issue.
No independent review, browser execution or live-provider validation claimed.

Final evidence:
- Before fix: new regression file **4 failed, 7 passed, 7 PostgreSQL skips**,
  1 warning, 17.63s. Failures were start/turn/completion database errors and
  answer reload HTTP 500, not setup failures.
- Focused SQLite **76 passed, 7 PostgreSQL skips**, 1 warning, 17.06s. Includes
  API erasure before store lookup, during flush, and after turn commit; competing
  connection delete-first/write-first cases, retries and unrelated failure.
- Scratch migrated SQLite HTTP/restart **15/15**: normal advisory completion,
  portal/admin erasure while answer resolution is paused, 404 refusal, credential
  revocation, surviving other transcript and no erased sessions/turns/audit.
- Focused PostgreSQL **83 passed, zero skips**, 1 warning, 108.05s. PostgreSQL
  18.6 with Asia/Calcutta session timezone; fresh disposable cluster, unique
  test schemas, migration up/down/up and cluster shutdown passed. SQLite cases
  in the parameterized concurrency fixture also run in this command.
- Full SQLite pytest: **2213 passed, 17 PostgreSQL skips**, 32 warnings,
  425.56s. PostgreSQL focused evidence above covers the new database gate;
  no full PostgreSQL rerun is claimed for this change.
- Compile, `git diff --check` and local documentation-link/status checks passed.

Commands (project Python throughout):
```
.resume/Scripts/python.exe -m pytest tests/test_interview_erasure_concurrency.py -q --tb=short
.resume/Scripts/python.exe -m pytest tests/test_interview_erasure_concurrency.py tests/test_interview_erasure.py tests/test_interview_store.py tests/test_interview_service.py tests/test_interview_api.py tests/test_portal_service.py tests/test_portal_api.py -q --tb=short
.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_i.py
.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_i_postgres.py
.resume/Scripts/python.exe -m pytest -q --tb=short
.resume/Scripts/python.exe -m py_compile src/app/interview/store.py src/app/interview/service.py tests/test_interview_erasure_concurrency.py scripts/smoke_r1_s1_t3b_i.py
git diff --check
```
Logs: `.pytest_cache/r1-s1-t3b-i-{focused,smoke,suite}.txt`. The initial narrower
focused run also passed (61 passed, 7 skips); the expanded run above supersedes it.
PostgreSQL logs: `.pytest_cache/r1-s1-t3b-i-pg-{runner,focused,migrations,stop}.txt`.
Runner derives from the previous local V1 runner, uses its restored runtime
metadata, and runs the focused command above in a new disposable cluster; it
does not run a full PostgreSQL suite. Initial runner attempt failed before
database setup because the copied metadata filename was wrong; corrected and
rerun successfully. No application schema or data migration was introduced.

Preserved pre-existing uncommitted feature/timestamp work and the working database
(SHA256 `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`).
Next: **R1-S1-T3b-D** only in a new chat. Derived-store/ingest and disclosure-audit
races remain unvalidated; T3b/T3/F05 and R1-S1-Q remain open.
