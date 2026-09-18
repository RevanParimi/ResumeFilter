# R1-S1-T3a - Report writes racing erasure

Status: awaiting validation (2026-09-11). Parent: [R1-S1-T3](R1-S1-T3.md).

## Scope and acceptance

Existing CASCADE foreign keys prevent orphan inserts. A report UPDATE whose row
is erased after loading can instead raise StaleDataError; current integrity-race
logs serialize SQL parameters, potentially retaining rejected claims/notes.
Keep database constraints authoritative; translate only verified disappearance,
preserve unrelated errors, and log fixed metadata without SQL/content.
Preserve existing evaluation cancellation (report=null) and outcome 404 contracts.
Interview/derived stores are T3b; no data cleanup, schema or UI change.

| ID | Acceptance | Evidence |
|---|---|---|
| AC1 | Erase before insert/update/outcome flush rejects stale writes and preserves B | SQLite competing connections/retry passed; PostgreSQL pending |
| AC2 | A committed write followed by erase leaves no report/outcome | SQLite event-controlled ordering passed; PostgreSQL pending |
| AC3 | Rejected claims/notes do not escape through race logs | Rendered production logging assertions passed |
| AC4 | Unrelated integrity/stale errors remain errors | Bad org FKs on reports/outcomes and report-only disappearance passed |
| AC5 | In-flight evaluation cancels; outcomes fail 404; restart retains only B | HTTP/restart 19/19; both outcome API boundary regressions passed |

Required: focused/full pytest, SQLite and PostgreSQL competing connections,
HTTP/restart journey, recorded self-review and diff check. Browser not applicable
without a UI change. Existing schema used; no migration changes planned.

## Implementation evidence

- Red: `.resume/Scripts/python.exe -m pytest tests/test_report_erasure_concurrency.py -q --tb=short`
  produced **3 failed, 3 passed, 6 skipped**, 23.30s. Insert/outcome cases
  exposed synthetic private SQL parameters in rendered logs; UPDATE raised
  StaleDataError instead of SubjectErasedError. No setup failures counted.
  Log: `.pytest_cache/r1-s1-t3a-red.txt`.
- `src/app/reports/store.py`: catches StaleDataError alongside IntegrityError,
  rolls back and verifies candidate disappearance before classifying erasure.
  Both report/outcome race logs now carry only fixed location/error-class
  metadata. CASCADE/FKs remain the persistence guard; no schema/API/UI change.
  Existing ingest cancellation remains HTTP 200 with `report=null`; both outcome
  routes return 404 when erasure wins. No change to standalone ownership.
- Final focused command: `.resume/Scripts/python.exe -m pytest tests/test_report_erasure_concurrency.py tests/test_report_store.py tests/test_report_cascade.py tests/test_portal_service.py tests/test_portal_api.py tests/test_screening_ingest.py tests/test_flywheel_retention.py -q --tb=short`
  **55 passed, 6 skipped, 2 warnings**, 50.19s, exit 0. Log:
  `.pytest_cache/r1-s1-t3a-focused.txt`. Eight new passing cases; six missing
  PostgreSQL counterparts. SQLite uses a file DB and separate pooled
  connections, with events at before_flush and commit/delete boundaries.
  API tests erase after authorization but before the real outcome INSERT;
  these are TestClient boundary checks, not concurrent browser execution.
- Journey: `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3a.py`:
  **19/19 passed**, exit 0. Real uvicorn/default services and migrated scratch
  SQLite; a scratch-only wrapper pauses the real evaluator using asyncio
  events. Both portal/admin erasure cancel the paused report; stale outcomes
  and repeated deletes return 404. Restart uses unwrapped `app.main:app`;
  SQL inspection finds only B's candidate/report/outcome. Provider keys cleared,
  CWD scratch, memory vectors, null email, GitHub directed to closed loopback.
  Log: `.pytest_cache/r1-s1-t3a-smoke.txt`; scratch:
  `.pytest_cache/r1-s1-t3a-ujvmthq9`. No live-provider/browser claim.
- Previous full pytest result recovered from `.pytest_cache/r1-s1-t3a-suite.txt`
  (UTF-16 log): **2195 passed, 6 skipped, 42 warnings**, 423.01s. Command:
  `.resume/Scripts/python.exe -m pytest -q --tb=short`. This is recovered
  SQLite evidence from the implementation session, not a new PostgreSQL run.
- PostgreSQL: `DEE_TEST_DB_URL` unset; postgres/pg_ctl/docker not found in PATH,
  and no `C:/Program Files/PostgreSQL` installation found. Six explicit skips
  are missing evidence, not passing database validation. To validate, configure
  DEE_TEST_DB_URL for a disposable PostgreSQL database, then run the focused
  command above and full suite. The new fixture creates/drops only its own
  random `r1_race_*` schema. Existing schema used; no migration up/down/up gate.

## Self-review

Reviewed HEAD `3ec92cc3d6820b9d8eeed42f7269adebf4bff95a` plus the report-store
diff, new concurrency tests and smoke. Read portal erase, both outcome routes,
org scope and ingest cancellation callers. Specification review mapped AC1-5;
correctness review checked rollback/fresh lookup, both write/delete orders,
retries, unrelated errors, log egress, B preservation and scratch isolation.
Pre-existing uncommitted work and user data were not overwritten.
Reviewed report-store SHA256:
`C27BBA1699764C08C53D0BA022B57807327A6B6CF1BA78FA0F6692E8F80BB4CD`.

- High, reports/store.py race handlers: SQL exception text retained rejected
  claims/notes in logs. Fixed to metadata-only logs; rendered regressions cover
  report insert, outcome insert and unrelated FK errors.
- Medium, reports/store.py save: erasure after row load raised StaleDataError
  outside the defined refusal contract. Fixed with verified-disappearance
  translation; controlled UPDATE and report-only deletion regressions pass.
- Low, smoke retry assertion: first run incorrectly expected a 200 false result
  for repeated admin deletion. The established route returns 404; corrected
  the smoke assertion, then reran successfully. No API change was needed.
- `git diff --check` passed; new-file whitespace checks emitted no errors.
  No acceptance-blocking implementation findings remain within T3a. This is
  self-review, not independent review. PostgreSQL evidence is still required.
- Limits: no physical-media/WAL/log-history cleanup; previous logs are not
  erased by this change. Interview/derived-store and ingest races remain T3b.

## Validation follow-up (2026-09-10)

- `.env` now has DEE_TEST_DB_URL; the process environment does not. SQLAlchemy
  read-only connection probes using only this dotenv value failed with
  OperationalError; DNS resolution succeeded and the redacted error category
  was `password authentication failed`. No SQL/schema mutation ran. Requested
  that the user correct the local setting; no credentials recorded or edited.
- Reran the exact focused command above, with no process DEE_TEST_DB_URL:
  **55 passed, 6 skipped, 2 warnings**, 41.32s, exit 0. Log:
  `.pytest_cache/r1-s1-t3a-validation-focused.txt`.
- Reran `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3a.py`:
  **19/19 passed**, exit 0. Log: `.pytest_cache/r1-s1-t3a-validation-smoke.txt`;
  scratch: `.pytest_cache/r1-s1-t3a-fizu62b4`. Same real HTTP/restart scope,
  isolated SQLite and fake/disabled providers as the implementation journey.
- No application code edits. Self-reviewed HEAD and the existing report-store
  diff, concurrency fixture and smoke isolation. Report-store SHA256 still
  matches the implementation review above. No new implementation findings.
  Reviewed acceptance mapping: AC1/AC2 PostgreSQL evidence remains absent.
  Browser, live providers and independent review are not claimed.
- The shared full-suite teardown drops every schema matching SQL LIKE `s\_%`,
  unlike the concurrency fixture's per-test `r1_race_*` cleanup. Use only a
  verified disposable database. After credentials are corrected, first check
  connectivity and existing relations read-only. Load only DEE_TEST_DB_URL
  from `.env` into the pytest process (fixtures do not load dotenv themselves),
  then run the focused command and `.resume/Scripts/python.exe -m pytest -q
  --tb=short`. Never substitute the application database to bypass this gate.
- Project Python initially hit sandbox access denial; approved escalated
  execution enabled the probes and local tests. This was not a database
  authentication workaround. No new full-suite run was required for these
  documentation-only edits; the prior full result is recorded above.
- Final Node stdin check passed: five documents, 16 local links, task-status
  consistency and whitespace; `data/veritas.db` SHA256 unchanged from session
  start. `git -c core.safecrlf=false diff --check` passed.

## Validation retry (2026-09-11)

- Ran a PowerShell here-string through `.resume/Scripts/python.exe -`:
  `dotenv_values('.env')` selected only DEE_TEST_DB_URL, then SQLAlchemy
  `create_engine` used `connect_timeout=10` and `hide_parameters=True`.
  The probe planned `SET TRANSACTION READ ONLY` and schema/relation counts.
  Connection failed before any SQL: **OperationalError, authentication rejected**.
  Only the error class/category was printed; no credentials or raw exception.
  Initial sandbox launch could not access the Python base executable; the
  approved escalated retry reached PostgreSQL. No remote mutations occurred.
- Disposable storage remains unverified. No pytest or HTTP rerun this session;
  prior SQLite evidence above does not close the PostgreSQL gate. No code,
  schema, UI or environment-file changes; no other backlog task started.
- Self-review covered HEAD `3ec92cc3d6820b9d8eeed42f7269adebf4bff95a`
  plus the existing report-store diff, concurrency fixture and shared schema
  cleanup. Store SHA256 matches the implementation review. AC1/AC2 still lack
  PostgreSQL evidence; no new implementation findings within this review scope.
  This was not independent review or a new application validation run.
- Documentation check (`node -`, PowerShell stdin): five documents, eight local
  links, dates/statuses and scoped whitespace passed; roadmap scope is the new
  entry (an initial whole-file check found pre-existing historical whitespace).
  `git -c core.safecrlf=false diff --check` passed. Working `data/veritas.db`
  SHA256 remained `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

## Handoff

Next task is **R1-S1-T3a validation** after correcting test DB authentication;
use disposable PostgreSQL and do not repeat
implementation or close the parent based on SQLite evidence. After its gates
pass, T3b is the next development child in a separate chat. F05 and R1-S1-Q
remain open. No publishing, deployment or legacy-file cleanup performed.
