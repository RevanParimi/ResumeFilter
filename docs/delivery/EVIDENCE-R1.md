# PI-R1 completed evidence

Reference history, consolidated 2026-10-18. Start with [the handoff](../PROGRESS.md)
and [PI-R1](PI-R1.md) for current status. Each task's original contract,
decisions, validation and limits are retained below; historical next-task pointers
and commands describe their recorded date, not today's execution order or paths.
Moved pytest cases now live in their product-area modules. No old result is a new
execution, independent review, live-provider check or broader quality claim.

- [R1-S1-Q](#r1-s1-q)
- [R1-S1-T1](#r1-s1-t1)
- [R1-S1-T2](#r1-s1-t2)
- [R1-S1-T3](#r1-s1-t3)
- [R1-S1-T3a](#r1-s1-t3a)
- [R1-S1-T3a-V1](#r1-s1-t3a-v1)
- [R1-S1-T3b](#r1-s1-t3b)
- [R1-S1-T3b-D](#r1-s1-t3b-d)
- [R1-S1-T3b-D1](#r1-s1-t3b-d1)
- [R1-S1-T3b-D2](#r1-s1-t3b-d2)
- [R1-S1-T3b-D2a](#r1-s1-t3b-d2a)
- [R1-S1-T3b-D2b](#r1-s1-t3b-d2b)
- [R1-S1-T3b-D3](#r1-s1-t3b-d3)
- [R1-S1-T3b-D3a](#r1-s1-t3b-d3a)
- [R1-S1-T3b-D3b](#r1-s1-t3b-d3b)
- [R1-S1-T3b-D3b1](#r1-s1-t3b-d3b1)
- [R1-S1-T3b-D3b2](#r1-s1-t3b-d3b2)
- [R1-S1-T3b-D3b2a](#r1-s1-t3b-d3b2a)
- [R1-S1-T3b-D3b2b](#r1-s1-t3b-d3b2b)
- [R1-S1-T3b-D3b2b1](#r1-s1-t3b-d3b2b1)
- [R1-S1-T3b-D3b2b2](#r1-s1-t3b-d3b2b2)
- [R1-S1-T3b-D3c](#r1-s1-t3b-d3c)
- [R1-S1-T3b-D3c1](#r1-s1-t3b-d3c1)
- [R1-S1-T3b-D3c2](#r1-s1-t3b-d3c2)
- [R1-S1-T3b-D3c3](#r1-s1-t3b-d3c3)
- [R1-S1-T3b-D3d](#r1-s1-t3b-d3d)
- [R1-S1-T3b-D3d1](#r1-s1-t3b-d3d1)
- [R1-S1-T3b-D3d2](#r1-s1-t3b-d3d2)
- [R1-S1-T3b-D3d2a](#r1-s1-t3b-d3d2a)
- [R1-S1-T3b-D3d2b](#r1-s1-t3b-d3d2b)
- [R1-S1-T3b-D3d2c](#r1-s1-t3b-d3d2c)
- [R1-S1-T3b-D3d2c1](#r1-s1-t3b-d3d2c1)
- [R1-S1-T3b-D3d2c2](#r1-s1-t3b-d3d2c2)
- [R1-S1-T3b-D3d2c3](#r1-s1-t3b-d3d2c3)
- [R1-S1-T3b-D3d2d](#r1-s1-t3b-d3d2d)
- [R1-S1-T3b-D3d2d1](#r1-s1-t3b-d3d2d1)
- [R1-S1-T3b-D3d2d2](#r1-s1-t3b-d3d2d2)
- [R1-S1-T3b-D3d2d2a](#r1-s1-t3b-d3d2d2a)
- [R1-S1-T3b-D3d2d2b](#r1-s1-t3b-d3d2d2b)
- [R1-S1-T3b-D3d2d2b1](#r1-s1-t3b-d3d2d2b1)
- [R1-S1-T3b-D3d2d2b2](#r1-s1-t3b-d3d2d2b2)
- [R1-S1-T3b-D3d2d2b2a](#r1-s1-t3b-d3d2d2b2a)
- [R1-S1-T3b-D3d2d2b2b](#r1-s1-t3b-d3d2d2b2b)
- [R1-S1-T3b-D3d2d2c](#r1-s1-t3b-d3d2d2c)
- [R1-S1-T3b-D3d2d3](#r1-s1-t3b-d3d2d3)
- [R1-S1-T3b-D3d2d4](#r1-s1-t3b-d3d2d4)
- [R1-S1-T3b-I](#r1-s1-t3b-i)
- [R1-S2-Q](#r1-s2-q)
- [R1-S2-T1](#r1-s2-t1)
- [R1-S2-T2](#r1-s2-t2)
- [R1-S2-T3](#r1-s2-t3)
- [R1-S2-T4](#r1-s2-t4)
- [R1-S2-T4A](#r1-s2-t4a)
- [R1-S2-T4B](#r1-s2-t4b)

## <a id="r1-s1-q"></a>R1-S1-Q - Sprint integration review

Status: done (2026-10-06; bounded sprint acceptance complete).
PI/sprint: [PI-R1 / R1-S1](PI-R1.md).
Finding: F05. Prerequisites: [T1](#r1-s1-t1), [T2](#r1-s1-t2),
[T3](#r1-s1-t3) done; [combined development evidence](#r1-s1-t3b-d3d2d3)
and [actual empty legacy inventory](#r1-s1-t3b-d3d2d4).

### <a id="r1-s1-q--acceptance-contract"></a>Acceptance contract

This gate tests the integrated sprint, rather than another development child.
Use the actual app composition, migrated disposable stores and fake/disabled
external providers. Reuse existing regression and HTTP/browser harnesses.

- Evaluate multiple candidates in two tenants; populate reports/outcomes,
  sources/owned curation, interviews, login state, screening inputs, consents,
  audits, fingerprints and feature vectors. Erase through portal and admin;
  restart and inspect retained sinks. Target content/credentials must stay absent,
  survivors intact, old retries refused, and fresh submissions permitted.
- Pause evaluation before report persistence, erase, then release: the defined
  cancellation must not recreate reports/outcomes or text. Re-run controlled
  write/delete interleavings on SQLite and PostgreSQL; no sleep-based race proof.
- Verify legacy-file dry-run/default preservation and explicit synthetic cleanup;
  production must create no unmanaged flywheel copy. Preserve the working DB,
  prior edits and legacy user files. The actual D4 inventory supplies only its
  named-database snapshot; no new working cleanup is in scope.
- Re-run migrated HTTP/restart journeys on both dialects, PostgreSQL migration
  head/base/head, full pytest, UI bindings/syntax and real Chrome reviewer plus
  screening refusal/reload/fresh-upload actions. Bindings are not browser proof.
- Record a separate specification/correctness diff self-review, exact commands,
  results and limits. Missing required evidence leaves this gate awaiting
  validation. No independent review, live-provider or quality claim is implied.

Supported limits remain explicit: final response reads are snapshots; completed
anonymous screening scalars remain; older unresolved input is paused with its
original TTL; separately committed fresh capture can recur. Fixed observation
expiry needs startup/maintenance for physical deletion; other workers refresh
on restart. Approved vocabulary is human-selected, not anonymization. Backups,
history and physical-media erasure are outside this gate. Consent/identity races
remain R1-S2. Do not start R1-S2 in this session.

### <a id="r1-s1-q--evidence-and-review"></a>Evidence and review

R1-S1 and F05's current-system remediation gate close within this contract and
the recorded inventory/retention limits. Future-media erasure remains R5-S1-T4;
PI-R1 remains open for R1-S2. No application/schema/UI
behavior changed. Three harness corrections strengthen the sprint gate:
`smoke_r1_s1_t3a.py` now asserts the supported 422 `candidate_erased` refusal;
`smoke_r1_s1_t3b_d3d2d3.py` seeds all candidate-FK SQL tables and checks saved
child IDs directly after erasure, alongside full survivor/rollback comparisons.
The curation browser driver waits for completed `/auth/me` startup and the
reactively rendered operator form before entering credentials.

Separate same-agent review: HEAD `5480498`, the preserved pending login/aggregate/
curation changes (including 0028 and reviewer UI), and these three harness revisions.
Specification pass maps T1/T2/T3 and the sprint journey to current commands.
Correctness pass traces both deletion routes, SQL cascades/child IDs, login
transaction ordering, report/outcome refusal, source capture ownership, screening
retry/TTL, curation expiry/approval/legacy compatibility, API status and reviewer
reload/error behavior. Scratch setup disables providers, uses capture mail and
owned schemas/processes, and leaves working storage untouched. This is self-review,
not independent review; synthetic behavior is not empirical model-quality proof.

Findings resolved in validation code:
- **Medium, stale smoke contract**, `smoke_r1_s1_t3a.py:upload/main`: erasure while
  evaluation is paused yields the supported 422, but the old smoke required 200
  with a null report and a SQL-race log. Initial invocation failed at `/candidates`
  status 422 after successful deletion. The corrected response/log checks pass
  both routes, absence/retry and unwrapped restart (19/19).
- **Medium, retained-sink coverage**, combined smoke `snapshot/gone`: previously
  unpopulated ledger, verification, request and outcome sinks could hide a broken
  cascade. Seed them over real HTTP, assert schema coverage of candidate FKs,
  and check saved child IDs without joins to erased parents. Final SQLite and
  PostgreSQL journeys passed 15/15 each. No application defect
  is implied by this coverage correction.
- **Medium, browser readiness**, `check_ui_curation_browser.py:run_browser`:
  the initial form-presence check accepted prerendered HTML before startup.
  The failed run timed out at OTP with no `/auth/admin/login` request in the
  scratch log. Wait for completed `/auth/me` and rendered operator sign-in,
  and assert clicks/type actions. Final browser/legacy journey passed 36/36,
  including both console/exception checks and actual rendered review actions.

No acceptance-blocking finding remains. Final review checked the completed
commands against the acceptance contract, the three final harness revisions,
615-file reviewed-state manifest, preservation and final status/next-pointer diff.
Source/binding checks, synthetic providers and self-review retain their stated
limits; no independent review, CI, deployment or empirical quality claim.

### <a id="r1-s1-q--final-validation"></a>Final validation

All Python commands use `.resume/Scripts/python.exe`. Local ignored runners/logs
are evidence conveniences, not portable setup guarantees. All application servers
use migrated synthetic storage, NullLLM/fake providers, capture/null mail, fresh
browser profiles and scratch working directories without live `.env` inheritance.

The table commands use `-u` before each script. PostgreSQL variants append
`--postgres`; browser commands below use SQLite. Final expanded combined smoke
was rerun directly after its child-ID/schema assertions were added.

| Script and arguments | SQLite result | PostgreSQL result |
|---|---|---|
| `scripts/smoke_r1_s1_t1.py` | 16/16 | Not a PG-specific gate |
| `scripts/smoke_r1_s1_t2.py` | 10/10 CLI checks | File-only contract |
| `scripts/smoke_r1_s1_t3a.py` | 19/19 | Controlled PG pytest covers report/outcome write races |
| `scripts/smoke_r1_s1_t3b_d3d2d3.py` | 15/15, final expanded sinks | 15/15 |
| `scripts/smoke_r1_s1_t3b_d3d1.py` | 36/36 | 36/36 |
| `scripts/smoke_r1_s1_t3b_d3d2a.py` | 29/29 | 29/29 |
| `scripts/smoke_r1_s1_t3b_d3d2b.py` | 29/29 | 29/29 |
| `scripts/smoke_r1_s1_t3b_d3d2b.py --aggregates` | 41/41 | 41/41 |
| `scripts/smoke_r1_s1_t3b_d3b2b2.py --browser` | 21/21, real Chrome | 17/17 without `--browser` |
| `scripts/smoke_curation_activation.py --browser --legacy-disposition` | 36/36, real Chrome | PG store/migration/legacy pytest gate |

These checks ran via `.resume/Scripts/python.exe
.pytest_cache/run_r1_s1_q_journeys.py`, with the final expanded combined and
corrected curation-browser commands rerun directly. The two interrupted journey
runner invocations failed on the stale smoke/readiness assertions above; their
independent successful commands are retained. Both final browser journeys report
no console errors or uncaught exceptions. Chrome requires internet CDN assets;
backend/provider checks are offline. No browser-on-PostgreSQL claim.

Full regression: `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_q_full.py`
invoked `-m pytest -q --tb=short` with cleared provider/config environment:
**2682 passed, 331 skipped, 110 warnings**, 798.32s; runner exit 0 (808.55s).
Skips include unconfigured PostgreSQL counterparts and SQLite variants of PG-only
lock cases. Existing SQLite expression-index reflection and Starlette/httpx
deprecation warnings; no failures.
Provisional runs were stopped while revising smoke assertions; only the final
complete result counts. Application, tests and migrations are unchanged;
the browser-driver revision is checked by its separate real-browser rerun.

PostgreSQL: `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_q_postgres.py`
owns a fresh disposable PG 18.6 cluster, Asia/Calcutta. Migration head/base/head
passed. Focused command is `-m pytest -q` with the 28 exact file arguments in
[D3's focused collection](#r1-s1-t3b-d3d2d3), followed by
`tests/test_flywheel_io.py tests/test_report.py tests/test_report_cascade.py
tests/test_portal_service.py tests/test_portal_api.py
tests/test_legacy_flywheel_cleanup.py --tb=short`. It runs both dialect fixture
variants: **827 passed, 36 skipped, 94 warnings**, 1232.49s; runner exit 0
(1242.78s). Skips are SQLite variants of PG-only lock cases; existing reflection
and deprecation warnings, no failures. All six PG HTTP/restart commands passed;
runner exit 0 and clean cluster shutdown (`stop: exit=0`, 20.07s). No
full-PostgreSQL-suite or remote-server claim.

Static: `node scripts/check_ui_bindings.js` passed (425 bindings / 10 states);
`node --check frontend/api.js`; `node --check frontend/support.js` passed.
`-m py_compile scripts/smoke_r1_s1_t3a.py scripts/smoke_r1_s1_t3b_d3d2d3.py`
and separate `-m py_compile scripts/check_ui_curation_browser.py` passed.
`git -c core.safecrlf=false diff --check` passed on the reviewed code.
Local artifacts: `.pytest_cache/r1-s1-q-*`, reviewed diff and 615-file code hash
manifest. Final documentation/preservation check is recorded below.

Final `.resume/Scripts/python.exe .pytest_cache/check_r1_s1_q_docs.py` passed
**59 documents / 313 local links**, Q/sprint closure and pending next-task
consistency, completed regression/shutdown evidence, unchanged prior files outside
the explicit task edits, and all **615 reviewed code files**. Final
`git -c core.safecrlf=false diff --check` passed. The saved combined/session diff
and hash manifests remain ignored local artifacts; this record owns durable results.

No deployment, external message, scheduler, working migration or user-data
cleanup occurred. Original database SHA256 remains
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

Next: **R1-S2-T1 - Apply current consent to serving**. Not started here.

## <a id="r1-s1-t1"></a>R1-S1-T1 — Make new flywheel records erasable

Status: done (2026-09-09). PI/sprint: PI-R1 / R1-S1. Audit finding: F05.
Prerequisites: F01–F04 recorded complete; see ../BASELINE.md.
Read ../WORKFLOW.md and only this task's section in ../PI-R1.md.

### <a id="r1-s1-t1--context-and-scope"></a>Context and scope

Before this task, `graph/nodes/report.py` logged claim_text and probes before
report persistence into an append-only JSONL production sink. Portal erasure
cleared candidate-linked SQL/auth data but could not erase those copies. The
original audit reproduced four retained claim records after candidate/report
deletion. The production sink is now non-retaining; existing legacy files remain.

This task covers newly written records and ordinary erase paths. Legacy-file
handling is R1-S1-T2; in-flight/concurrent erasure is R1-S1-T3. F05 remains open
until those tasks and R1-S1-Q pass. Do not rewrite existing user files now.

Entry points: `src/app/services/flywheel.py`, `src/app/services/__init__.py`,
`src/app/graph/nodes/report.py`, `src/app/graph/state.py`,
`src/app/portal/service.py`, outcome-writing callers found with
`rg -n 'flywheel\.log|build_flywheel' src tests`.

Before implementation, trace whether every evaluation has a durable candidate
owner at logging time. Do not invent an owner for standalone reports. Decide
whether training needs verbatim text at all. Prefer dropping unnecessary text;
if retained, use a deletable candidate-linked store and explicit lifecycle.
Record the choice and compatibility impact here. Avoid a new storage framework.

### <a id="r1-s1-t1--acceptance-and-test-mapping"></a>Acceptance and test mapping

| ID | Observable criterion | Required scenario | Result |
|---|---|---|---|
| AC1 | New claim/probe/outcome text is not retained in unmanaged files | Evaluate and record outcome through actual callers, inspect all selected sinks | Passed: retention pytest + both HTTP smokes |
| AC2 | Erasing A removes A's retained content but preserves B | Two candidates/reports; portal and admin erase entry points; repeat erase | Passed: parameterized retention test + restart smoke |
| AC3 | Standalone evaluation obeys an explicit retention policy | Evaluation without candidate linkage; no guessed identity or orphan text | Passed: standalone retention test + smoke |
| AC4 | Persistence/deletion failures are observable and honest | Failing sink/transaction; no false completed-erasure response | Passed: report/outcome/erase failure tests; no second sink exists |
| AC5 | Production wiring uses the same lifecycle as test wiring | Build actual app against migrated scratch storage, evaluate → erase → inspect | Passed: default-app HTTP startup/restart smoke |
| AC6 | Existing report/outcome and ownership behavior remains compatible | Relevant report/portal regressions and full suite | Passed: focused 57; full suite 2163 |

Start with `tests/test_flywheel_io.py`, `tests/test_report.py`,
`tests/test_report_outcomes.py`, `tests/test_portal_service.py` and
`tests/test_portal_api.py`; add behavioral cases where appropriate. Existing
audit probe artifacts are diagnostic context, not the acceptance suite.

Planned focused command (extend after tracing callers):

```powershell
.\.resume\Scripts\python.exe -m pytest tests/test_flywheel_io.py tests/test_report.py tests/test_report_outcomes.py tests/test_portal_service.py tests/test_portal_api.py -q --tb=short
```

Also required: full pytest; an isolated real-app HTTP smoke using the existing
`scripts/_smoke.py` pattern; PostgreSQL/migration checks if storage schema or SQL
semantics change. No UI behavior is intended, so browser checks are not required
unless implementation changes a user flow. Do not run tests on `data/veritas.db`.

### <a id="r1-s1-t1--evidence-and-review-fill-during-implementation"></a>Evidence and review (fill during implementation)

- Reproducer before fix: six tests in `tests/test_flywheel_retention.py` failed
  on the JSONL existence/append assertions (not setup errors). Log:
  `.pytest_cache/r1-s1-t1-red.txt` (6 failed, 1 warning, 17.04s).
- Design: eliminate the redundant durable event stream. No application reader
  consumes JSONL; quality labels read SQL reports/outcomes and training joins
  read SQL features/ledger. `build_flywheel` now returns `NullFlywheel`; removed
  the JSONL writer. The in-memory observer is explicitly test-only. Existing
  report persistence, outcome persistence and erasure SQL are unchanged.
- Compatibility: `flywheel_path` is accepted but ignored for new writes, even
  if it names an existing file. The internal `JsonlFlywheel` class is removed.
  External JSONL consumers must use existing SQL report/outcome access instead.
  No existing files or database rows are cleaned up by this implementation.
- Focused tests: 57 passed, 1 warning, 16.21s; log
  `.pytest_cache/r1-s1-t1-focused.txt`. Includes seven new retention scenarios
  and three replacement policy tests for the retired writer's I/O behavior.
  Exact file selection: `tests/test_flywheel_retention.py`,
  `tests/test_flywheel_io.py`, `tests/test_report.py`,
  `tests/test_report_outcomes.py`, `tests/test_portal_service.py`,
  `tests/test_portal_api.py`, `tests/test_api.py`,
  `tests/test_screening_outcome_api.py`, using `-m pytest -q --tb=short`.
- Real app smoke: `scripts/smoke_r1_s1_t1.py`, 16/16 passed. Starts and restarts
  actual uvicorn/default service composition on migrated synthetic SQLite;
  verifies both erase doors, preserved other-user outcomes across restart,
  standalone ownership policy and byte-identical legacy file. Log:
  `.pytest_cache/r1-s1-t1-smoke.txt`. Provider calls disabled, CWD scratch,
  inherited DEE_* removed. The existing outcome smoke now checks no file.
- Employer outcome smoke: 21/21 passed with actual cookie/CSRF sessions,
  captured synthetic email, org-scoped outcomes and erasure. Executed through
  `.resume/Scripts/python.exe .pytest_cache/run_r1_outcome_smoke.py`, an isolated
  wrapper for `scripts/smoke_s85_outcome.py` that clears DEE_* variables, uses
  scratch CWD/PYTHONPATH and a free port, and blocks external GitHub access.
  Log: `.pytest_cache/r1-s1-t1-outcome-smoke.txt`. Initial inline wrapper had
  a shell quoting error before execution; corrected to a script before this run.
- Self-review: specification then correctness review of all flywheel writers,
  builder, portal/report/outcome paths and test fixture behavior. Found and
  corrected the new smoke's weak `bool(response_dict)` assertion to check the
  persisted outcome count and note. Reviewed orphan-on-save-failure and honest
  erasure failure; both covered. No new SQL, migration, concurrency primitive,
  or frontend change: PostgreSQL/browser gates not applicable to this task.
- Reviewed code state: local changes on `3ec92cc3d6820b9d8eeed42f7269adebf4bff95a`;
  pre-existing uncommitted F01–F04 work preserved. Runtime flywheel file SHA256:
  `C722B84CB3C1FDC6F7381BB90DA1ED794326112D51F314F98B9FE215C76D9D78`.
  Review includes the new retention tests/smoke, retired writer tests and
  current documentation/config compatibility. No independent review claimed.
- Full pytest: `.resume/Scripts/python.exe -m pytest -q --tb=short`:
  **2163 passed**, 42 warnings, 286.40s. Log:
  `.pytest_cache/r1-s1-t1-suite.txt`. Warnings remain dependency deprecations
  and SQLite expression-index reflection limitations; no failures or skips
  reported. No application code changed after this validated state.
- Open limitations: legacy retention and concurrent erasure are explicitly
  unresolved until T2/T3. No production cleanup or external requests authorized.

### <a id="r1-s1-t1--handoff"></a>Handoff

Implementation, acceptance checks, self-review and full regression complete.
After this task passes its gates, next is **R1-S1-T2** in a new chat.

## <a id="r1-s1-t2"></a>R1-S1-T2 — Handle existing flywheel files safely

Status: done (2026-09-09). PI/sprint: PI-R1 / R1-S1. Audit finding: F05.
Prerequisite: [R1-S1-T1](#r1-s1-t1), completed non-retaining production sink.

### <a id="r1-s1-t2--context-and-scope"></a>Context and scope

Legacy JSONL contains claim/probe/outcome text without an erasure lifecycle.
Add an offline, explicit-file CLI; never discover or apply to existing user data.
The T1 retention decision also applies to historical copies: retain zero rows
when cleanup is explicitly applied. No selective migration or identity guessing.
SQL reports/outcomes remain authoritative and are never opened by this utility.
All ownership is reported as unresolved: even a candidate/report reference is
an assertion, not proof of present ownership or consent. Known, deleted, missing
and ambiguous owners therefore receive the same whole-record removal policy.

Entry points reviewed: historical flywheel writer, current report-node and
outcome callers, reports/store.py. New code: scripts/cleanup_legacy_flywheel.py;
tests/test_legacy_flywheel_cleanup.py; operator policy in docs/LEGACY_FLYWHEEL.md.

### <a id="r1-s1-t2--acceptance-and-test-mapping"></a>Acceptance and test mapping

| ID | Observable criterion | Scenario | Result |
|---|---|---|---|
| AC1 | Dry-run preserves bytes and emits only fixed counts/digest | Mixed historical text, malformed/oversized lines | Passed: pytest + CLI smoke |
| AC2 | All ownership states have explicit outcomes without guessing | Known/deleted/missing/ambiguous synthetic references | Passed: policy + removal test/smoke |
| AC3 | Apply affects only the explicit file, is idempotent, and refuses changed input | Digest mismatch, retry, sibling preservation | Passed: pytest + CLI smoke |
| AC4 | Interrupted replacement preserves the source or leaves it empty | Injected pre-replace failure and subprocess interruption | Passed: both child-process exit boundaries + retry |
| AC5 | Paths and failures fail closed without leaking text | Links, directories, relative paths, read/replace failures | Passed: pytest, including real Windows junction |

Required: focused and full pytest; real CLI subprocess journey on synthetic
files; recorded self-review and diff check. No application/SQL/API/UI behavior
changes, so HTTP/browser/PostgreSQL and migration gates do not apply.

### <a id="r1-s1-t2--implementation-evidence"></a>Implementation evidence

- New-feature red: `.resume/Scripts/python.exe -m pytest tests/test_legacy_flywheel_cleanup.py -q --tb=short`
  produced **2 failed**, 1.57s against the CLI scaffold's explicit
  `cleanup_unavailable` result. Both dry-run and apply behavior were missing;
  no fixture/import failure counted as reproduction. Initial sandbox invocation
  could not access the venv's base executable; approved escalation used thereafter.
- Implemented `scripts/cleanup_legacy_flywheel.py` (stdlib only) and
  [operator policy](../LEGACY_FLYWHEEL.md). No app, config or store edits.
  Explicit apply requires an inspected SHA256 and stopped writers. An empty
  same-directory temporary file is synced and atomically replaces the source.
  No backup; interruption before replacement leaves the original for retry.
- Final focused command: `.resume/Scripts/python.exe -m pytest tests/test_legacy_flywheel_cleanup.py tests/test_flywheel_io.py tests/test_flywheel_retention.py -q --tb=short`:
  **31 passed**, 1 dependency warning, 9.92s (21 new cleanup cases).
- CLI journey: `.resume/Scripts/python.exe scripts/smoke_r1_s1_t2.py`:
  **10/10 passed**, exit 0. Real CLI children, synthetic temporary copies,
  counts-only inspection, digest refusal, apply, sibling preservation, retry,
  reinspection and no backup. Pytest also abruptly exits real child processes
  before/after replacement to verify recovery and empty-only temp residue.
- Full suite: `.resume/Scripts/python.exe -m pytest -q --tb=short *> .pytest_cache/r1-s1-t2-suite.txt`:
  **2186 passed**, 42 warnings, 344.08s; exit 0, no failures/skips reported.
  Warnings are dependency deprecations and SQLite expression-index reflection
  limitations. No code changes after the final focused/smoke/full checks.
- Reviewed state: HEAD `3ec92cc3d6820b9d8eeed42f7269adebf4bff95a` plus
  the new cleanup utility, new regression file, new smoke and this task's docs.
  Existing uncommitted F01–F04/T1 work and modified database preserved.
  Cleanup utility SHA256:
  `71F2DCEB1D951FBEB84508E0960B88CA1A365D89EA646253017F71F3791AA199`.

### <a id="r1-s1-t2--review"></a>Review

Self-review, specification then correctness, covering the new files and the
historical writer/current report and outcome callers. No independent review.

- Medium, metadata guard: initial Windows tests falsely refused unchanged files
  because `stat` and `fstat` expose different ctime values. Removed ctime from
  comparisons; device/inode/size/mtime and inspected digest remain. Final Windows
  subprocess tests pass, including mutation immediately before replacement.
- Medium, argument parser: default argparse abbreviation would accept `--app`
  as destructive `--apply`. Disabled abbreviation; regression proves refusal
  with unchanged source. All parser/OS errors use fixed codes without text.
- Reviewed ownership: no guessed join, deleted-report resurrection, partial
  de-identification or retained-row selection. All source bytes are discarded
  only under explicit whole-file apply, regardless of the parsed counts.
- Reviewed crash/retention: bounded line reads, fsynced empty temp, atomic replace,
  empty retry, missing-file refusal, source/sibling preservation, no data backup.
  Paths reject links/reparse ancestors, hardlinks, traversal and alternate streams.
  No acceptance-blocking findings remain. `git diff --check` and checks of the
  three untracked Python files passed with Windows CRLF handling; final docs
  links/status consistency also checked. `node .pytest_cache/check_r1_s1_t2_docs.js`
  passed for 5 files, 29 local links and T2-done/T3-next status consistency.
- Limits: exclusive directory control/stopped writers are preconditions, not
  a hostile-writer locking guarantee. Windows process-crash tests are not POSIX
  execution or power-loss evidence. No secure-media, cloud-history or backup
  erasure claim. No HTTP/browser/PostgreSQL/provider validation claimed or needed
  for this offline file-only task.

### <a id="r1-s1-t2--handoff"></a>Handoff

Done: acceptance, focused/full tests, subprocess journey and self-review complete.
Next: **R1-S1-T3**, preventing writes
after erasure; read its PI-R1 section and reports/store.py, portal/service.py,
tests/test_report_cascade.py and tests/test_interview_erasure.py. F05 stays open
through T3 and the sprint review. Existing user files have not been inspected
or changed by the CLI. Their cleanup remains a separate authorized operation.

## <a id="r1-s1-t3"></a>R1-S1-T3 - Prevent writes after candidate erasure

Status: done (2026-10-06; bounded acceptance and evidence complete). PI/sprint: PI-R1 / R1-S1. Finding: F05.
Prerequisites: T1 and T2 complete. See [workflow](WORKFLOW.md).

| Child | Scope | Status |
|---|---|---|
| [T3a](#r1-s1-t3a) | Report/outcome persistence and evaluation cancellation, including PostgreSQL timestamp validation. | Done |
| [T3b](#r1-s1-t3b) | Interview/derived-store writes, ingest and cross-store ordering. | Done |

Acceptance: stale candidate-linked work cannot undo erasure; unrelated candidates
survive, and clients receive defined refusals/cancellation. Review transaction
boundaries, not only preflight existence checks. Preserve consent, identity,
advisory scoring and fresh-upload policies.

Each child owns focused/full pytest, diff review, real HTTP/restart and controlled
SQLite/PostgreSQL evidence. Apply migration gates where required; screening
migrations 0024-0026 are documented in the relevant descendants. Do not close
T3, F05 or R1-S1-Q until all children and the combined acceptance evidence pass.
For the next leaf task use [PROGRESS.md](../PROGRESS.md); completed counts and
commands remain in leaf evidence records.

[D3d2d3](#r1-s1-t3b-d3d2d3) maps the completed combined acceptance to child
evidence and limits. [D4](#r1-s1-t3b-d3d2d4) settles the named working-database
curation row-retention gap with an actual empty inventory. All development
children are complete; T3 closes within these recorded boundaries. The separate
[Q integration review](#r1-s1-q) closes the bounded sprint/F05 gate. Backup/history,
maintenance, response-snapshot and historical-input limits remain explicit.

## <a id="r1-s1-t3a"></a>R1-S1-T3a - Report writes racing erasure

Status: done (2026-09-21). Parent: [R1-S1-T3](#r1-s1-t3).

### <a id="r1-s1-t3a--scope-and-acceptance"></a>Scope and acceptance

Existing CASCADE foreign keys prevent orphan inserts. A report UPDATE whose row
is erased after loading can instead raise StaleDataError; current integrity-race
logs serialize SQL parameters, potentially retaining rejected claims/notes.
Keep database constraints authoritative; translate only verified disappearance,
preserve unrelated errors, and log fixed metadata without SQL/content.
Preserve existing evaluation cancellation (report=null) and outcome 404 contracts.
Interview/derived stores are T3b; no data cleanup, schema or UI change.

| ID | Acceptance | Evidence |
|---|---|---|
| AC1 | Erase before insert/update/outcome flush rejects stale writes and preserves B | SQLite and PostgreSQL competing connections/retry passed |
| AC2 | A committed write followed by erase leaves no report/outcome | SQLite and PostgreSQL event-controlled ordering passed |
| AC3 | Rejected claims/notes do not escape through race logs | Rendered production logging assertions passed |
| AC4 | Unrelated integrity/stale errors remain errors | Bad org FKs on reports/outcomes and report-only disappearance passed |
| AC5 | In-flight evaluation cancels; outcomes fail 404; restart retains only B | HTTP/restart 19/19; both outcome API boundary regressions passed |

Required: focused/full pytest, SQLite and PostgreSQL competing connections,
HTTP/restart journey, recorded self-review and diff check. Browser not applicable
without a UI change. Existing schema used; no migration changes planned.

### <a id="r1-s1-t3a--implementation-evidence"></a>Implementation evidence

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

### <a id="r1-s1-t3a--self-review"></a>Self-review

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

### <a id="r1-s1-t3a--validation-follow-up-2026-09-10"></a>Validation follow-up (2026-09-10)

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

### <a id="r1-s1-t3a--validation-retry-2026-09-11"></a>Validation retry (2026-09-11)

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

### <a id="r1-s1-t3a--postgresql-validation-2026-09-18-result-recovered-2026-09-21"></a>PostgreSQL validation (2026-09-18, result recovered 2026-09-21)

- Configured remote test URL still rejects authentication before SQL. Instead,
  initialized a disposable local PostgreSQL **18.6** cluster matching CI's major
  version, using the [EDB binary archive](https://www.enterprisedb.com/download-postgresql-binaries).
  Archive: `postgresql-18.6-3-windows-x64-binaries.zip`, observed SHA256
  `59F8CE701C63C2ED623C665A5E51B3EF6F2E37CCF837B68FFEED0742D0AE6ABD`.
  Runtime is in OS temp; loopback-only, random port/password, no Windows service
  or `.env` edits. Only this newly created cluster receives schema/data writes.
- Runner: `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3a_postgres.py`.
  Uses initdb, pg_ctl, a fresh `veritas_test` database and process-only
  DEE_TEST_DB_URL. Runs CI's Alembic up/down/up, the exact focused pytest command
  above, then full pytest. External providers disabled; pg_ctl stops in finally.
- First local migration up/down/up passed. Focused tests: **61 passed, 1 teardown
  error**, 2 warnings, 74.35s. Shared `_drop_postgres_test_schemas` exhausted
  default PostgreSQL lock storage by dropping every schema in one transaction.
  Reproducer log: `.pytest_cache/r1-s1-t3a-pg-cleanup-red.txt`.
- Validation fix in `tests/conftest.py`: finish the schema-list read transaction,
  then commit each DROP separately. No production change or raised lock limits.
  The existing real-PostgreSQL focused run is the regression for bounded cleanup.
  Rerun on a new cluster: **61 passed, zero skips, 2 warnings**, 61.64s, exit 0,
  including teardown. Log: `.pytest_cache/r1-s1-t3a-pg-focused.txt`. Migration
  up/down/up also passed again; log: `r1-s1-t3a-pg-migrations.txt` in the same
  directory. Recovered full result: **9 failed, 2192 passed, 32 warnings**,
  1150.32s. These feature timestamp/API failures block completion; bounded
  repair [R1-S1-T3a-V1](#r1-s1-t3a-v1) was completed on 2026-09-21.
- Reviewed current HEAD `eaa94ded275e6039f96f1f50f4fde67e2fc02bf8` plus this
  fixture diff. Report store, concurrency tests and HTTP smoke still match
  their implementation-session hashes. No independent review claimed.
  Fixture SHA256: `B1AC147E1DEDDAE068C3B64DD16D92A35941E7A93EBE8B5FF00C92E1AEACE613`.

### <a id="r1-s1-t3a--final-validation-2026-09-21"></a>Final validation (2026-09-21)

Validation prerequisite [R1-S1-T3a-V1](#r1-s1-t3a-v1) is done. Its record
contains exact commands, final code-state review and logs. Final PostgreSQL
focused: **93 passed**, zero skips, 2 warnings, 79.17s, including all T3a cases.
Full PostgreSQL: **2208 passed**, zero skips, 32 warnings, 1431.51s. Full SQLite:
**2198 passed, 10 PostgreSQL skips**, 32 warnings, 663.66s. Erasure HTTP/restart:
**19/19** on SQLite; feature HTTP/restart **12/12** on each backend. Migration
up/down/up, per-schema cleanup and clean cluster shutdown passed. Report-store
and shared-fixture hashes match their reviewed implementation states above.
No T3a acceptance gates remain open. This does not close parent T3 or F05.

### <a id="r1-s1-t3a--handoff"></a>Handoff

Next task is **R1-S1-T3b**, in a separate chat. Interview/derived-store and
ingest races, F05 and R1-S1-Q remain open. Historical shifted feature timestamps
need a separate repair policy. No publishing, deployment, user-data rewrite or
legacy-file cleanup performed. No independent review, browser or live-provider
validation is claimed.

## <a id="r1-s1-t3a-v1"></a>R1-S1-T3a-V1 - PostgreSQL feature timestamp compatibility

Status: done (2026-09-21). Validation prerequisite for [R1-S1-T3a](#r1-s1-t3a).
Finding: F03 residual discovered during the PostgreSQL validation gate.

### <a id="r1-s1-t3a-v1--behavior-and-acceptance"></a>Behavior and acceptance

FeatureStore stripped UTC tzinfo before binding to timezone-aware columns.
PostgreSQL interpreted those naive values in its session timezone, shifting
feature cuts/materialization times and emptying search/match/dashboard pools.
The prior full log (9 failed, 2192 passed, 32 warnings, 1150.32s) was recovered
from `.pytest_cache/r1-s1-t3a-pg-suite.txt`; the old handoff had missed it.

Removed `_key_dt`; existing `as_utc` now normalizes all six write/equality/cutoff
bindings without stripping tzinfo. SQLite drops tzinfo from normalized UTC
values and restores UTC on read. No scoring, consent, snapshot selection,
schema or UI contract change. Existing user records were not rewritten.

| Acceptance | Final evidence |
|---|---|
| Preserve cut/materialization instants on SQLite and PostgreSQL UTC/non-UTC | Six new cases: equivalent UTC/offset/naive inputs, microseconds, upsert identity; all pass with PostgreSQL configured |
| Keep newest, partial-refresh and historical pools consistent | Store and existing matching/dashboard/materialization/search API tests pass |
| Preserve erasure, T3a concurrency and defined API refusals | All T3a focused cases pass; real erasure HTTP/restart 19/19 |
| Validate actual application persistence and restart | New feature HTTP/restart 12/12 on SQLite and PostgreSQL Asia/Calcutta |

### <a id="r1-s1-t3a-v1--runs-and-reproducible-commands"></a>Runs and reproducible commands

| Run | Result |
|---|---|
| Red PostgreSQL focused | 11 failed, 82 passed, 2 warnings, 123.60s: original nine failures plus two new Asia/Calcutta cases |
| Final SQLite focused (first five files below) | 28 passed, 4 PostgreSQL skips, 1 warning, 7.58s |
| Final PostgreSQL focused (all files below) | 93 passed, zero skips, 2 warnings, 79.17s |
| Full SQLite | 2198 passed, 10 PostgreSQL skips, 32 warnings, 663.66s |
| Full PostgreSQL | 2208 passed, zero skips, 32 warnings, 1431.51s |
| Feature HTTP/restart, final isolation rerun | 12/12 on each database; public schema stayed empty and owned schemas were cleaned |
| T3a erasure HTTP/restart | 19/19 on migrated scratch SQLite |
| PostgreSQL migration up/down/up | Passed; schema teardown and cluster shutdown exited 0 |

Focused command uses `.resume/Scripts/python.exe -m pytest` with these files,
in this order, followed by `-q --tb=short`:

```text
tests/test_feature_timestamps.py tests/test_feature_store.py
tests/test_features_materialize_api.py tests/test_dashboard_api.py
tests/test_talent_search_api.py tests/test_report_erasure_concurrency.py
tests/test_report_store.py tests/test_report_cascade.py
tests/test_portal_service.py tests/test_portal_api.py
tests/test_screening_ingest.py tests/test_flywheel_retention.py
```

Full command: `.resume/Scripts/python.exe -m pytest -q --tb=short`, once with
DEE_TEST_DB_URL set to the new disposable PostgreSQL cluster and once unset.
Providers disabled and test settings isolated in the child environments.
Feature journey: `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3a_v1.py`
(with `--postgres` for PostgreSQL); T3a journey:
`.resume/Scripts/python.exe scripts/smoke_r1_s1_t3a.py`.

Local orchestrators actually run: `.resume/Scripts/python.exe
.pytest_cache/run_r1_s1_t3a_v1_postgres.py` (also `--red` before the fix), and
`.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3a_v1_journeys.py` for final
smoke isolation. The red diagnostic invoked pytest.main with the focused list
and `-q --tb=short -vv -s -p no:faulthandler`, plus periodic stack dumps. Two
silent startup attempts and an extra collection diagnostic were stopped and
are not test results; stack traces showed filesystem reads during imports.

Logs in `.pytest_cache/`: `r1-s1-t3a-v1-pg-{red,focused,suite,migrations}.txt`,
`r1-s1-t3a-v1-sqlite-{suite,erasure-smoke}.txt`, and final
`r1-s1-t3a-v1-journey-{postgres,sqlite}-smoke-final.txt`. Earlier feature smoke
runs also passed; the final reruns cover the reviewed isolation fix.

### <a id="r1-s1-t3a-v1--self-review-and-environment"></a>Self-review and environment

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus feature-store,
new timestamp regressions and smoke. Specification review mapped every criterion
above to final evidence. Correctness review traced all bindings, read conversion,
view/version predicates, CASCADE and materialize/context/search/match/board
callers. Existing consent/scoring policy and historical user data are preserved.

Review findings in the new smoke setup: URL query encoding conflicted with
Alembic interpolation, and inherited URL `options` could override its owned
schema. Fixed by passing schema/timezone through child PGOPTIONS and removing
URL options. Final real journeys deliberately supplied `search_path=public`,
then verified public candidates remained zero and owned schemas were gone.
No unresolved acceptance-blocking findings. Same-agent self-review only.

Reviewed feature-store SHA256:
`683C0A4133903832BAF3CAC69E57915A4A4369B7A1BF25D2F30BFDCD0E33BD16`.
Final smoke SHA256:
`C62676FA3E0983A3AB03D5DD3558804A39F3FF686B262D7087F1CB4105A542BF`.
Report-store and shared-fixture hashes match T3a's prior review. Compile,
whitespace, local documentation links/status consistency and
`git -c core.safecrlf=false diff --check` passed. Working `data/veritas.db` SHA256
remained `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

Restored the missing matching CPython 3.13.11 base from the signed
[Python installer](https://www.python.org/downloads/release/python-31311/),
retaining .resume/dependencies. Restored portable PostgreSQL 18.6 with the same
archive SHA256 recorded in T3a; random loopback ports/passwords, new disposable
clusters, no Windows PostgreSQL service or .env changes. Runtime metadata:
`.pytest_cache/r1-s1-t3a-v1-pg-runtime.json`. Remote credentials were not rechecked.

### <a id="r1-s1-t3a-v1--handoff-and-limits"></a>Handoff and limits

V1 is done and closes T3a's remaining validation gate. Next task: **R1-S1-T3b**
in a separate chat. Parent T3, F05 and R1-S1-Q remain open. Historical feature
timestamps written under non-UTC PostgreSQL may still be shifted; repair needs
an explicit policy, not a guessed timezone. No user-data/legacy-file cleanup,
browser execution, independent review or live-provider validation claimed.

## <a id="r1-s1-t3b"></a>R1-S1-T3b - Interview and derived-store writes racing erasure

Status: done (2026-10-06; bounded acceptance and evidence complete). Parent: [T3](#r1-s1-t3).

| Child | Scope | Status |
|---|---|---|
| [I](#r1-s1-t3b-i) | Interview start/turn/completion refusal, transactional audit rollback and answer reload. | Done |
| [D](#r1-s1-t3b-d) | Derived stores, ingest, retained screening input and cross-store ordering. | Done |

Acceptance: each persistence boundary must refuse stale work safely and preserve
other candidates; cascade constraints alone do not establish the response or
interruption contract. Entry points are interview/store.py and the derived-store
callers named in D. Child evidence owns regression counts and commands.

Both children and their required validation are complete. Combined acceptance
and limits: [D3d2d3](#r1-s1-t3b-d3d2d3). The actual empty working-database
curation inventory in [D4](#r1-s1-t3b-d3d2d4) settles the last development gap.
This closes the bounded parent, without whole-request or backup erasure claims.
Sprint/F05 gate and limits: [Q](#r1-s1-q). Next task: [PROGRESS.md](../PROGRESS.md).

## <a id="r1-s1-t3b-d"></a>R1-S1-T3b-D - Derived stores and ingest erasure races

Status: done (2026-10-06; bounded acceptance and evidence complete). Parent: [T3b](#r1-s1-t3b).

| Child | Scope | Status |
|---|---|---|
| [D1](#r1-s1-t3b-d1) | Feature-vector writes and materialization API accounting. | Done |
| [D2](#r1-s1-t3b-d2) | Resolved ingest and post-ingest fingerprints. | Done |
| [D3](#r1-s1-t3b-d3) | Screening input/completion, candidate-linked audits and cross-store ordering. | Done |

Acceptance: refused writes cannot recreate erased data; surviving subjects,
idempotent duplicates and legitimate retries retain their behavior. Cover each
separate commit boundary with controlled regressions, including disclosures
computed from an earlier loaded pool. Do not change consent/identity policy.

All children and required evidence are complete. Combined acceptance mapping:
[D3d2d3](#r1-s1-t3b-d3d2d3); actual empty working-database curation inventory:
[D4](#r1-s1-t3b-d3d2d4). The bounded parent closes; recorded consent/identity,
response-snapshot and storage-copy limits remain. Child records own commands;
[PROGRESS.md](../PROGRESS.md) names the separate sprint review next.

## <a id="r1-s1-t3b-d1"></a>R1-S1-T3b-D1 - Feature-vector writes racing erasure

Status: done. Parent: [D](#r1-s1-t3b-d). Date: 2026-09-21.

Trigger: erasure commits after feature computation/vector lookup and before
insert/update flush. Before: database exception becomes HTTP 500. Intended:
upsert returns None for an erased candidate; materialization counts that item
as skipped and continues other candidates. Successful writes still return IDs.

Acceptance:
- Event-controlled SQLite/PostgreSQL connections exercise insert and update,
  delete-first/write-first orderings and stale retry. No erased vector survives;
  another candidate's vector remains unchanged.
- Rollback before fresh parent lookup; unrelated integrity/stale-row failures
  remain errors. No SQL parameters or feature payload in handled refusals.
- Real API batch accounting includes erased/missing IDs and surviving candidates;
  normal same-cut updates remain compatible.
- Migrated scratch HTTP materialize/erase/retry/restart journey, focused backend
  checks, PostgreSQL migration up/down/up, full pytest and recorded self-review.

Design: reuse candidate foreign-key cascade and ORM stale-row detection. No
schema, UI, scoring, timestamp or consent policy change. Computation-time consent
audit races are D3; ingest/fingerprints are D2. No browser/provider evidence
required for this persistence-only child.

Implementation: FeatureStore rolls back IntegrityError/StaleDataError and checks
the candidate afresh. Only an absent parent returns None. The route increments
skipped on that result and continues the batch. The existing FK remains the
retention boundary; successful write-before-delete can return its saved ID while
the subsequent cascade removes the row.

Self-review (2026-09-21): HEAD `9f2f6cd` plus feature store/route additions, new
concurrency tests and the extended feature HTTP smoke. Preserved the earlier UTC
binding changes in the store. Specification: insert/update/retry and batch
accounting map to behavioral regressions; all production upsert callers traced
with rg (the materialization route is the only caller). Correctness: rollback
precedes the parent read, deleted-vector/live-parent errors propagate, other
candidates survive, and no error payload is logged on handled erasure. Existing
admin-only access and same-cut timestamp tests remain in focused coverage.
No blocking finding remains within D1. Consent audit persistence happens before
upsert and remains explicitly D3; this is not whole-materialization race closure.
No independent review, browser execution or live-provider validation claimed.

Final evidence:
- Before fix: 8 failed, 2 passed, 6 PostgreSQL skips, 1 warning, 19.10s.
  Insert/update database errors, stale retry errors and four API HTTP 500s.
- Focused SQLite: 35 passed, 10 PostgreSQL skips, 1 warning, 25.23s.
  Includes unrelated NOT NULL/stale-row errors and recovery with a live parent.
- Focused PostgreSQL: 45 passed, zero skips, 1 warning, 92.08s. PostgreSQL 18.6,
  Asia/Calcutta server timezone; competing connections for insert/update in both
  orderings, stale retries and unrelated database failures. Timestamp fixture
  also explicitly covers UTC and Asia/Calcutta sessions.
- Migrated scratch HTTP/restart: 15/15 each on SQLite and PostgreSQL. Same/new-cut
  retries skip the erased candidate, update the survivor and keep search/board
  results correct after restart. PostgreSQL migration up/down/up and cluster
  shutdown passed. No schema/data migration introduced by this child.
- Full SQLite pytest: 2223 passed, 23 PostgreSQL skips, 42 warnings, 404.17s.
  No full PostgreSQL rerun claimed; the new database paths passed focused PG.
- Compilation, git diff whitespace and task/PI documentation link checks passed.

Commands (project environment throughout):
```
.resume/Scripts/python.exe -m pytest tests/test_feature_erasure_concurrency.py -q --tb=short
.resume/Scripts/python.exe -m pytest tests/test_feature_erasure_concurrency.py tests/test_feature_timestamps.py tests/test_features_materialize.py tests/test_features_materialize_api.py tests/test_talent_search_api.py tests/test_job_store_match.py tests/test_services_features.py -q --tb=short
.resume/Scripts/python.exe scripts/smoke_r1_s1_t3a_v1.py
.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d1_postgres.py
.resume/Scripts/python.exe -m pytest -q --tb=short
.resume/Scripts/python.exe -m py_compile src/app/features/store.py src/app/api/routes.py tests/test_feature_erasure_concurrency.py scripts/smoke_r1_s1_t3a_v1.py
git diff --check
```

Logs: `.pytest_cache/r1-s1-t3b-d1-{red,focused,smoke,suite}.txt` and
`r1-s1-t3b-d1-pg-{runner,focused,migrations,smoke,stop}.txt` there. The local PG
runner derives from the interview runner, uses the existing V1 runtime metadata,
creates/stops a fresh disposable cluster and invokes the focused command above
plus `scripts/smoke_r1_s1_t3a_v1.py --postgres`. No full PostgreSQL suite claimed.
HTTP smoke is a real sequential materialize/erase/retry/restart journey with
providers disabled; controlled races are pytest store/TestClient evidence.

Compilation passed. Attempted `node scripts/check_ui_bindings.js` could not run
because Node is unavailable on PATH; no binding/browser result is claimed.
No frontend asset or UI contract changed. Existing skipped-count response field
now also accounts for erasure at vector persistence.

Working `data/veritas.db` SHA256 remained
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Pre-existing uncommitted work was preserved. Next: **R1-S1-T3b-D2** only in a new
chat; D/D3/T3b/T3/F05 and R1-S1-Q remain open.

## <a id="r1-s1-t3b-d2"></a>R1-S1-T3b-D2 - Ingest and fingerprint erasure races

Status: done, 2026-09-22. Parent: [D](#r1-s1-t3b-d).

Trace: ingest resolves an existing candidate, updates its identity timestamp,
flushes, writes/reuses a resume and commits an extraction in one transaction.
The identity UPDATE holds the write lock until commit. Erasure before that
UPDATE raises StaleDataError; erasure after it waits, then cascades all rows.
Fingerprint persistence runs in a separate transaction after ingest returns.

Bounded children, one per chat:
- [D2a](#r1-s1-t3b-d2a): resolved-candidate ingest through commit; done.
  Focused SQLite 64 passed; PostgreSQL runner 71 passed (2 SQLite-only skips);
  full SQLite 2234 passed, 32 skipped; HTTP/restart 12/12 per backend.
  Migration up/down/up and self-review recorded in the child evidence.
- [D2b](#r1-s1-t3b-d2b): post-ingest fingerprint persistence; done.
  Missing candidates/resumes safely refuse; concurrent duplicates are idempotent.
  Focused SQLite 79 passed; PG runner 97 passed, four SQLite-only skips; full
  SQLite 2250 passed, 45 skipped; HTTP/restart 18/18 per backend. Migration
  up/down/up and self-review recorded in the child evidence.

No tombstone or new permanent ban on uploading an erased identity is introduced.
A new upload resolving after erasure cannot identify the erased row; that is
distinct from replaying work that already resolved that row. D2 is complete;
D stays open. Next: D3 screening completion, audits and cross-store ordering.
Erasure after a successful fingerprint commit can still race later response/
screening work; this is not a whole-ingest erasure guarantee.

## <a id="r1-s1-t3b-d2a"></a>R1-S1-T3b-D2a - Resolved-candidate ingest racing erasure

Status: done.
Parent: [D2](#r1-s1-t3b-d2). Date: 2026-09-22.

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

## <a id="r1-s1-t3b-d2b"></a>R1-S1-T3b-D2b - Post-ingest fingerprint persistence

Status: done. Parent: [D2](#r1-s1-t3b-d2). Date: 2026-09-22.

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

## <a id="r1-s1-t3b-d3"></a>R1-S1-T3b-D3 - Screening, audits and cross-store ordering

Status: done (2026-10-06; bounded acceptance and evidence complete). Parent: [D](#r1-s1-t3b-d).

| Child | Scope | Status |
|---|---|---|
| [D3a](#r1-s1-t3b-d3a) | Screening completion refusal, retained-input cleanup and truthful counts. | Done |
| [D3b](#r1-s1-t3b-d3b) | Earlier retained input, retry references and interrupted cleanup. | Done |
| [D3c](#r1-s1-t3b-d3c) | Materialization/training/matching audit and disclosure boundaries. | Done |
| [D3d](#r1-s1-t3b-d3d) | Ingest responses and cross-store ordering/combined validation. | Done |

Acceptance: review each retained-data and disclosure boundary through its actual
caller. Preserve consent/scoring policy and anonymous completed-screening counts.
Older unresolved input pauses on erasure under D3b's authorized policy while
retaining its original TTL; this is not immediate erasure of unidentified text.

All children and required evidence are complete. [D3d2d3](#r1-s1-t3b-d3d2d3)
owns combined acceptance mapping; [D4](#r1-s1-t3b-d3d2d4) settles the named
working-database curation row-retention gap with an empty actual inventory.
Per-store completion does not prove atomic whole-ingest or HTTP delivery behavior.
The historical-input/TTL policy above remains unchanged. Counts/commands live
with each leaf; next task: [PROGRESS.md](../PROGRESS.md).

## <a id="r1-s1-t3b-d3a"></a>R1-S1-T3b-D3a - Screening completion erasure refusal

Status: done (2026-09-22). Parent: [D3](#r1-s1-t3b-d3).

### <a id="r1-s1-t3b-d3a--acceptance-and-scope"></a>Acceptance and scope

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

### <a id="r1-s1-t3b-d3a--validation-plan"></a>Validation plan

Reproduce failures with controlled separate connections on SQLite/PostgreSQL;
test both orderings, lease replacement, retries, unrelated errors and HTTP
process/queue/retry with another tenant. Observe PostgreSQL delete blocking.
Run focused screening regressions, full project pytest, migrated scratch HTTP
and restart inspection on both backends, migration up/down/up, diff self-review
and static checks. Record results and limits below before completion.

### <a id="r1-s1-t3b-d3a--implementation-and-review"></a>Implementation and review

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

### <a id="r1-s1-t3b-d3a--evidence-2026-09-22"></a>Evidence (2026-09-22)

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

### <a id="r1-s1-t3b-d3a--remaining-boundaries"></a>Remaining boundaries

D3b owns earlier unlinked input, ingest exceptions and interrupted cleanup: a
crash between failed completion rollback and cleanup can still retain input.
A superseded worker must not scrub the new claimant's row. No whole-ingest,
permanent re-upload ban or atomic cross-store erasure guarantee is claimed.
D3c audits and D3d ordering remain pending; D3/D/T3b/T3/F05/R1-S1-Q stay open.
Next: **R1-S1-T3b-D3b**; create its bounded acceptance record before implementing.
Working data/veritas.db SHA256 stayed
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

## <a id="r1-s1-t3b-d3b"></a>R1-S1-T3b-D3b - Screening input before completion

Status: done (2026-09-23; all children complete). Parent: [D3](#r1-s1-t3b-d3).

Initial trace: registration stores raw_text/hash without a candidate ID. Claim leaves
them intact; extraction and CandidateStore.ingest resolve/store the identity;
fingerprinting and evaluation run before complete first writes the item links.
IngestRefused reaches fail; explicit erasure failures now scrub text (D3b1),
while earlier interrupted/unlinked input remains. Completed anonymous
counts/scalars and existing consent policy must remain unchanged.

Bounded children, one per session:

1. [D3b1](#r1-s1-t3b-d3b1): atomically scrub recorded erasure refusals in fail;
   preserve leases, ordinary failure retries, tenant isolation and API accounting.
   Done 2026-09-22: focused SQLite 102 passed, PG runner 142 passed; HTTP/restart
   19/19 per backend; full SQLite 2279 passed, 70 skipped. Self-review recorded.
2. [D3b2](#r1-s1-t3b-d3b2): durable association of pre-completion input with resolved identity,
   erasure during ordinary failure/retry and interrupted cleanup (including
   crashes before fail and D3a rollback-to-cleanup). Create acceptance record
   split into D3b2a successful-ingest retry references (done 2026-09-23) and
   D3b2b earlier unresolved input/report-only cleanup interruptions.

D3b1 and every D3b2 child are done. D3b2b2 closes unresolved/historical input
with the authorized cross-tenant pause, original TTL and fresh-upload behavior.
Final full SQLite 2332 passed; PG focused 330 passed plus 25 final-file checks;
HTTP/worker exit/restart 17/17 per backend, SQLite browser journey 21/21.
Detailed evidence and self-review are in the child records.
Exact next task: **R1-S1-T3b-D3c**. D3 and its ancestors remain open.
No permanent re-upload ban, registration-time identity inference, or whole-ingest
erasure guarantee is claimed.

## <a id="r1-s1-t3b-d3b1"></a>R1-S1-T3b-D3b1 - Scrub recorded screening erasure refusals

Status: done (2026-09-22). Parent: [D3b](#r1-s1-t3b-d3b).

### <a id="r1-s1-t3b-d3b1--acceptance-and-scope"></a>Acceptance and scope

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

### <a id="r1-s1-t3b-d3b1--validation-plan"></a>Validation plan

Behavioral red/green store and HTTP regressions on isolated SQLite/PostgreSQL,
controlled competing connections for lease replacement/deletion, transaction
rollback checks, focused screening/ingest/fingerprint tests, full pytest,
migrated scratch HTTP/restart with disabled external providers, PostgreSQL
migration up/down/up, and recorded diff self-review. No browser requirement:
frontend assets and wire schema are unchanged.

### <a id="r1-s1-t3b-d3b1--implementation-and-review"></a>Implementation and review

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

### <a id="r1-s1-t3b-d3b1--evidence-2026-09-22"></a>Evidence (2026-09-22)

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

## <a id="r1-s1-t3b-d3b2"></a>R1-S1-T3b-D3b2 - Durable screening input and interrupted cleanup

Status: done (2026-09-23; all children complete). Parent: [D3b](#r1-s1-t3b-d3b).

Two boundaries require separate evidence and one child per session:

1. [D3b2a](#r1-s1-t3b-d3b2a): successful ingest atomically transfers batch
   retry input to an erasure-bound resume reference. Ordinary failures and
   interrupted processing may retry that exact surviving resume, without
   resolving it as a new identity. Candidate/resume erasure must remove the
   retry reference even when no completion/failure cleanup runs.
   Done 2026-09-23: final durable SQLite 23 passed; PG runner 253 passed;
   HTTP/worker termination/restart 18/18 per backend; full SQLite 2303 passed,
   93 skipped. Migration, retention and self-review evidence recorded in D3b2a.
2. [D3b2b](#r1-s1-t3b-d3b2b): earlier identity-resolution/failed-first-ingest retention and
   interruptions before the first durable association. Also assess report-only
   erasure interrupted before D3a cleanup and legacy unlinked records. Create
   its acceptance record before implementing; do not infer ownership from raw
   text or silently delete existing ambiguous input. Split 2026-09-23 into
   D3b2b1 report-only interrupted cleanup and D3b2b2 unresolved/legacy input.

D3b2a binds successful-ingest input to an exact resume. D3b2b1 binds reports
atomically; D3b2b2 now guards earlier unresolved/historical input with the
user-authorized cross-tenant generation barrier. All children are done; evidence
is in their records. D3b2b2 full SQLite 2332 passed, PG focused 330 passed plus
25 final-file checks; HTTP/worker restart 17/17 per backend, SQLite browser 21/21.

Consent, anonymous completed counts/scalars, tenant isolation and the original
batch-input retention window remain intact. No permanent fresh-upload ban or
whole-ingest erasure guarantee. Exact next task: **R1-S1-T3b-D3c**.

## <a id="r1-s1-t3b-d3b2a"></a>R1-S1-T3b-D3b2a - Bind retry input in the successful ingest transaction

Status: done (2026-09-23). Parent: [D3b2](#r1-s1-t3b-d3b2).

### <a id="r1-s1-t3b-d3b2a--acceptance-and-design"></a>Acceptance and design

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

### <a id="r1-s1-t3b-d3b2a--validation-plan"></a>Validation plan

Red/green actual process failures and interrupted evaluation; candidate/resume
erasure, ordinary retry, two tenants, expired retention, lost leases, rollback
and pinned retry races. Controlled SQLite/PostgreSQL connections, PostgreSQL
lock inspection, populated migration up/down/up, ORM drift, full pytest,
migrated scratch HTTP/restart/worker termination, compilation and diff
self-review. No browser requirement because public UI contracts stay unchanged.

### <a id="r1-s1-t3b-d3b2a--implementation-and-self-review"></a>Implementation and self-review

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

### <a id="r1-s1-t3b-d3b2a--evidence-2026-09-23-work-started-2026-09-22"></a>Evidence (2026-09-23; work started 2026-09-22)

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

## <a id="r1-s1-t3b-d3b2b"></a>R1-S1-T3b-D3b2b - Earlier input and interrupted report cleanup

Status: done (2026-09-23; both children complete). Parent: [D3b2](#r1-s1-t3b-d3b2).

Tracing shows two independent boundaries; complete one child per session:

1. [D3b2b1](#r1-s1-t3b-d3b2b1): atomically associate saved reports with
   private retry input, so report-only erasure works after worker interruption
   and between failed completion rollback and cleanup. Implement first because
   its ownership is explicit and requires no legacy ownership inference.
   Done 2026-09-23: report save atomically binds retry to report erasure.
   Full SQLite 2317 passed; PostgreSQL focused 306 passed; migrated HTTP/worker
   exit/restart 19/19 per backend, migrations and self-review recorded.
2. [D3b2b2](#r1-s1-t3b-d3b2b2): first extraction/identity resolution, failed-first-ingest
   interruptions before durable association, and historical unlinked input.
   Create its acceptance record before implementation. Current registration
   stores raw text without a known subject; ingest rollback leaves it intact.
   No safe ownership is established by similar text or by a missing identity.
   Preserve the existing TTL and do not silently delete ambiguous legacy input.
   Migration 0025 also leaves historical private references without inferred
   report links; document this boundary alongside historical unlinked raw input.
   Done 2026-09-23: user-authorized generation barrier pauses older unresolved
   input across tenants; migration 0026 quarantines historical input without
   deleting text or changing TTL. Full SQLite 2332 passed; PG focused 330 passed
   plus final-file supplement 25 passed; HTTP/worker exit/restart 17/17 each
   backend, SQLite browser journey 21/21. Self-review/migration evidence recorded.

No whole-ingest guarantee or permanent re-upload ban. Both children are done.
Exact next task: **R1-S1-T3b-D3c**; D3 and its ancestors remain open.

## <a id="r1-s1-t3b-d3b2b1"></a>R1-S1-T3b-D3b2b1 - Report erasure after interrupted screening

Status: done (2026-09-23). Parent: [D3b2b](#r1-s1-t3b-d3b2b).

### <a id="r1-s1-t3b-d3b2b1--acceptance-and-design"></a>Acceptance and design

Trigger: a batch report saves, then the worker exits before completion (or
between failed completion rollback and cleanup). Report-only erasure currently
leaves the private resume reference retryable and recovery creates a new report.

- Saving a batch report must atomically bind its private retry reference to
  report erasure. Deletion removes retry capability even with no worker cleanup;
  the surviving candidate/resume and unrelated tenants remain intact.
- Lost leases, deleted batches, erased/swept retry input or a different tenant
  cannot save an abandoned batch report. Binding and report save roll back
  together. Stale input cannot restore an erased reference.
- Ordinary failures/recovery retain exact-resume retry while the report/input
  survives. Preserve completed anonymous counts/scalars, public fields and TTL.
- Migration preserves existing input without guessing historical report links;
  populated upgrade/downgrade/upgrade preserves surviving references and cannot
  restore erased ones. No migration or cleanup on working storage.

Use a nullable CASCADE report FK on the existing private input table and a
before-commit callback in report save. No new public linkage, inferred identity,
consent change or UI change. Earlier unresolved and legacy input is D3b2b2.

### <a id="r1-s1-t3b-d3b2b1--validation-plan"></a>Validation plan

Red/green process interruption and rollback-to-cleanup regression; two tenants,
lost lease, erased/swept reference, ordinary retry, completion-first, transaction
rollback. Controlled SQLite/PostgreSQL connections, PG deletion lock inspection,
populated migration round trip and schema drift. Real migrated HTTP/worker exit/
restart on both backends, full pytest, compilation, bindings and diff self-review.

### <a id="r1-s1-t3b-d3b2b1--implementation-and-self-review"></a>Implementation and self-review

Migration 0025 adds a nullable, indexed report CASCADE FK to the private input
table. Report save flushes and invokes the optional callback before committing;
screening binds only a surviving tenant-owned input under the current lease,
with the report and resume naming the same candidate. A missing association
rolls back the new report. The item lock precedes the input update, matching
completion. Existing non-batch report saves retain their call contract.

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus this session's
report store diff and screening diffs against saved starting files; also new
migration, regressions, updated 0024 migration test sequence and scratch smoke.
Specification review covered interruption on both sides of rollback, ordinary
retry, tenant ownership, migration preservation and unchanged completion/TTL.
Correctness review traced callback rollback, FK deletion ordering, replaced
leases, batch deletion, erasure/sweep during evaluation, unrelated constraints
and historical unlinked records. No acceptance-blocking findings remain in this
scope. This is self-review, not independent review or live-provider validation.

Validation setup corrections: the older 0024 round-trip test must now also
downgrade/upgrade 0025; its initial failure was a stale-schema test fixture.
The first scratch smoke stopped after eight checks because its parent-process
eraser lacked organization/authorship ORM metadata imports. Added the imports;
no application change was needed for either setup issue.

### <a id="r1-s1-t3b-d3b2b1--commands-and-evidence"></a>Commands and evidence

Commands run from the project root (all database validation uses scratch storage):

```powershell
.resume/Scripts/python.exe -m pytest -q tests/test_screening_report_input.py --tb=short
.resume/Scripts/python.exe -m pytest -q tests/test_screening_report_input.py tests/test_screening_ingest.py tests/test_screening_durable_input.py tests/test_migrations.py --tb=short
.resume/Scripts/python.exe -m pytest -q tests/test_screening_report_input.py tests/test_screening_durable_input.py --tb=short
.resume/Scripts/python.exe -m pytest -q tests/test_screening_report_input.py tests/test_screening_durable_input.py tests/test_report_store.py tests/test_report_erasure_concurrency.py tests/test_screening_erasure_concurrency.py tests/test_screening_ingest.py tests/test_migrations.py --tb=short
.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3b2b1.py
.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3b2b1_postgres.py
.resume/Scripts/python.exe -m pytest -q --tb=short
.resume/Scripts/python.exe -m py_compile src/app/reports/store.py src/app/screening/models.py src/app/screening/store.py src/app/screening/service.py src/app/screening/ingest.py alembic/versions/0025_screening_input_report.py tests/test_screening_report_input.py tests/test_screening_durable_input.py scripts/smoke_r1_s1_t3b_d3b2b1.py
git diff --check
node scripts/check_ui_bindings.js
```

- Red: **2 failed**, 1 warning, 5.20s; both interrupted report cleanup cases
  left the private input reference behind after report-only erasure.
- Initial focused: 1 stale-schema migration fixture failure, 44 passed,
  23 skipped, 16 warnings, 32.03s. Corrected sequence as described above.
- Expanded SQLite focused: **95 passed, 56 skipped**, 19 warnings, 86.57s.
  The final extra unrelated-integrity regression is included in the full suite.
- PostgreSQL runner focused: **306 passed, 12 skipped**, 23 warnings, 443.78s.
  All PostgreSQL variants passed; skips are SQLite variants of PG lock inspection.
  Controlled erase-first and binding-first orderings passed, including observed
  report deletion blocked on the binding transaction. Populated 0024/0025
  downgrade/upgrade tests and the migration chain up/down/up passed.
  Disposable PostgreSQL cluster stopped cleanly: pg_ctl exit 0, 31.81s.
- Migrated HTTP/worker exits/restarts: **19/19 on each backend**. Real worker exit 71
  before completion and exit 72 after rollback, then erasure/recovery/restart;
  report deletion through the production store (there is no report-delete HTTP
  route), other-tenant HTTP denial, surviving resumes and no recreated report.
- Full SQLite pytest: **2317 passed, 105 skipped**, 44 warnings, 474.80s.
  Skips: 93 unconfigured PostgreSQL variants and 12 SQLite variants of PG lock
  inspection. No full PostgreSQL suite claimed.
- Compilation, tracked diff whitespace and new-file whitespace passed. Attempted
  Node binding check unavailable (Node not installed); no frontend/public-field
  changes, so no browser execution is required or claimed.

Local logs: `.pytest_cache/r1-s1-t3b-d3b2b1-{red,initial,focused-initial,focused,full,smoke-sqlite}.txt`
and `r1-s1-t3b-d3b2b1-pg-*.txt`. Local portable-PG runner is an ignored artifact;
no deployed migration, full PostgreSQL suite or live-provider claim.

Next: **R1-S1-T3b-D3b2b2**, unresolved/failed-first-ingest and historical input.
D3b2b/D3b2/D3b/D3/D/T3b/T3/F05/R1-S1-Q remain open. Working data/veritas.db
SHA256 is unchanged: `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

## <a id="r1-s1-t3b-d3b2b2"></a>R1-S1-T3b-D3b2b2 - Unresolved and historical screening input

Status: done (2026-09-23); conservative policy explicitly authorized.
Parent: [D3b2b](#r1-s1-t3b-d3b2b).

### <a id="r1-s1-t3b-d3b2b2--acceptance-boundary"></a>Acceptance boundary

Trace and reproduce erasure before first identity resolution, ordinary first
ingest failure and worker interruption before its first durable association.
Do not infer identity from text, silently delete ambiguous historical input,
change consent or lose completed anonymous counts/scalars. Preserve the batch
input retention window. D3b2a/D3b2b1's durable resume/report bindings remain done.

User selected the recommended conservative policy: "go ahead as recommeneded,
i trust your expertise" after identifying the beta records as dummy data.
Implement option 1 below; no further policy approval is needed. Preserve working
storage rather than treating dummy data as an instruction to delete it.

### <a id="r1-s1-t3b-d3b2b2--selected-implementation-acceptance"></a>Selected implementation acceptance

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

### <a id="r1-s1-t3b-d3b2b2--implementation-and-limits"></a>Implementation and limits

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

### <a id="r1-s1-t3b-d3b2b2--validation-2026-09-23"></a>Validation (2026-09-23)

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

### <a id="r1-s1-t3b-d3b2b2--recorded-diff-self-review"></a>Recorded diff self-review

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

## <a id="r1-s1-t3b-d3c"></a>R1-S1-T3b-D3c - Candidate-linked audit races

Status: done (2026-09-24; split 2026-09-23). Parent: [D3](#r1-s1-t3b-d3).

Three callers have different refusal and response contracts. One child per chat:

1. [D3c1](#r1-s1-t3b-d3c1): feature.materialize consent-audit erasure race;
   safely skip the erased subject and continue materializing surviving subjects.
   Done 2026-09-23: full SQLite 2353 passed, 123 skipped; PG focused 104 passed,
   1 skipped; HTTP/restart 19/19 per backend, observed locking and self-review
   recorded in the child.
2. [D3c2](#r1-s1-t3b-d3c2): training.label audit/export erasure races. Done
   2026-09-23: audit erasure cancels the subject; final existence reads exclude
   stale examples with or without auditing, preserving stored consent policy.
   Full SQLite 2371 passed, 142 skipped; PG focused 151 passed, 2 skipped;
   HTTP/subprocess/restart 3/3 outer and 13/13 worker checks per backend.
   Snapshot/file-delivery limits, migration chain and self-review recorded.
3. [D3c3](#r1-s1-t3b-d3c3): match.surface disclosure audit/response race.
   Done 2026-09-24: rollback/retry omits vanished subjects, preserves survivor
   scores and audits, and final existence reads filter matches/counts on both
   match and board routes. Full SQLite 2398 passed, 158 skipped; PG focused
   167 passed, 3 skipped; migrated HTTP/restart 21/21 per backend. Observed FK
   blocking, migration chain, snapshot limits and self-review recorded.

Existing consent snapshots/current-consent policy changes remain separately
scheduled. No whole-ingest or response-time erasure guarantee is implied.
All three bounded caller contracts are complete. Exact next task:
**R1-S1-T3b-D3d**. D3/D/T3b/T3/F05/R1-S1-Q remain open.

## <a id="r1-s1-t3b-d3c1"></a>R1-S1-T3b-D3c1 - Feature materialization consent audit after erasure

Status: done (2026-09-23). Parent: [D3c](#r1-s1-t3b-d3c).

### <a id="r1-s1-t3b-d3c1--acceptance-and-scope"></a>Acceptance and scope

Trigger: candidate erasure after feature context loading or after the consent
check but before feature.materialize audit insertion. Current code raises a raw
LookupError/IntegrityError, aborting the batch. The erased subject must produce
no audit or vector; materialize_candidate returns None and the existing admin
POST /features/materialize counts it as skipped while continuing other subjects.

- Cover absent subject, erased-before-audit-flush and audit-commit-before-erasure
  on isolated SQLite/PostgreSQL with controlled competing connections. Verify
  foreign-key ordering and cascade cleanup, retry and unaffected second subject.
- Preserve direct materialization_consent's LookupError compatibility, using a
  specific missing-subject refusal the orchestrator can distinguish from other
  errors. Roll back before checking disappearance after an integrity error.
- Unrelated database/lookup failures must propagate; do not falsely classify them
  as withheld consent or successful materialization. No SQL/private payload logs.
- Preserve existing allowed/withheld decisions, masking, timestamps, API fields,
  admin authorization and unknown-candidate skip semantics. Test both decisions
  and operator/portal erasure, plus migrated HTTP/restart persistence.
- No schema migration, frontend asset/contract change, scoring/consent-policy
  change, training export or matching fix in this child. Required: red/green,
  focused/full pytest, PG ordering and migration up/down/up, HTTP subprocess
  journey, diff self-review, documentation. Browser not required for unchanged
  visible contract; API response behavior must be exercised.

Use existing candidate CASCADE foreign keys and narrow error translation, not
new locking/schema machinery or general audit abstractions. Audit-first may
return the decision, but subsequent erasure removes its audit and the existing
feature-store guard refuses later persistence (D1). Cross-store review is D3d.

### <a id="r1-s1-t3b-d3c1--evidence"></a>Evidence

- Red: `.resume/Scripts/python.exe -m pytest -q tests/test_materialization_audit_erasure.py --tb=short`:
  **10 failed, 8 passed, 7 skipped**, 1 warning, 7.92s. Intended failures:
  raw FK errors at audit flush and HTTP 500 before/at audit for allowed/withheld
  subjects. Existing audit-first paths passed.
- Focused command: `.resume/Scripts/python.exe -m pytest -q tests/test_materialization_audit_erasure.py tests/test_ledger_store_materialize_consent.py tests/test_features_materialize.py tests/test_features_materialize_api.py tests/test_feature_erasure_concurrency.py tests/test_ledger_store.py --tb=short`:
  **59 passed, 13 skipped**, 1 warning, 9.27s. Earlier command had a wrong
  test filename and collected no tests; corrected, not counted as a defect.
- `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3c1.py`: **19/19** on
  migrated scratch SQLite. Real app/HTTP, six allowed/withheld boundary cases,
  unchanged admin-only access, retry and restart audit/vector inspection.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3c1_postgres.py`:
  PostgreSQL 18.6 focused tests **104 passed, 1 skipped**, 16 warnings, 108.36s.
  Twelve files cover the new races, ledger/materialization/vector stores, export,
  training callers, jobs API and migrations. Skip is the SQLite variant of PG
  lock inspection. Observed pg_blocking_pids proves erasure waits for the audit
  FK lock; delete-first and commit-first orderings passed. Full migration chain
  up/down/up passed on scratch storage; no new migration in this child.
- PostgreSQL migrated HTTP/restart **19/19** via the same smoke script with
  `--postgres` (runner supplies only a disposable database). Scratch cluster
  stopped cleanly: pg_ctl exit 0, 11.57s. Both backend journeys use synthetic
  separate-session erasure at controlled hooks, not worker-crash simulation.
- `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2353 passed,
  123 skipped**, 44 warnings, 277.01s, on the final reviewed source/test state.
  Skips are unconfigured PG variants and SQLite variants of PG lock inspection.
  No full PostgreSQL suite or live-provider validation claimed.
- Compilation passed:
  `.resume/Scripts/python.exe -m py_compile src/app/ledger/store.py src/app/features/materialize.py tests/test_materialization_audit_erasure.py scripts/smoke_r1_s1_t3b_d3c1.py`.
  `git diff --check`, new-file whitespace and local documentation links passed.
  `node scripts/check_ui_bindings.js` unavailable (Node not installed). No frontend
  assets or visible API contract changed; browser execution not claimed.


### <a id="r1-s1-t3b-d3c1--diff-self-review-2026-09-23"></a>Diff self-review (2026-09-23)

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus this session's
ledger/store.py, features/materialize.py, new regression file and HTTP smoke.
Start copies are in `.pytest_cache/d3c1-start`; pre-existing changes preserved.
Specification review: exact missing-subject LookupError subtype, rollback and
fresh lookup, narrow orchestrator cancellation, survivor accounting and unchanged
consent masking each map to focused regressions. Correctness review checked
CASCADE ordering, both commit orderings, retry, unrelated NOT NULL/LookupError
propagation, no new payload logging, and the existing D1 vector guard after an
audit-first erasure. No new schema/locks/general audit abstraction is needed.
No acceptance-blocking finding remains; required checks completed on this state.
This is self-review, not independent review. No live-provider validation claimed.


Logs: `.pytest_cache/r1-s1-t3b-d3c1-*.txt`. The local PG runner uses the ignored
portable runtime record `.pytest_cache/r1-s1-t3a-v1-pg-runtime.json`; this is local
evidence, not a portable setup guarantee. No .env edits or service registration.
Working data/veritas.db remains SHA256
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Existing uncommitted work preserved. No working-data migration or deployment.
Exact next task: **R1-S1-T3b-D3c2** (training-label audit/export erasure).
D3c/D3/D/T3b/T3/F05/R1-S1-Q remain open.

## <a id="r1-s1-t3b-d3c2"></a>R1-S1-T3b-D3c2 - Training-label audit/export erasure

Status: done (2026-09-23). Parent: [D3c](#r1-s1-t3b-d3c).

### <a id="r1-s1-t3b-d3c2--acceptance-and-scope"></a>Acceptance and scope

Trigger: cached vectors/outcomes survive in a training builder while their
candidate is erased, before audit insertion/commit or before builder handoff.
Today the audit raises an IntegrityError, or audit=False emits stale data.
The builder must omit erased subjects entirely (including withheld vectors),
continue surviving subjects, and export only the resulting examples.

- Audit erasure raises a specific LookupError subtype after rollback and a fresh
  missing-subject check; unrelated integrity/lookup failures propagate. Existing
  successful audit returns None and keeps its fields and allowed/withheld meaning.
- Cover absent candidates, cached labels, before-flush and after-commit erasure,
  erasure of an earlier example while building a later one, and audit=False.
  Final existence checks apply with or without auditing. Retry must stay omitted.
- Preserve snapshot consent policy, withheld short-circuit (no outcome reads),
  strict post-as_of label cutoff, survivor data and CSV/parquet columns/types.
- Exercise SQLite and PostgreSQL competing connections and observed FK locking;
  full migration up/down/up, focused/full pytest, migrated subprocess build/export
  and restart inspection, static checks and recorded diff self-review.
- No schema/UI/API route changes. Training currently has only a library builder
  and smoke caller, not a production HTTP export route. Pure example/CSV/parquet
  serializers have no store; final per-subject existence reads exclude erasures
  visible at each read, not a lock across later checks/file delivery or revocation
  of already returned snapshots/files.
  Current-consent changes remain R1-S2-T2; matching disclosure remains D3c3.

Use the existing CASCADE FK for audit ordering and narrow error translation.
No new lock protocol, schema, serializer dependency or generalized audit wrapper.

### <a id="r1-s1-t3b-d3c2--evidence"></a>Evidence

- Red: `.resume/Scripts/python.exe -m pytest -q tests/test_training_audit_erasure.py --tb=short`:
  **16 failed, 1 passed, 19 skipped**, 15.98s. Raw FK failures at insertion/retry
  and erased candidates retained in returned examples reproduced the defect.
- Focused: `.resume/Scripts/python.exe -m pytest -q tests/test_training_audit_erasure.py tests/test_ledger_store_audit_training_label.py tests/test_features_build_training_set.py tests/test_features_training_export.py tests/test_features_build_label.py tests/test_features_training_schema.py tests/test_materialization_audit_erasure.py tests/test_ledger_store.py --tb=short`:
  **73 passed, 26 skipped**, 1 warning, 30.39s. An earlier command named a
  nonexistent test_features_training_label.py and collected no tests; corrected.
- Migrated journey: `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3c2.py`:
  real HTTP setup, subprocess library build/export, restart HTTP inspection;
  **3/3 outer checks and 13/13 worker checks**, with 12 allowed/withheld boundary
  scenarios and persisted vector/audit inspection. No production training HTTP
  route exists. Repeated after adding explicit worker-log capture, same result.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3c2_postgres.py`:
  PostgreSQL 18.6 focused **151 passed, 2 skipped**, 16 warnings, 177.85s.
  Includes training/materialization/ledger/vector/export callers and migrations;
  skips are SQLite variants of PG lock inspection. Controlled competing sessions
  cover delete-first/audit-first ordering; pg_blocking_pids observes the audit FK
  blocking erasure. Full migration chain up/down/up passed on disposable storage.
  PostgreSQL migrated journey **3/3 outer and 13/13 worker checks**, 28.56s,
  via the same smoke script with `--postgres`; cluster stopped cleanly (exit 0,
  20.34s). Neither backend journey simulates a worker crash. Logs use
  `.pytest_cache/r1-s1-t3b-d3c2-*.txt`; subprocess artifact directory contains
  `worker.log`, synthetic CSVs and `server.log`.
- `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2371 passed,
  142 skipped**, 44 warnings, 384.53s, on the final reviewed code/tests. Skips
  include unconfigured PG variants and SQLite variants of PG lock inspection.
  No full PostgreSQL suite claim.
- `node scripts/check_ui_bindings.js` unavailable (Node not installed). No UI
  or visible API contract changed; no browser execution or live-provider claim.
- PyArrow is absent: actual CSV rows and the parquet missing-dependency contract
  passed. No actual parquet file round trip is claimed; the regression also
  validates rows when run in a PyArrow-enabled environment.
- `.resume/Scripts/python.exe -m py_compile src/app/ledger/store.py src/app/features/training.py tests/test_training_audit_erasure.py scripts/smoke_r1_s1_t3b_d3c2.py`,
  `git diff --check`, changed-file whitespace and local documentation links passed.

### <a id="r1-s1-t3b-d3c2--diff-self-review-2026-09-23"></a>Diff self-review (2026-09-23)

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus this session's
ledger/store.py, features/training.py, new regression file and subprocess smoke.
Start copies in `.pytest_cache/d3c2-start` distinguish pre-existing changes.
Specification review mapped narrow erasure refusal, survivor continuation,
audit=False, withheld no-read behavior, cached labels, later-example erasure and
CSV/parquet contract to behavioral checks. Correctness review traced all builder
and audit callers (library tests and smoke_s44; no production route), fresh
sessions after rollback, CASCADE ordering, unchanged stored consent/cutoff policy,
unrelated NOT NULL/LookupError propagation and read-only serializers.

Review finding (documentation, FEATURES.md S4.4 export): the claim that a file
can never leak overstates stored consent and snapshot erasure semantics. Replaced
with the actual stored-decision policy and explicit per-subject final-read/file
delivery limits. Each final check uses a new session, adding one existence query
per assembled example; it does not hold candidate locks or provide an atomic
whole-export snapshot. No schema or serializer coupling needed for this scope.
Worker stdout is explicitly captured for reproducible Windows evidence.
No acceptance-blocking finding remains. This is self-review, not independent
review. Required regression/database/journey checks completed on this state.

Working data/veritas.db remains SHA256
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Pre-existing uncommitted work preserved; no working-data migration/deletion or
deployment. Exact next task: **R1-S1-T3b-D3c3** (matching
disclosure audit/response race). D3c/D3/D/T3b/T3/F05/R1-S1-Q remain open.

## <a id="r1-s1-t3b-d3c3"></a>R1-S1-T3b-D3c3 - Matching disclosure audit/response erasure

Status: done (2026-09-24). Parent: [D3c](#r1-s1-t3b-d3c).

### <a id="r1-s1-t3b-d3c3--acceptance-and-scope"></a>Acceptance and scope

Trigger: erasure after loading/ranking materialized vectors but before the
match.surface audit commits, or after that commit before response assembly.
Today one vanished subject aborts the whole audit with an IntegrityError, or its
cached match is returned. POST /jobs/{id}/match and GET /jobs/{id}/board
(the requisition board) must omit subjects whose erasure is observed, retain
surviving advisory matches and continue using the existing response schemas.

- Roll back a failed batch audit, check candidate existence in a fresh read, and
  retry only when an attempted subject disappeared. Each retry removes at least
  one subject; unrelated integrity/lookup errors propagate. No partial audit
  batch or duplicate survivor audit from a rolled-back attempt.
- Remove erased subjects from the ranked pool and refill the limit before a
  successful audit. Preserve original survivor scores, contributions, ordering,
  filter membership and stored consent masking. Re-number audit ranks on retry.
- Recheck existence after audit commit; filter response rows and pool/filtered
  counts. Do not backfill unaudited candidates after this final check. An
  after-commit erasure may shorten the result; audit rank records the committed
  ranking. Checks are snapshots, not locks across HTTP delivery or revocation of
  already delivered data. Preserve empty-result API behavior.
- Cover pre-audit/before-flush/after-commit erasure, multiple erasures during
  retries, all erased, filtered/outside-limit erasures, ownership rejection before
  reads/audits, retries and unrelated failures. Both direct and dashboard APIs
  must exercise the real matcher and isolated stores with synthetic providers.
- Required: red/green, full pytest, SQLite/PG controlled competing sessions and
  observed FK blocking, full migration up/down/up, migrated HTTP/restart journey,
  static checks and separate diff self-review. No new schema, consent policy,
  ranking formula, frontend handler or visible UI contract; no browser claim.
  Current-consent changes remain R1-S2; cross-store ordering remains D3d.

Use existing CASCADE foreign keys and a bounded retry of the existing batch
transaction. No per-candidate commits or generalized audit framework.

### <a id="r1-s1-t3b-d3c3--evidence"></a>Evidence

- Red: `.resume/Scripts/python.exe -m pytest -q tests/test_match_disclosure_erasure.py --tb=short`:
  **20 failed, 1 passed, 15 skipped**, 1 warning, 13.33s. Intended audit FK/HTTP
  500 failures, stale returned matches and stale pool counts reproduced.
- Focused: `.resume/Scripts/python.exe -m pytest -q tests/test_match_disclosure_erasure.py tests/test_job_store_match.py tests/test_jobs_api.py tests/test_dashboard_api.py tests/test_dashboard_service.py tests/test_matching_match.py tests/test_matching_engine.py tests/test_job_store.py --tb=short`:
  **63 passed, 16 skipped**, 1 warning, 16.00s. Includes final empty-response
  and unrelated LookupError regressions; exact survivor scores/contributions,
  retry audit counts/ranks, portal/operator erasure, two-actor ownership, and
  controlled competing SQLite connections.
- `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3c3.py`: **21/21** on
  migrated scratch SQLite. Real app/HTTP on both routes, ranked/before-flush/
  after-commit erasure, unauthorized calls, retry, limit-one post-commit refusal
  to backfill, unrelated failure and recovery, restart/vector/audit inspection,
  existing all-erased empty response. Synthetic hooks, not worker-crash evidence.
- `.resume/Scripts/python.exe -m py_compile src/app/matching/store.py tests/test_match_disclosure_erasure.py scripts/smoke_r1_s1_t3b_d3c3.py`
  and `git diff --check`, changed-file whitespace and local documentation links
  passed. `node scripts/check_ui_bindings.js` unavailable
  (Node not installed); no frontend handler/schema changed, no browser claim.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3c3_postgres.py`:
  PostgreSQL 18.6 focused **167 passed, 3 skipped**, 16 warnings, 167.70s.
  Twelve files cover matching/dashboard, materialization/training audit callers,
  feature erasure and migrations. Skips are SQLite variants of PG lock inspection.
  Controlled delete-first/audit-first orderings and observed pg_blocking_pids
  blocking passed. Full migration chain up/down/up passed on disposable storage.
  PostgreSQL migrated HTTP/restart **21/21**, 20.62s; scratch cluster stopped
  cleanly (exit 0, 18.00s). No full PostgreSQL suite
  claim. Logs:
  `.pytest_cache/r1-s1-t3b-d3c3-*.txt`; smoke artifacts include `server.log`.
- `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2398 passed,
  158 skipped**, 44 warnings, 305.25s, on the final reviewed source/tests.
  Skips include unconfigured PG variants and SQLite variants of PG lock inspection.

### <a id="r1-s1-t3b-d3c3--diff-self-review-2026-09-24"></a>Diff self-review (2026-09-24)

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus matching/store.py,
new regression/smoke files and MATCHING.md. Original store copy is in
`.pytest_cache/d3c3-start`; prior uncommitted work is preserved.
Specification review mapped every acceptance item to code and behavioral checks:
atomic rollback/retry, strictly shrinking attempted set, preserved rank snapshot,
top-N refill before audit only, final counts and existing API empty contract.
Correctness review traced both callers (direct match route and dashboard.board),
ownership rejection before pool/audit work, unchanged stored consent policy and
pure ranking engine, fresh sessions after rollback and commit, parameter-bounded
existence queries, survivor audit rank/score consistency and unrelated failures.
No new table, schema version, API field, frontend handler or private-payload log.

Documentation finding (MATCHING.md HTTP section): it still claimed empty pools
return 422. Corrected to the existing 200/reason contract, verified on both routes.
Final existence reads are snapshot boundaries, not an atomic whole-response
erasure guarantee; pools over 500 IDs use multiple bounded reads. Audits describe
the committed ranking, so after-commit removal may leave gaps in audited ranks.
No acceptance-blocking finding remains. This is self-review, not independent
review. Required checks completed on the final source/test state.

Working data/veritas.db remains SHA256
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
No working-data migration/deletion, deployment or live-provider validation.
Exact next task: **R1-S1-T3b-D3d** (cross-store erasure ordering
and post-fingerprint response review). D3c and all its children are done;
D3/D/T3b/T3/F05/R1-S1-Q remain open.

## <a id="r1-s1-t3b-d3d"></a>R1-S1-T3b-D3d - Cross-store ordering and response review

Status: done (2026-10-06; bounded acceptance and evidence complete). Parent: [D3](#r1-s1-t3b-d3).

| Child | Scope | Status |
|---|---|---|
| [D3d1](#r1-s1-t3b-d3d1) | Shared-ingest candidate/resume response checks on uploads/batches, including short input. | Done |
| [D3d2](#r1-s1-t3b-d3d2) | Report/source responses, login-state ordering and combined validation. | Done |

Acceptance: trace both erasure routes and each read/write/commit boundary.
Candidate-linked SQL rows cascade; login cleanup, issuance and redemption are
ordered as recorded in [D3d2c](#r1-s1-t3b-d3d2c). Keep interrupted cleanup
separate from response-snapshot guarantees.

D3d2 owns source-list/portal aggregate windows and the shared curation raw-display-
name policy. No new retention or identity policy is implicit. Do not close this
parent or F05/R1-S1-Q from individual-store evidence. See child records for
validation and [PROGRESS.md](../PROGRESS.md) for the next leaf.

Combined ordering/response acceptance and ancestor mapping are complete in
[D3d2d3](#r1-s1-t3b-d3d2d3). [D4](#r1-s1-t3b-d3d2d4) verifies an empty
actual working-database curation inventory, settling the last development gap.
This bounded parent closes with the response and storage-copy limits preserved;
F05 and R1-S1-Q remain open for the separate sprint review.

## <a id="r1-s1-t3b-d3d1"></a>R1-S1-T3b-D3d1 - Shared ingest response after subject erasure

Status: done (2026-09-24). Parent: [D3d](#r1-s1-t3b-d3d).

### <a id="r1-s1-t3b-d3d1--acceptance-and-scope"></a>Acceptance and scope

Trigger: candidate/resume deletion after ingest/fingerprint commit, during farm
comparison or evaluation, or after report persistence before response assembly.
Currently evaluate=False returns stale success unconditionally; evaluate=True
can return stale IDs with report=null. Refuse observed missing subjects using
existing IngestRefused codes: admin/org uploads return 422, batches record a
failed item and scrub retry input under existing erasure-refusal semantics.

- A fresh store read checks candidate and exact resume ownership together.
  Candidate disappearance takes precedence; missing resume is resume_erased;
  wrong ownership and unrelated store/provider failures remain errors.
- Check before evaluation, before report persistence after evaluation, and
  before returning. Include short text with no fingerprint, both evaluate modes,
  duplicate uploads, erasure after fingerprint/comparison/report commit, both
  upload planes, batch continuation/retry and an unaffected second subject.
- Candidate erasure refuses report persistence through existing FK/store guards;
  when a report save signals SubjectErasedError, refuse the ingest instead of
  reporting stale success. This intentionally supersedes candidate-upload 200
  with report=null for erased subjects; standalone /evaluate is unchanged.
- Preserve ownership/redaction, consent, scoring, fresh-upload behavior and
  existing independent report lifetime when only one resume version is deleted.
  Checks are snapshots, not a lock across evaluation, save or HTTP delivery;
  report-only deletion/cleanup interruption and integrated ordering remain D3d2.
- Required: red/green, focused/full pytest, SQLite/PG controlled connections,
  migration round trips, migrated HTTP/restart journey, diff self-review and
  static/docs checks. No schema/frontend change or new response fields/codes;
  existing 422 refusal handling is reused. No browser/live-provider claim.

Use a small read guard in CandidateStore and the existing shared ingest caller;
do not add locks, tombstones, retry identity resolution or change erasure policy.

### <a id="r1-s1-t3b-d3d1--evidence"></a>Evidence

- Red: `.resume/Scripts/python.exe -m pytest -q tests/test_ingest_response_erasure.py --tb=short`:
  **36 failed, 4 passed, 2 skipped**, 1 warning, 28.82s. Stale HTTP 200 success,
  continued evaluation after observed erasure, and missing late-ingest refusal
  reproduced. Existing batch candidate-erasure completion safeguards passed.
- Broad focused: `.resume/Scripts/python.exe -m pytest -q tests/test_ingest_response_erasure.py tests/test_screening_ingest.py tests/test_candidates_api.py tests/test_screening_api.py tests/test_screening_erasure_concurrency.py tests/test_screening_refusal_retention.py tests/test_fingerprint_erasure_concurrency.py tests/test_report_erasure_concurrency.py tests/test_screening_durable_input.py --tb=short`:
  **150 passed, 70 skipped**, 2 warnings, 69.51s. Final optimization removes one
  redundant evaluate=False read.
- Final focused: `.resume/Scripts/python.exe -m pytest -q tests/test_ingest_response_erasure.py tests/test_screening_ingest.py tests/test_candidates_api.py --tb=short`:
  **66 passed, 3 skipped**, 1 warning, 30.57s.
- Migrated SQLite: `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3d1.py`:
  **36/36**, real HTTP/restart, both upload planes, short and long inputs,
  both evaluation modes, duplicate identities, late candidate/resume refusals,
  batch retry refusal/fresh batch success and persisted subject/report inspection.
  Repeated on final source: **36/36**. Synthetic providers; no worker-crash claim.
- PostgreSQL 18.6 broad runner:
  `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3d1_postgres.py`:
  **225 passed, 9 skipped**, 17 warnings, 358.54s. Includes report/fingerprint
  lock inspection, screening retry/refusal, durable input and migrations. This
  run began before the redundant-read optimization; final-source evidence follows.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3d1_final_postgres.py`:
  final source **80 passed**, zero skips, 1 warning, 142.89s, covering late-ingest,
  shared ingest, candidate and screening APIs. PostgreSQL migrated HTTP/restart
  **36/36** on final source. Both runners passed full migration up/down/up on
  isolated storage and shutdown logs confirm clean stops. The saved full SQLite
  log records **2441 passed, 161 skipped**, 44 warnings, 423.14s; the resumed
  final-state rerun below supersedes it. No full PG suite claim. Logs use
  `.pytest_cache/r1-s1-t3b-d3d1-*.txt`; scratch smoke artifacts include server.log.
- `.resume/Scripts/python.exe -m py_compile src/app/candidates/store.py src/app/screening/ingest.py tests/test_ingest_response_erasure.py tests/test_candidates_api.py scripts/smoke_r1_s1_t3b_d3d1.py`,
  `git diff --check`, changed-file whitespace and local documentation links passed.
  `node scripts/check_ui_bindings.js` unavailable (Node not installed). Existing
  refusal UI handling is reused; no frontend change or browser execution claim.

### <a id="r1-s1-t3b-d3d1--diff-self-review-2026-09-24"></a>Diff self-review (2026-09-24)

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus session changes to
candidates/store.py, screening/ingest.py, the candidates API regression, new
late-erasure tests/HTTP smoke and SCREENING.md. Start copies are saved under
`.pytest_cache/d3d1-start`; pre-existing changes remain preserved.
Specification: one fresh joined candidate/resume read, candidate-first refusal,
ownership rejection, pre-evaluation/pre-save/final checkpoints, safe API codes,
batch scrubbing and fresh-upload permission map to behavioral regressions.
Correctness: traced all three shared-ingest callers, report FK fallback, narrow
exception translation, no identity retry, no SQL/content logging, unchanged
tenant redaction and single-resume report lifetime. A redundant non-evaluating
read was removed; one final read suffices when no evaluation/save follows.
The old candidate-upload 200/report=null test was deliberately updated to 422;
standalone evaluation and successful upload fields remain unchanged.
No acceptance-blocking finding remains. This is self-review, not independent
review. Snapshot races after the final read, report-only erasure, and non-FK
cleanup interruption remain D3d2 scope; this does not close the parent.

### <a id="r1-s1-t3b-d3d1--resumed-validation-2026-09-24"></a>Resumed validation (2026-09-24)

Handoff still pointed to D3d, but this child already had implementation and
unfinished evidence in the workspace. Resumed this child only; preserved those
changes and added four regressions. Review of the saved pre-task copies versus
current source confirmed the bounded diff above. A coverage finding (medium,
`tests/test_ingest_response_erasure.py`) was resolved: erasure between the last
subject check and report save must exercise the real store refusal through both
upload routes. Two additional checks preserve unrelated evaluation/save errors.
Source needed no further change. Same-agent specification/correctness review
traced the joined read, exception mapping, both routes and batch fail/scrub;
no acceptance-blocking finding remains within this child.

- `.resume/Scripts/python.exe .pytest_cache/check_d3d1_resumed_red.py` loads the
  saved pre-task ingest in memory (no source replacement): **2 failed, 47
  deselected**, 1 warning, 5.31s. Both routes returned 200 instead of 422 after
  real report FK refusal. An initial runner import-order error was corrected
  before this reproduction and is not red evidence.
- `.resume/Scripts/python.exe -m pytest -q tests/test_ingest_response_erasure.py tests/test_screening_ingest.py tests/test_candidates_api.py tests/test_screening_api.py --tb=short`:
  **81 passed, 3 skipped**, 1 warning, 20.95s. PostgreSQL-only fixture variants
  skipped without a configured scratch connection.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3d1_final_postgres.py`:
  final tests **84 passed**, zero skips, 1 warning, 136.65s on PostgreSQL 18.6.
  Includes controlled competing connections in the response-erasure file.
  Migration up/down/up, migrated HTTP/restart **36/36**, clean cluster shutdown
  all passed. No full PostgreSQL suite claimed. Runner output:
  `.pytest_cache/r1-s1-t3b-d3d1-resumed-pg-runner.txt`; detailed logs retain the
  `r1-s1-t3b-d3d1-final-pg-*` names.
- `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3d1.py`:
  SQLite migrated HTTP/restart **36/36**; log
  `.pytest_cache/r1-s1-t3b-d3d1-resumed-smoke.txt`. Synthetic providers only.
- Compilation and `git diff --check` passed again. Node binding command was
  attempted again and remains unavailable; no frontend assets/handlers changed,
  no browser execution claimed.
- `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2445 passed, 161
  skipped**, 44 warnings, 351.33s on the final reviewed source/tests. Logs use
  `r1-s1-t3b-d3d1-resumed-{red,focused,full}.txt` under `.pytest_cache`.
- `.resume/Scripts/python.exe .pytest_cache/check_d3d1_docs.py`: local links,
  IDs, parent/next-task status and whitespace passed across **10 documents**.
  Working DB SHA256 remains
  `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

Next: **R1-S1-T3b-D3d2**, a separate session. D3d/D3/D/T3b/T3/F05/R1-S1-Q
remain open. No working-data migration/deletion, deployment or independent
review was performed.

## <a id="r1-s1-t3b-d3d2"></a>R1-S1-T3b-D3d2 - Cross-store cleanup ordering and combined validation

Status: done (2026-10-06; bounded acceptance and evidence complete). Parent: [D3d](#r1-s1-t3b-d3d). Prerequisite: D3d1.

| Child | Scope | Status |
|---|---|---|
| [D3d2a](#r1-s1-t3b-d3d2a) | Report-only erasure after save, before ingest/standalone response. | Done |
| [D3d2b](#r1-s1-t3b-d3d2b) | Profile-source persistence refusal and exact-row response checks. | Done |
| [D3d2c](#r1-s1-t3b-d3d2c) | Login-state cleanup and in-flight issuance/redemption. | Done |
| [D3d2d](#r1-s1-t3b-d3d2d) | Combined ordering and parent-coverage review. | Done |

Combined acceptance:
- Trace portal/admin erasure, report counts, challenge cleanup and candidate
  deletion. Separate shared transactions/cascades from independent commits.
- Cover both erasure doors, unrelated subjects/tenants, retries, failures and
  interruption on isolated stores. Preserve independent report lifetime after
  resume-only deletion, consent/identity policy and fresh-upload permission.
- Include source-list/portal aggregate response windows and shared curation
  raw-display-name retention/input policy. No identity FK does not establish
  de-identification, and final reads do not lock across HTTP delivery.
- Map the combined evidence back to D3d/D3/D/T3b/T3. Code changes require red/green
  regressions, focused/full pytest, relevant migrated HTTP/restart and diff review;
  SQL concurrency/transaction changes also require controlled PostgreSQL and
  applicable migration checks. Browser gates apply to visible UI changes.

All children and required validation are complete. Combined acceptance/mapping:
[D3d2d3](#r1-s1-t3b-d3d2d3); actual empty working-database curation inventory:
[D4](#r1-s1-t3b-d3d2d4). The bounded parent closes without claiming whole-ingest,
HTTP-delivery or backup erasure. Evidence counts live with each child;
exact next task: [PROGRESS.md](../PROGRESS.md), the separate R1-S1-Q review.

## <a id="r1-s1-t3b-d3d2a"></a>R1-S1-T3b-D3d2a - Report-only erasure before evaluation response

Status: done (2026-09-24). Parent: [D3d2](#r1-s1-t3b-d3d2).

Trigger: report deletion commits after save but before response assembly while
candidate/resume survive (or standalone evaluation has no candidate). Before:
admin/org upload and standalone `/evaluate` return the erased report body.
Batch completion already refuses deleted reports, but shared ingest itself does
not. After: a fresh report lookup observes absence and refuses with `report_erased`;
HTTP returns 422 and batches use existing failed-item cleanup/retry semantics.

Acceptance:
- Check report existence after successful save in shared ingest and standalone
  evaluation. Keep candidate/resume refusal precedence in shared ingest; preserve
  evaluate=False, short text, successful report fields, tenant redaction and
  independent candidate/resume lifetime after report deletion.
- Cover all three HTTP doors, unrelated subjects/tenants, outcome cascade,
  duplicates/fresh uploads, batch refusal before completion and no retained retry
  capability. Unrelated store/provider errors must propagate, not become erasure.
- Controlled competing connections cover erase-before-response and response-first
  on SQLite/PostgreSQL. Explicitly document/test the snapshot boundary: deletion
  after the final read can still leave a delivered snapshot, with no durable row.
- Reuse current report-store `get`, refusal handling and schema; no locks,
  tombstones, new response shape, frontend changes or retention/consent policy.
- Required: meaningful red/green, focused/full pytest, migrated real HTTP/restart
  on scratch SQLite/PostgreSQL, migration up/down/up, diff self-review, compilation,
  whitespace and documentation checks. Synthetic providers only. Browser checks
  do not apply to this backend-only reuse of existing error handling.

Other erasure ordering, sources and login state remain D3d2b/c/d. This child
cannot close D3d2/D3d/D3/D/T3b/T3/F05/R1-S1-Q.

### <a id="r1-s1-t3b-d3d2a--diff-self-review-and-evidence"></a>Diff self-review and evidence

Reviewed HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus the bounded changes
against `.pytest_cache/d3d2a-start`: two existence checks in routes.py/ingest.py,
new report-response regressions/HTTP runner and SCREENING.md. Existing changes
were preserved. Specification review maps all doors, batch refusal, report-only
lifetime, unrelated errors and both ordering/snapshot limits to behavioral tests.
Correctness review traced store session closure, candidate/resume precedence,
original org redaction, report/outcome cascade, existing batch scrub/retry codes
and fresh-request permission. No lock or policy change; no new exception catch
that could swallow unrelated failures. No acceptance-blocking finding remains
in this child. This is self-review, not independent review.

- Red: `.resume/Scripts/python.exe -m pytest -q tests/test_report_response_erasure.py --tb=short`:
  **14 failed, 3 passed, 2 skipped**, 1 warning, 7.02s. Stale HTTP 200 on all
  three doors, no ingest refusal and absent final lookup reproduced. An initial
  missing-provenance outcome fixture was corrected before this red run.
- Focused: `.resume/Scripts/python.exe -m pytest -q tests/test_report_response_erasure.py tests/test_ingest_response_erasure.py tests/test_screening_report_input.py tests/test_screening_ingest.py tests/test_candidates_api.py tests/test_api.py --tb=short`:
  **117 passed, 17 skipped**, 2 warnings, 31.43s. PostgreSQL fixture variants
  require a configured disposable connection.
- `.resume/Scripts/python.exe -m py_compile src/app/api/routes.py src/app/screening/ingest.py tests/test_report_response_erasure.py scripts/smoke_r1_s1_t3b_d3d2a.py`
  and `git diff --check` passed. `node scripts/check_ui_bindings.js` was attempted
  but Node remains unavailable. No frontend assets/handlers changed or browser
  execution claimed.
- Initial SQLite HTTP run: 28/29, only the final raw SQL JSON-null inspection
  failed; SQLite returns JSON text while PostgreSQL decodes JSON. Normalized
  that inspection without changing production.
- `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3d2a.py`: final SQLite
  migrated HTTP/restart **29/29**. Both uploads and standalone evaluation, short/
  long inputs, report erasure/fresh recovery, late response snapshots, unrelated
  failure/recovery, batch cleanup/no retry, tenant denial, unauthorized access
  and restart SQL inspection all passed.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3d2a_postgres.py`:
  PostgreSQL 18.6 focused **172 passed, 1 skipped**, 17 warnings, 210.82s.
  Includes the six focused files above plus screening API, report erasure
  concurrency and migrations. The one skip is SQLite's PostgreSQL-only lock
  inspection variant. Full migration up/down/up, PostgreSQL migrated
  HTTP/restart **29/29**, and clean disposable cluster shutdown passed. No full
  PostgreSQL suite claimed.
- `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2463 passed, 163
  skipped**, 44 warnings, 377.56s, on the final reviewed source/tests.
- Documentation check: `.resume/Scripts/python.exe .pytest_cache/check_d3d2a_docs.py`;
  links/IDs/status/whitespace passed across **12 documents**. Working DB
  SHA256 remains `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

Logs: `.pytest_cache/r1-s1-t3b-d3d2a-*.txt`. No live-provider validation.
No working-data migration/deletion, deployment or worker-crash claim. Next:
**R1-S1-T3b-D3d2b**. D3d2 and all higher parents remain open.

## <a id="r1-s1-t3b-d3d2b"></a>R1-S1-T3b-D3d2b - Profile-source erasure refusal and response review

Status: done (2026-09-24). Parent: [D3d2](#r1-s1-t3b-d3d2). Prerequisite: D3d2a.

Entry points: `profile_sources/service.py`, `profile_sources/store.py`, source
routes in `api/routes.py`, related source tests and `_capture_unmapped` callers.
Initial trace only: GitHub fetch and LinkedIn parse follow an early candidate
read. `save_signal` commits a candidate-FK row without erasure translation;
the service returns its in-memory signal after save. Curation capture precedes
save and has a separate lifetime.

Bounded acceptance (before implementation): both source POST callers and their
store writes. Preserve existing LookupError compatibility with narrow domain
subclasses; routes map only those known erasures to safe 404 responses.
- Reproduce candidate erasure during fetch/parse and before/after signal commit;
  define safe refusal for observed absence and preserve unrelated errors.
- Demonstrate no orphan/recreated signal after erasure, unaffected other subjects,
  unchanged source/ownership behavior and permitted fresh ingestion. Separate
  durable-write protection from response snapshots after the final read.
- Trace curation capture's stored fields/ownership and established retention
  policy; do not silently delete shared vocabulary or invent identity links.
- For code changes: red/green tests, full pytest, relevant scratch migrated
  HTTP/restart journeys, SQLite/PostgreSQL controlled connections, migrations
  where applicable, diff self-review and static/documentation checks. Use fake
  providers; do not label them live-provider validation.

- Roll back a failed insert before confirming candidate disappearance; translate
  only FK failures, leaving unrelated constraints/provider/lookup failures intact.
- After save, one fresh joined read checks the candidate and the exact returned
  storage row ID (distinct from the signal JSON ID). Candidate disappearance
  takes precedence; source-only deletion returns a safe source-not-found refusal.
  Wrong ownership is an error. No locking across later response delivery.
- Cover both adapters at initial service read, fetch/parse, flush and after
  commit; fresh ingestion for a surviving/new candidate, unaffected subjects,
  unavailable-source 200 behavior, append-only history and admin-only access.
  SQLite/PG controlled connections cover both write/delete orders and PG locking.
- No schema, consent/scoring or frontend change. List/portal aggregate reads
  retain their existing snapshot behavior; their combined response review is
  D3d2d, not a claim of whole-response atomicity from this write-path fix.

Curation trace: `unmapped_terms` stores normalized key, raw display name, source
types, counts/times and reviewer decisions. It has no candidate identity/FK, and
CURATION.md/models/store explicitly retain shared terms after candidate erasure.
Capture runs before signal persistence and may therefore survive a refused write.
Preserve and regression-test that policy; absence of a candidate ID does not
prove raw skill names contain no personal data. Correct the documentation's
stronger claim; do not delete shared terms or infer ownership here. Any broader
input/retention policy remains an explicit residual for combined review.

Login-state ordering and combined closure remain D3d2c/d. D3d2 and higher parents
stay open until every required child and validation gate is complete.

### <a id="r1-s1-t3b-d3d2b--review-and-evidence"></a>Review and evidence

Self-review: HEAD `9f2f6cd91ee17333ea0d2c52473c96aa5af526d6` plus bounded diffs
against `.pytest_cache/d3d2b-start`: source store/service, two POST handlers,
new regressions/HTTP smoke and PROFILE_SOURCES.md/CURATION.md. Specification
mapped rollback/refusal, exact storage ID/ownership, both adapters, recovery,
snapshot limits, unavailable sources and retained curation to behavioral checks.
Correctness traced both save callers, exception compatibility, dialect FK codes,
session rollback/closure, unchanged route authorization and raw taxonomy fields.
Medium review finding: implicit GitHub handle resolution could turn candidate
erasure into a 400 input error. Added a fresh absence check before that fallback
and a direct API regression. No acceptance-blocking finding remains in this
bounded write-path contract. No independent review or whole-portal claim.

- Initial red: `.resume/Scripts/python.exe -m pytest -q tests/test_profile_source_erasure.py --tb=short`:
  **12 failed, 4 passed, 6 skipped**, 1 warning, 7.05s. Raw FK errors, initial
  read/fetch/flush HTTP 500 and stale after-commit/source-only HTTP 200 reproduced.
- First green focused: **41 passed, 6 skipped**, 1 warning, 6.04s (new file plus
  source store/service/API and curation capture). Expanded pre-review focused:
  **76 passed, 7 skipped**, 1 warning, 8.51s (adds curation store/service and
  LinkedIn parse/transform). Final state results follow.
- `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3d2b.py`: initial migrated
  SQLite HTTP/restart **29/29**, before the implicit-handle adjustment.
- Compilation and `git diff --check` passed before that adjustment. Node binding
  command was attempted but remains unavailable; no frontend assets/handlers
  changed and no browser execution is claimed.

- `.resume/Scripts/python.exe .pytest_cache/check_d3d2b_implicit_red.py` loads
  only the saved pre-task handle resolver in memory: **1 failed, 30 deselected**,
  1 warning, 5.40s; 400 instead of 404 reproduced. No working source replacement.
- Final focused command:
  `.resume/Scripts/python.exe -m pytest -q tests/test_profile_source_erasure.py tests/test_profile_sources_store.py tests/test_profile_sources_service.py tests/test_profile_sources_api.py tests/test_curation_capture.py tests/test_curation_store.py tests/test_curation_service.py tests/test_linkedin_parse.py tests/test_linkedin_transform.py --tb=short`:
  **77 passed, 7 skipped**, 1 warning, 20.14s. Six unconfigured PG variants plus
  the SQLite variant of PostgreSQL lock inspection skipped.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3d2b_postgres.py`:
  broad PostgreSQL 18.6 **96 passed, 1 skipped**, 16 warnings, 112.43s. Adds
  migrations to the focused files. Includes controlled FK deletion blocking
  (`pg_blocking_pids`), both orderings and unrelated NOT NULL failures. Migration
  up/down/up and HTTP/restart **29/29** passed. Run began before the handle
  adjustment; final-source supplement follows. No full PG suite claimed.

- `.resume/Scripts/python.exe .pytest_cache/run_r1_s1_t3b_d3d2b_final_postgres.py`:
  final source/tests **52 passed, 1 skipped**, 1 warning, 72.39s; source erasure,
  source service/API and curation capture. Migration up/down/up and final PG
  HTTP/restart **29/29** passed. Both disposable PG clusters stopped cleanly.
- Final SQLite repeat: `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3d2b.py`:
  **29/29**, both adapters at fetch/flush/commit/source-only removal, fresh
  candidates/ingestion, snapshots, retained histories/curation, unavailable 200,
  malformed transport, org-only authorization denial and persisted restart reads.
- Final compilation and `git diff --check` passed again.

- `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2488 passed, 170
  skipped**, 44 warnings, 381.06s on final reviewed source/tests.
- `.resume/Scripts/python.exe .pytest_cache/check_d3d2b_docs.py`: local
  links/IDs/status/whitespace passed across **12 documents**. Working DB SHA256
  remains `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

Logs: `.pytest_cache/r1-s1-t3b-d3d2b-*.txt`. Synthetic providers only; no live-provider
or worker-crash claim. No working-data migration/deletion or deployment. Next:
**R1-S1-T3b-D3d2c**. D3d2 and higher parents remain open, including aggregate-read
response windows and raw curation-display-name policy review in D3d2d.

## <a id="r1-s1-t3b-d3d2c"></a>R1-S1-T3b-D3d2c - Login-state erasure ordering

Status: done 2026-09-28. Parent: [D3d2](#r1-s1-t3b-d3d2). Prerequisite: D3d2b.

| Child | Scope | Status |
|---|---|---|
| [D3d2c1](#r1-s1-t3b-d3d2c1) | Atomic candidate/existing-challenge erasure, rollback, interruption and retry. | Done |
| [D3d2c2](#r1-s1-t3b-d3d2c2) | Competing code issuance across erasure. | Done |
| [D3d2c3](#r1-s1-t3b-d3d2c3) | Competing redemption and combined login validation. | Done |

Portal/admin erasure commits candidate and login-state cleanup together (c1).
Reserved sends activate only if they survive cleanup (c2). Exact consumption,
principal resolution/creation and session/audit now share the address lock and
transaction (c3). Failure restores the uncommitted challenge; committed candidate
sessions cascade on erasure. Fresh signup and unrelated principals remain valid.

Acceptance: preserve all-plane cleanup, anti-enumeration, unrelated principals,
send-failure retry and legitimate fresh signup. No permanent contact ban, inferred
identity or working-data cleanup. Use synthetic capture/null email only.

Child records own red/green, both API doors, controlled SQLite/PostgreSQL,
migrations, migrated HTTP/interruption/restart, full pytest and self-review
evidence. C3 reran the combined login checks. Response delivery is outside the
transaction; a cookie returned after erasure cannot resolve its erased candidate.
[D3d2d](#r1-s1-t3b-d3d2d) still owns wider aggregate-response windows and shared
curation retention policy. T3/F05/R1-S1-Q remain open.

## <a id="r1-s1-t3b-d3d2c1"></a>R1-S1-T3b-D3d2c1 - Atomic existing login-state erasure

Status: done 2026-09-26. Parent: [D3d2c](#r1-s1-t3b-d3d2c). Prerequisite: D3d2b.

### <a id="r1-s1-t3b-d3d2c1--acceptance-defined-before-implementation"></a>Acceptance defined before implementation

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

### <a id="r1-s1-t3b-d3d2c1--evidence"></a>Evidence

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

### <a id="r1-s1-t3b-d3d2c1--diff-self-review"></a>Diff self-review

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

## <a id="r1-s1-t3b-d3d2c2"></a>R1-S1-T3b-D3d2c2 - Challenge issuance across erasure

Status: done 2026-09-27. Parent: [D3d2c](#r1-s1-t3b-d3d2c). Prerequisite: D3d2c1.

### <a id="r1-s1-t3b-d3d2c2--acceptance-before-implementation"></a>Acceptance before implementation

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

### <a id="r1-s1-t3b-d3d2c2--evidence"></a>Evidence

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

### <a id="r1-s1-t3b-d3d2c2--diff-self-review"></a>Diff self-review

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

## <a id="r1-s1-t3b-d3d2c3"></a>R1-S1-T3b-D3d2c3 - Redemption across erasure and login closure

Status: done 2026-09-28. Parent: [D3d2c](#r1-s1-t3b-d3d2c). Prerequisite: D3d2c2.

### <a id="r1-s1-t3b-d3d2c3--acceptance-before-implementation"></a>Acceptance before implementation

The consume, principal resolution/creation, session and candidate audit must
commit together under the existing per-address login lock. Erasure first makes
the exact stale challenge lose with generic refusal on every plane; redemption
first finishes before erasure removes candidate sessions and all pending login
state. Existing org/admin principals and their sessions remain independent.
Both portal and admin erasure doors, unrelated candidates, fresh signup after
erasure and single successful redemption remain supported.

An interrupted/failed transaction must leave no partial principal, session or
audit and must restore the uncommitted challenge. This deliberately replaces
the former crash-consumes-code behavior: retry is allowed only when no session
committed. No new schema, permanent address ban or lock over provider I/O.
Conditional consumption still rejects a replaced/deleted challenge observed by
a stale verifier. Response delivery itself is outside the transaction: a cookie
returned after subsequent erasure cannot resolve to an erased candidate.

Validate controlled competing connections and rollback on SQLite/PostgreSQL,
API generic refusal, migrated HTTP/process interruption/restart, composed c1/c2
checks, full pytest and recorded diff self-review. No UI/browser change or
contact-verification attempt-race scope is included.

### <a id="r1-s1-t3b-d3d2c3--implementation-and-diff-self-review"></a>Implementation and diff self-review

Resumed the existing uncommitted c3 implementation and preserved prior work.
AuthStore.login_transaction uses the c2 address lock. Consume, principal lookup/
creation and session/audit writes join its caller-owned SQLAlchemy session;
standalone store calls retain their own transactions. No schema change.

Same-agent review of HEAD `5480498` plus the uncommitted auth service/store,
candidate store, AUTH.md, redemption regressions and c1 smoke extension traced
both erasure doors, session cascades, principal callers and exception handling.
Specification: cleanup-first invalidates the exact challenge snapshot; redemption-
first commits before cleanup can remove the candidate and session. Org/admin
principals remain independent. Failure rolls back consumption and signup as a
unit; organization-name conflict still maps to 409, ordinary refusal to generic
400. Locks never span email I/O or response delivery. Existing store regressions
also cover changed/replaced challenge IDs/hashes.

Correctness/maintenance review: transaction ownership and exception propagation
are consistent; no new persistent address state or raw contact retention. The
resumed implementation removes SQL exception text from the org-name race log.
Strengthened rollback evidence to flush the candidate audit before interruption,
then assert no principal/session/audit survives and retry writes exactly once.
Expanded competing-verifier checks to all three planes; removed an unused smoke
import. No acceptance-blocking code findings remain. This is self-review, not
independent review. Final regression/journey evidence below passed.

### <a id="r1-s1-t3b-d3d2c3--evidence"></a>Evidence

All Python commands use `.resume/Scripts/python.exe`; providers are synthetic
capture/null, stores disposable. Validation ran 27 September; closure recorded
28 September. Working database hash is unchanged.

- Retained initial red log `.pytest_cache/d3d2c3-red.txt`: original
  `-m pytest tests/test_login_redemption_erasure.py -q --tb=short` had **2 failed,
  2 skipped**, 1.94s. Erasure after committed consume recreated a candidate;
  injected session failure left a newly committed candidate. This was collected
  before the resumed fix; the expanded current tests were rerun below.
- Final focused command: `-m pytest tests/test_login_redemption_erasure.py
  tests/test_auth_org_name_taken.py tests/test_auth_service.py
  tests/test_auth_store.py tests/test_login_erasure_atomic.py
  tests/test_login_issuance_erasure.py -q --tb=short`: **128 passed, 38 skipped**,
  1 Starlette/httpx deprecation warning, 78.66s.
  Log: `.pytest_cache/d3d2c3-focused-final.txt`.
- `node scripts/check_ui_bindings.js`: **402 bindings / 9 states passed**.
  No screen/handler change; no browser or live-provider claim.
- `scripts/smoke_r1_s1_t3b_d3d2c1.py --redemption`: migrated SQLite **46/46**,
  real HTTP on all planes through both erasure doors, held challenge snapshots,
  generic refusal/no cookie, unrelated session survival, restart and fresh login.
  Candidate/org process exits after consume and session creation leave no partial
  principal; restart restores the uncommitted code for exactly one successful
  retry. Log: `.pytest_cache/d3d2c3-smoke-sqlite-final.txt`.
- `-m py_compile src/app/auth/service.py src/app/auth/store.py
  src/app/candidates/store.py tests/test_login_redemption_erasure.py
  scripts/smoke_r1_s1_t3b_d3d2c1.py` passed.
- `.pytest_cache/run_r1_s1_t3b_d3d2c3_postgres.py` creates an owned disposable
  PostgreSQL 18.6 cluster (Asia/Calcutta), runs migration **up/down/up** and
  focused pytest: **257 passed, 2 skipped**, 16 warnings, 401.77s. Command:
  `-m pytest tests/test_login_redemption_erasure.py tests/test_auth_org_name_taken.py
  tests/test_auth_api.py tests/test_auth_session_twins.py
  tests/test_login_issuance_erasure.py tests/test_retention_plan.py
  tests/test_retention_sweep.py tests/test_login_erasure_atomic.py
  tests/test_portal_sessions.py tests/test_auth_service.py tests/test_auth_store.py
  tests/test_portal_service.py tests/test_portal_api.py tests/test_migrations.py
  -q --tb=short`, with the runner-owned `DEE_TEST_DB_URL`. Two skips are SQLite
  variants of PG lock inspection. Actual `pg_blocking_pids` observations cover
  redemption held after consume/principal/session, erasure-first commit/rollback
  and the composed issuance checks. Logs:
  `.pytest_cache/r1-s1-t3b-d3d2c3-pg-{migrations,focused}.txt`.

- Full SQLite `-m pytest -q --tb=short`: **2543 passed, 208 skipped**, 44 warnings,
  711.10s. Log: `.pytest_cache/d3d2c3-full-final.txt`. Warnings concern Starlette/
  httpx, SQLite expression-index reflection and Chroma legacy embedding config.
  Skips remain qualified; this is not a full PostgreSQL or live-provider run.
- The same PG runner completed migrated real HTTP/process interruption/restart:
  `scripts/smoke_r1_s1_t3b_d3d2c1.py --postgres` **24/24**, with `--issuance`
  **34/34**, with `--redemption` **46/46**. Together these compose c1 atomic
  cleanup, c2 reserved issuance and c3 atomic redemption. The runner stopped
  its owned cluster cleanly. Logs:
  `.pytest_cache/r1-s1-t3b-d3d2c3-pg-{smoke,issuance-smoke,redemption-smoke,stop}.txt`.
- Final documentation/static check `.pytest_cache/check_d3d2c3_docs.py` passed:
  local links in **156 Markdown files**, **20 active task records**, completed
  login group/archived children/next-task status, **5 Python files compiled** and
  unchanged working database SHA256. `git diff --check` passed. C1/c2 archival
  preserves their evidence, with parent links rebased; c3 evidence and the next
  review brief have distinct contracts. No application changes followed validation.

Login group D3d2c is complete. No whole-response delivery guarantee, browser,
full-PG, live-provider or independent-review claim. D3d2d owns the remaining
combined response/curation review; T3/F05/R1-S1-Q remain open.

## <a id="r1-s1-t3b-d3d2d"></a>R1-S1-T3b-D3d2d - Combined ordering and parent-coverage review

Status: done (2026-10-06; bounded acceptance and evidence complete). Parent: [D3d2](#r1-s1-t3b-d3d2). Prerequisite: D3d2c.

### <a id="r1-s1-t3b-d3d2d--combined-acceptance"></a>Combined acceptance

Review the combined erasure paths after report/source/login fixes. Start with
the [parent's combined acceptance](#r1-s1-t3b-d3d2); child evidence owns its
individual test commands and limitations. Trace actual callers and commit/response
boundaries, using targeted source reads rather than repeating the repository audit.

- Map portal/admin erasure and retained stores to the D3d/D3/D/T3b/T3 contracts.
  Distinguish atomic transactions/cascades from independent cleanup, retry and
  interrupted-response behavior. Preserve unrelated subjects/tenants, consent,
  identity policy, report lifetime after resume deletion and fresh uploads.
- Explicitly inspect source-list and portal aggregate response windows. Final
  existence reads do not guarantee erasure throughout HTTP delivery; state the
  supported behavior and expose any acceptance gaps with behavioral regressions.
- Review shared curation raw display-name retention and its input policy. Lack
  of an identity FK does not prove de-identification. Do not silently choose a
  new retention/identity policy or clean working data.
- Record combined migrated API/restart evidence on disposable stores and a
  separate diff self-review. Follow WORKFLOW.md for meaningful red/green, full
  pytest, PostgreSQL and browser gates when the review requires code changes.
  Split any substantial new remediation into bounded children before implementing.

Close this review and its ancestors only when their actual acceptance/evidence
is complete; otherwise name the remaining gaps and exact next bounded task.
T3/F05/R1-S1-Q are not closed by login-state validation alone.

### <a id="r1-s1-t3b-d3d2d--review-scope-and-bounded-children"></a>Review scope and bounded children

Reviewed HEAD `5480498` plus the preserved, validated c3 working diff. Traced
PortalService.erase through both routes, CandidateStore.delete_candidate,
ProfileSourceService/list store, portal aggregate builders, curation capture/
store/normalization and production composition. Same-agent review, not independent.

| Child | Distinct acceptance contract | Status |
|---|---|---|
| [D3d2d1](#r1-s1-t3b-d3d2d1) | Refuse source/portal aggregates when candidate erasure is observed before return. | Done |
| [D3d2d2](#r1-s1-t3b-d3d2d2) | Decide and implement raw curation-input/provenance/retention policy. | Done; actual named-database inventory decision in D4 |
| [D3d2d3](#r1-s1-t3b-d3d2d3) | Final combined migrated journey and ancestor acceptance mapping after fixes. | Done; synthetic validation only |
| [D3d2d4](#r1-s1-t3b-d3d2d4) | Read-only working-data legacy inventory, disposition decision and cleanup authorization boundary. | Done; empty actual inventory, no cleanup needed |

D2's owned lifecycle and explicit legacy procedure are implemented and validated.
[D3 evidence](#r1-s1-t3b-d3d2d3) owns combined acceptance and ancestor mapping;
[D4](#r1-s1-t3b-d3d2d4) records the actual empty named-database inventory and
no-action disposition decision. The active curation row-retention gap is settled
at that verified snapshot, so this bounded parent closes. No working-data cleanup
was needed or authorized. Existing backups/history and physical reclamation
remain outside this result; F05 and R1-S1 await their separate integration review.

The findings below are the original dated reproductions, resolved through D1/D2
engineering, D3 combined validation and D4's actual inventory. Recorded response,
maintenance and legacy-compatibility limits still apply to other/nonempty stores.

Findings (28 September):
- **Medium, aggregate disclosure:** source list checks the candidate before the
  signal read; portal my_data/access_log/consents return separately loaded values.
  Erasure after loading can therefore produce stale 200s. Erasure between route
  authentication and a service precheck can instead become an unhandled 500.
  D1 adds narrow erasure refusals and final existence snapshots; no guarantee
  after that last read or across independent child-only deletion follows.
- **High, retained raw input:** curation capture runs before source persistence,
  stores raw display_name and normalized key without subject provenance, and is
  neither cascaded nor swept. A submitted skill may contain personal text; a
  normalized-key length check is not a raw-input bound or de-identification.
  D2 must settle input/retention policy explicitly, preserve approved shared
  vocabulary, and avoid silently deleting working data. This blocks parent closure.
- **Documented snapshot limit:** reports_deleted counts before candidate deletion;
  it is not an exact count of rows removed by that transaction. Cascade safety is
  independent of that number. Existing write guards and final response reads do
  not establish whole-request erasure. D3 must verify the supported combined
  behavior and carry these limits into the parent decision.

Parent mapping: T3a and I own report/interview writes; D1 owns vector persistence;
D2 owns resolved ingest/fingerprints; D3a/b own retained screening input; D3c owns
candidate-linked audits; D3d1/2a/b own ingest/report/source write-response checks;
D3d2c owns login ordering. Those bounded completions remain valid. D3d2d1/d2/d3
address the aggregate, new-input and combined evidence gaps; D4's actual empty
inventory settles the last named-database row-retention gap. D3d2/D3d/D3/D/T3b/T3
close within their recorded acceptance; F05 awaits the R1-S1-Q sprint gate.
Consent/identity races stay R1-S2.

Curation review reproduction: `.resume/Scripts/python.exe
.pytest_cache/d3d2d-curation-probe.py` (synthetic LinkedIn Skills.csv, null
providers, isolated in-memory store) passed two characterization assertions:
erasure during parsing leaves no candidate/source rows, but both submitted raw
terms remain in the queue; a normalized key within the configured limit retains
a **5013-character** raw display name. The other sentinel includes a synthetic
name/address. Log: `.pytest_cache/d3d2d-curation-probe.txt`. This proves retention
and the raw-length gap, not de-identification or an approved replacement policy.
No working data was read or cleaned. D2's completed engineering addresses this
historical reproduction; D4 now owns the actual empty-inventory decision.

## <a id="r1-s1-t3b-d3d2d1"></a>R1-S1-T3b-D3d2d1 - Aggregate response refusal after erasure

Status: done 2026-09-28. Parent: [D3d2d](#r1-s1-t3b-d3d2d).

### <a id="r1-s1-t3b-d3d2d1--acceptance-before-implementation"></a>Acceptance before implementation

Bounded routes: GET /candidates/{id}/sources, /portal/me, /portal/access-log and
/portal/consents. Erasure after authentication/precheck or while assembling these
reads must yield generic 404 candidate-not-found if observed at a final existence
snapshot. Do not return loaded candidate data or leak an unhandled lookup error.
Translate only specific erasure exceptions; unrelated provider/store/programming
errors remain errors. Preserve surviving subjects, admin/candidate authorization,
source-type filtering/order, empty collections and legitimate fresh signup/upload.

The simpler fix is a final candidate existence check after composing the result,
plus narrow domain-error mapping. No schema, write lock, consent/identity policy,
curation retention or frontend change. Erasure after the final read can still
leave a response snapshot; child-only removal during aggregation is not an atomic
whole-view guarantee. Characterize that boundary explicitly.

Require red/green HTTP regressions at early/late read boundaries, both erasure
doors with unrelated actors, controlled connections on SQLite/PostgreSQL,
unrelated-error preservation, migrated real HTTP/restart on both backends, full
pytest, bindings and recorded diff self-review. Preserve previous c3 changes and
the working DB. D2 curation policy and D3 combined review remain separate tasks.

### <a id="r1-s1-t3b-d3d2d1--implementation-and-self-review"></a>Implementation and self-review

ProfileSourceService.list_sources now refuses missing candidates both before and
after reading signals. Portal my_data/access_log/consents validate candidate
existence after composing their return values. PortalSubjectErasedError remains
LookupError-compatible; the four routes translate only the relevant domain errors
to 404 candidate-not-found. MyData also handles source erasure during composition.

Self-review of HEAD `5480498` plus this task's source service, portal service,
four route handlers, aggregate regressions and source-smoke extension; preserved
c3 changes are outside this diff. Checked every list_sources caller (including
verification's existing LookupError fallback), both erasure doors, response
serialization, route authorization and error translation. Final reads use fresh
store sessions, after building the result; no transaction spans HTTP delivery.
Unrelated lookup failures remain 500s. Filtering/order, empty-live collections,
schema, candidate identity and consent semantics are unchanged. No blocking code
findings remain within d1. Broader raw curation and combined closure findings
remain in the parent; this is same-agent review, not independent review.

### <a id="r1-s1-t3b-d3d2d1--evidence"></a>Evidence

Project Python: `.resume/Scripts/python.exe`; synthetic providers/disposable stores.
- Red `-m pytest tests/test_aggregate_erasure.py -q --tb=short`: **20 failed,
  4 passed**, 1 warning, 11.32s. Sixteen controlled early/loaded reads returned
  stale 200 or unhandled 500 instead of 404; four final-snapshot probes found no
  final read. `.pytest_cache/d3d2d1-red.txt`.
- Initial focused `-m pytest tests/test_aggregate_erasure.py
  tests/test_profile_sources_service.py tests/test_profile_sources_api.py
  tests/test_portal_service.py tests/test_portal_api.py
  tests/test_profile_source_erasure.py -q --tb=short`: **79 passed, 7 skipped**,
  1 warning, 22.24s. `.pytest_cache/d3d2d1-focused.txt`.
- Expanded file-backed connection fixtures and mid-MyData source refusal:
  `-m pytest tests/test_aggregate_erasure.py -q --tb=short`: **26 passed,
  26 skipped**, 1 warning, 39.43s. Skips are unconfigured PG variants.
  `.pytest_cache/d3d2d1-expanded.txt`. Separate ASGI loops with event-held readers
  allow actual portal/admin DELETE requests while responses hold loaded values;
  no arbitrary race sleeps. Surviving keys/subjects, erased credentials, unrelated
  errors and erasure after the last read are asserted.
- `scripts/smoke_r1_s1_t3b_d3d2b.py --aggregates`: migrated SQLite **41/41**,
  real app/HTTP early/loaded/snapshot refusals, both erasure doors, surviving
  principals, fresh same-address uploads and restart. Synthetic source providers.
  `.pytest_cache/d3d2d1-smoke-sqlite.txt`.
- `node scripts/check_ui_bindings.js`: **402 bindings / 9 states passed**.
  No frontend change or browser execution claim.

- Full `-m pytest -q --tb=short`: **2569 passed, 234 skipped**, 44 warnings,
  487.88s. `.pytest_cache/d3d2d1-full.txt`. Warnings: Starlette/httpx, SQLite
  expression-index reflection and Chroma legacy embedding configuration.
- `.pytest_cache/run_r1_s1_t3b_d3d2d1_postgres.py`: owned disposable PostgreSQL
  18.6 cluster, Asia/Calcutta; migration **up/down/up**, focused **138 passed,
  1 skipped**, 16 warnings, 235.49s; migrated HTTP/restart **41/41** via
  `scripts/smoke_r1_s1_t3b_d3d2b.py --postgres --aggregates`; clean cluster stop.
  Focused command: `-m pytest tests/test_aggregate_erasure.py
  tests/test_profile_source_erasure.py tests/test_profile_sources_service.py
  tests/test_profile_sources_api.py tests/test_portal_service.py
  tests/test_portal_api.py tests/test_portal_sessions.py tests/test_report_cascade.py
  tests/test_migrations.py -q --tb=short`, using runner-owned `DEE_TEST_DB_URL`.
  The skip is the SQLite variant of PostgreSQL source-write lock inspection.
  Aggregate tests ran on both file-backed SQLite and isolated PG schemas.
  Logs: `.pytest_cache/r1-s1-t3b-d3d2d1-pg-{focused,migrations,aggregate-smoke,stop}.txt`.
- `.pytest_cache/check_d3d2d1_docs.py` passed: local links across **159 Markdown
  files**, **23 active task records**, d1/d2/d3 and parent status consistency,
  preserved login archive, **10 changed Python files compiled** (includes prior
  c3 work), unchanged working DB hash. `git diff --check` passed. Documentation
  self-review corrected stale portal-login/T3b wording and the curation config
  table's inaccurate raw-length claim; no curation policy was changed.

No application changes followed these checks. Full-PG, live-provider, browser
and independent-review evidence are not claimed. D1 is complete; parent D3d2d
remains in progress for D2 policy remediation and D3 combined validation.

## <a id="r1-s1-t3b-d3d2d2"></a>R1-S1-T3b-D3d2d2 - Curation input and retention policy

Status: done for policy implementation/validation (2026-10-05); option A approved
by user (2026-09-28). [D4](#r1-s1-t3b-d3d2d4) subsequently settled the named
working-database row-retention gap with an empty actual inventory. Parent:
[D3d2d](#r1-s1-t3b-d3d2d). Prerequisite: D3d2d1 (done).

Original defect: unreviewed raw terms entered shared curation storage with
norm_key/display_name retaining personal free text. Capture preceded source
persistence, lacked candidate provenance/expiry, and raw punctuation bypassed
the normalized-key length bound. Shared approved
vocabulary must remain available; absence of a candidate FK is not de-identification.

Before implementing, present concrete input/provenance/promotion/retention options
and obtain any required product-policy decision. Define behavior for refused
ingests, erased subjects, multiple contributors, resolved/ignored terms, reviewer
notes and historical rows. Do not infer identity from strings or clean working
data. Prefer a small explicit policy over heuristic claims of perfect PII detection.

Acceptance: the approved policy has observable safe boundaries, meaningful
regressions, preserved domain-independent vocabulary and normalization, and an
explicit historical-data/migration approach. Follow WORKFLOW.md for full pytest,
API/restart, PostgreSQL/migration and browser gates when applicable. Record limits
honestly; leave parents open if the required policy or evidence is missing.

### <a id="r1-s1-t3b-d3d2d2--approved-policy-option-a"></a>Approved policy (option A)

User decision: "go ahead with recommended" on 2026-09-28 approves option A
and the detailed contract below. No further policy confirmation is needed.
Working-data cleanup remains outside this authorization.

| Choice | New raw input | Tradeoff |
|---|---|---|
| A - candidate-linked review, recommended | Capture only against a successfully saved source, with deletable candidate/source provenance and a fixed 30-day review lifetime. | Keeps automatic vocabulary discovery; requires schema, lifecycle and reviewer-flow changes. |
| B - stop automatic capture | Source adapters no longer copy unknown terms into the shared queue. Maintain approved vocabulary through explicit administrator entries. | Smaller retention surface; reviewers must supply vocabulary themselves. Existing source records retain their current candidate-linked lifecycle. |

Approved A contract:

- Bound the raw submitted term before normalization: at most 128 Unicode code
  points, including surrounding whitespace; reject overlong/control-character
  input from curation without truncation or failing source ingestion. Preserve
  existing normalized-key bounds, Unicode/punctuation normalization and static
  taxonomy precedence. These are input limits, not personal-data detection.
- Persist A observations only with durable candidate/source ownership, enforced
  by foreign keys and deletion cascades. A refused source write creates no
  observation; erasure or source deletion removes its observations. No identity
  inference from names, aliases or other text. Best-effort capture errors must
  not log the submitted term or database exception text containing it.
- Keep each contributor's raw form separately. Recompute queue counts, source
  types and representative display text from surviving, unexpired observations;
  erasing one contributor must not expose its raw form through another's row.
  No detached aggregate may retain raw keys/display names after its last
  observation disappears. Repeated observations cannot extend earlier lifetimes.
- For A, expiry is 30 days from each observation's creation, regardless of
  repeats. Exclude expired observations from every review/read/resolve path;
  physically purge on startup and a documented daily maintenance run. Delayed
  maintenance means physical retention can exceed 30 days: test and document
  that operational limit rather than equating hidden rows with deletion.
- Promotion requires an explicit reviewer-approved vocabulary alias, canonical
  ID and category. Do not automatically promote the submitted raw display name
  or key. Retain only this approved vocabulary independently of contributors;
  remove associated raw observations on resolution. Approval is human judgment,
  not a guarantee that strings are anonymous. Preserve existing normalization
  behavior and domain-independent input handling; no new domain allowlist.
- Ignore deletes the raw observations rather than creating a permanent raw
  ignore-list entry. A later submission may reappear. Do not persist free-text
  reviewer notes or caller-supplied reviewer names in new curation decisions;
  use action/time and an authenticated operator identifier only if available.
  Do not invent an operator identity from the shared admin key.
- HTTP failure after a committed source write is still a response snapshot;
  it does not imply rollback of that source. Its observations remain linked and
  erasable. Resolve/delete/expiry races must never recreate raw observations.

Historical contract: additive migration with explicit legacy classification;
never fabricate ownership or silently delete existing rows. Preserve existing
resolved alias-to-canonical mappings for compatibility, but treat their legacy
raw display names, notes, reviewer names and all pending/ignored rows as
unattributed legacy content. Exclude that content from ordinary queue responses
and further automatic capture; provide a counts-only dry-run inventory and an
explicit operator-selected review/removal procedure. Historical resolved aliases
also require review because their keys may contain personal text. Keeping them
available is a compatibility exception, not proof of safe retention. Test the
migration/cleanup procedure only on synthetic stores; applying cleanup to working
data needs separate authorization. Legacy retention remains an explicit parent
closure gap until disposition is settled, even if new writes are fixed.

### <a id="r1-s1-t3b-d3d2d2--bounded-implementation-tasks"></a>Bounded implementation tasks

| Child | Acceptance ownership | Status |
|---|---|---|
| [D2a](#r1-s1-t3b-d3d2d2a) | Raw-input bounds before trimming/normalization and safe capture-failure logging. | Done |
| [D2b](#r1-s1-t3b-d3d2d2b) | Candidate/source-linked observations, expiry, approved promotion, ignore/reviewer fields and legacy isolation in runtime. | Done; storage and activation evidence in linked children |
| [D2c](#r1-s1-t3b-d3d2d2c) | Explicit legacy inventory/disposition tooling and integrated policy validation. | Done; no working-data disposition performed |

All engineering children are complete. [D2c evidence](#r1-s1-t3b-d3d2d2c)
owns the final integrated checks and review; [CURATION.md](../../CURATION.md)
owns the offline operator procedure. D2 completion alone did not settle retained
working-data legacy text; D4 now owns that actual inventory decision. Maintenance,
worker-refresh, storage-copy and response-snapshot limits remain in
[D3d2d3](#r1-s1-t3b-d3d2d3).
Detailed completed children are archived; this summary remains the policy owner.

### <a id="r1-s1-t3b-d3d2d2--implementation-and-validation-contract"></a>Implementation and validation contract

Before code, split the selected policy into bounded children if needed; do not
start the final combined D3d2d3 review while this contract is incomplete.
Regressions must cover raw-length bypass, refused writes, erasure during capture,
two contributors with colliding normalized keys, repeats/expiry, resolution and
ignore, reviewer fields, approved normalization, unrelated candidates and legacy
compatibility. Exercise routes with admin/unauthorized actors, restart on migrated
scratch storage, SQLite and controlled PostgreSQL ordering plus migration
up/down/up. Any reviewer UI/API contract change requires real browser evidence.
Full pytest and final diff self-review remain required for implementation.

### <a id="r1-s1-t3b-d3d2d2--policy-preparation-evidence-before-approval"></a>Policy-preparation evidence (before approval)

Inspected HEAD `5480498` plus existing uncommitted work: curation service/store/
models/schema, profile-source capture/store, normalization, resolve/list routes,
current curation tests and the parent's synthetic reproduction. Confirmed capture
precedes source persistence, raw length is unbounded, shared rows have no owner
or expiry, and resolution retains raw input plus free-text reviewer fields.
No new application behavior, data cleanup or application test result is claimed.
At that point the proposal awaited selection; the later user approval above
supersedes that blocker.

Validation: `.resume/Scripts/python.exe .pytest_cache/check_d3d2d2_docs.py`
passed (5 session documents, 63 local links, policy/next-task status checks).
`git diff --check` passed; Git emitted existing LF-to-CRLF conversion warnings.
No pytest, browser, API, PostgreSQL or live-provider run for this docs-only work.

Self-review: reviewed the five session documents against the inspected callers
and existing HEAD/uncommitted diff. Acceptance covers every requested policy
case without implying approval or completed remediation. Explicitly distinguished
review expiry from physical purge, failed source commits from response failures,
and legacy compatibility from safe retention. Parents remain open, prior code
and data are preserved, and D2 stays the exact next task. No independent review
or implemented safety guarantee is claimed.

## <a id="r1-s1-t3b-d3d2d2a"></a>R1-S1-T3b-D3d2d2a - Curation raw-input boundary

Status: done (2026-09-28). Parent: [D2](#r1-s1-t3b-d3d2d2), approved option A.

Trigger: submitted unknown skill text can normalize to a short key while
retaining an arbitrarily long display name; capture exceptions can log that text.
LinkedIn CSV trimming currently removes evidence of original whitespace length.

Acceptance:
- Reject raw curation submissions above 128 Unicode code points or containing
  Unicode control characters (category Cc), before trimming or key normalization.
  Preserve the existing normalized-key min/max guards. No truncation, personal
  data detector, domain allowlist or change to profile-source skill evidence.
- Apply the boundary to GitHub and original LinkedIn skill-cell values, including
  whitespace and quoted CSV controls. Valid repeated/case-varied terms retain
  existing per-signal deduplication; invalid variants cannot replace valid input.
- Capture failures remain observable using fixed event/source metadata, but no
  submitted text, exception message, SQL parameters or traceback leaves this path.
  Valid terms still queue, resolve and normalize; capture refusal/failure never
  breaks ingestion. Admin access boundaries remain enforced.
- Historical rows and approved mappings are untouched. Candidate linkage, TTL,
  resolution/ignore lifecycle and legacy disposition remain D2b/D2c; this child
  must not claim erasure or retention is fixed.

Validation: meaningful red/green service, both-adapter, API and rendered-log
regressions; full pytest; migrated scratch HTTP/restart journey; UI bindings and
diff self-review. No SQL/schema/concurrency change planned, so PostgreSQL and
migration up/down/up are not required for this boundary-only child. No visible
screen/handler/response contract change planned; no browser completion claim.

### <a id="r1-s1-t3b-d3d2d2a--implementation-and-review"></a>Implementation and review

Three runtime files: `curation/service.py` bounds raw capture before norm_key;
`profile_sources/linkedin.py` preserves original skill cells (other CSV fields
still trim); `profile_sources/service.py` selects one valid original cell per
unknown LinkedIn display skill and omits exception details from capture logs.
The curation store remains internal to the service capture boundary. Existing
shared retention and resolve behavior deliberately remain the open D2b contract.

Self-review after implementation: HEAD `5480498` plus the three runtime-file
diffs, new boundary tests and scratch smoke; earlier login/aggregate edits were
preserved. Specification review mapped every acceptance clause to input, both
adapter, API, rendered-log or existing normalization regressions. Correctness
review traced both capture callers, CSV whitespace/control stripping, duplicate
ordering, normalized-key collisions, private exception parameters and restart.
The raw CSV bypass and rendered-log disclosure found during preparation are
covered by regressions. No remaining finding blocks this child's boundary
contract; short personal text, ownership, TTL and historical rows remain explicit
parent risks. Same-agent review only; no independent review claim.

### <a id="r1-s1-t3b-d3d2d2a--validation-evidence"></a>Validation evidence

- Red: `.resume/Scripts/python.exe -m pytest -q tests/test_curation_input_boundary.py
  --tb=short` -> **13 failed, 3 passed**, one Starlette/httpx deprecation warning.
  Failures reproduced actual persisted oversized/control terms, adapter/API
  bypasses and private SQL parameters in rendered logs, not fixture failures.
  Log: `.pytest_cache/d2a-red.txt`. One later survivor-overwrite regression was
  added before final testing; parameter IDs were shortened for readable output.
- Initial focused: `.resume/Scripts/python.exe -m pytest -q
  tests/test_curation_input_boundary.py tests/test_curation_capture.py
  tests/test_curation_service.py tests/test_linkedin_parse.py
  tests/test_linkedin_transform.py tests/test_curation_api.py
  tests/test_curation_overlay.py tests/test_silent_swallows.py --tb=short`
  -> **57 passed**, same warning (`.pytest_cache/d2a-focused.txt`).
- `node scripts/check_ui_bindings.js` -> **402 bindings across 9 states** passed.
  Binding validation is not browser execution. `git -c core.safecrlf=false
  diff --check` passed.
- Working DB SHA256 checked unchanged at
  `4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

- Full reviewed application state: `.resume/Scripts/python.exe -m pytest -q
  --tb=short` -> **2587 passed, 234 skipped, 44 warnings**, 845.96 seconds;
  `.pytest_cache/d2a-full.txt`. Warnings: Starlette/httpx deprecation, SQLite
  expression-index reflection/autogenerate limits, Chroma legacy embedding config.
- First `.resume/Scripts/python.exe scripts/smoke_curation_input.py` -> **11/13**:
  two restart assertions incorrectly measured the response envelope instead of
  its `sources` list. Corrected the harness to compare both candidate ID and
  the complete saved signal. No application change resulted; this initial run
  does not count as a passing journey.
- Final same smoke command -> **13/13 passed**, exit 0;
  `.pytest_cache/d2a-smoke-final.txt`. Real migrated SQLite startup, two candidates,
  LinkedIn/GitHub ingestion with synthetic providers, admin refusal, resolution,
  process restart, exact retained source signals and reloaded normalization.
  Both scratch server processes were stopped. Rendered process logs contain the
  capture warning but no injected private term or exception text.
- `.resume/Scripts/python.exe -m compileall -q src/app/curation/service.py
  src/app/profile_sources/service.py src/app/profile_sources/linkedin.py
  tests/test_curation_input_boundary.py scripts/smoke_curation_input.py` passed.

Only the smoke assertion and documentation changed after full pytest; the affected
journey was rerun successfully. Final same-agent review includes that corrected
response-envelope assertion. Documentation checker
`.resume/Scripts/python.exe .pytest_cache/check_d3d2d2_docs.py` passed on ten
session documents; final link/status and whitespace checks were repeated after
closure updates. No PostgreSQL, real browser or live-provider evidence is claimed
for this non-SQL boundary change. Next task: D2b; D2 and wider parents stay open.

## <a id="r1-s1-t3b-d3d2d2b"></a>R1-S1-T3b-D3d2d2b - Owned curation review lifecycle

Status: done (2026-10-05); split before implementation (2026-09-28).
Parent: [D2](#r1-s1-t3b-d3d2d2). Prerequisite: D2a.

### <a id="r1-s1-t3b-d3d2d2b--bounded-children"></a>Bounded children

| Child | Acceptance ownership | Status |
|---|---|---|
| [D2b1](#r1-s1-t3b-d3d2d2b1) | Additive owned-observation/approved-alias schema and explicit legacy classification; database ownership and migration validation. | Done |
| [D2b2](#r1-s1-t3b-d3d2d2b2) | Owned-store lifecycle, followed by atomic runtime/reviewer activation; API/browser and ordering validation. | Done; linked children own store and activation evidence |

The storage foundation and coupled runtime/reviewer activation are complete.
New capture and review use owned observations exclusively; linked child records
own validation. Legacy inventory/disposition and integrated policy closure remain
[D2c](#r1-s1-t3b-d3d2d2c). Working data was preserved.

Implement the approved option A runtime contract: source/candidate-owned raw
observations written only against durable sources; erasure/source cascades;
survivor-only aggregates; fixed 30-day expiry and startup/daily physical purge;
explicit reviewer-approved aliases separated from raw input; ignore removes raw
observations; no new free-text notes or caller-supplied reviewer identity.
Classify legacy rows additively and exclude legacy raw content from review/capture
while preserving existing approved overlay mappings. Do not alter working data.

Acceptance is the parent's approved policy, including concurrency, original
lifetimes under repeats, unrelated contributors/tenants, explicit snapshot limits
and preservation of normalization. Split further before code if this combined
schema/API switch cannot fit a focused session; do not leave a new raw-write path
reachable through an old resolution path without the approved protections.

Required evidence: red/green regressions, full pytest, migrated API/restart,
controlled PostgreSQL writes/deletes and migration up/down/up, relevant real
browser contract journeys and final diff self-review. Use synthetic data only.

## <a id="r1-s1-t3b-d3d2d2b1"></a>R1-S1-T3b-D3d2d2b1 - Owned curation storage foundation

Status: done (handoff finalized 2026-09-29). Parent: [D2b](#r1-s1-t3b-d3d2d2b).

### <a id="r1-s1-t3b-d3d2d2b1--acceptance-and-scope"></a>Acceptance and scope

Add an additive migration after 0027 and matching ORM models. Raw observations
reference a durable profile source with ON DELETE CASCADE; candidate ownership
is derived through that source's existing candidate FK, avoiding inconsistent
duplicated owner IDs. Separate observations preserve each contributor's raw form
and creation timestamp; there is no detached aggregate. Index source, normalized
key and creation time for deletion/review/30-day cutoff queries in D2b2.

Approved aliases occupy a separate table with explicit alias/key, canonical,
category, action/time and optional authenticated admin FK. No notes or supplied
reviewer name. Preserve every legacy row/field and resolved normalization mapping;
classify all old-table rows as legacy_unattributed without guessing ownership or
copying them into approved vocabulary. No runtime capture/review/UI switch here.

Required regressions: missing source refusal, candidate/source cascades with
unrelated contributors and approved vocabulary surviving, same-key independent
observations/timestamps, length/non-null/alias-uniqueness constraints, legacy
preservation and schema/model parity, migration up/down/up. Controlled PostgreSQL
insert/delete orderings on real migrated disposable storage. Full pytest,
migrated HTTP/restart compatibility, bindings and final diff self-review.
No browser gate for this schema-only child; real reviewer browser remains D2b2.
Downgrade removes the new tables, so rollback data loss must be documented and
tested only on synthetic stores. Working data must not be migrated or cleaned.

### <a id="r1-s1-t3b-d3d2d2b1--evidence"></a>Evidence

Red: `.resume/Scripts/python.exe -m pytest -q tests/test_curation_storage_migration.py
-k 'cascade' --tb=short`: **2 failed, 2 skipped, 24 deselected**. Both SQLite
failures were the intended `owned curation storage missing` assertion; PostgreSQL
was not configured for this red run. No fixture/import failure counted as red.

Implementation: `0028_owned_curation.py`, `app/curation/models.py`, new behavioral
`test_curation_storage_migration.py` and existing migration parity coverage.
There are no new runtime readers/writers yet. Original timestamps and raw forms
are independent rows; enforcing the 30-day read/purge policy remains D2b2.

Initial focused run (before three additional review checks):
`.resume/Scripts/python.exe -m pytest -q tests/test_curation_storage_migration.py
tests/test_migrations.py --tb=short`: **24 passed, 18 skipped**, 29 warnings.
Final reviewed application state: `.resume/Scripts/python.exe -m pytest -q
--tb=short`: **2600 passed, 255 skipped, 61 warnings**, 569.25s, exit 0.
Log: `.pytest_cache/curation-storage-full.txt`. This includes all final storage
tests; the later smoke-only extension was validated with its own real HTTP run.
Full-suite warnings: Starlette/httpx deprecation, SQLite expression-index
reflection/autogenerate limitations and Chroma legacy embedding configuration.

- PostgreSQL 18.6, server timezone Asia/Calcutta: `.resume/Scripts/python.exe
  .pytest_cache/run_curation_storage_postgres.py` created a fresh disposable
  password-authenticated local cluster, ran Alembic `upgrade head`, `downgrade
  base`, `upgrade head`, then `.resume/Scripts/python.exe -m pytest
  tests/test_curation_storage_migration.py tests/test_migrations.py
  tests/test_curation_store.py tests/test_curation_overlay.py -q --tb=short` with
  process-scoped `DEE_TEST_DB_URL`: **54 passed, 4 skipped, 32 warnings**, 91.92s.
  The new module runs SQLite and PostgreSQL; four skips are its explicitly
  PostgreSQL-only races on the SQLite parameters. Each of four actual PG races
  observed `pg_blocking_pids` before releasing the owning transaction. Both
  insert-first/delete-first orders for candidate and source deletion ended with
  no orphan and the unrelated source intact. Populated 0027/0028 roundtrips
  preserve every legacy field and overlay. Clean cluster shutdown exit 0.
  Local logs: `.pytest_cache/curation-storage-pg-{focused,migrations,stop}.txt`.
  This is focused PostgreSQL evidence, not a full PostgreSQL suite.
- `.resume/Scripts/python.exe scripts/smoke_curation_input.py`: **13/13 passed**,
  migrated SQLite HTTP startup/restart with two synthetic contributors, admin
  refusal and approved legacy normalization. Both server processes stopped.
  The optional `--owned-storage` extension separately seeds the inactive new
  tables, checks restart and real HTTP erasure; it does not claim new capture.
  `.resume/Scripts/python.exe scripts/smoke_curation_input.py --owned-storage`:
  **18/18 passed**, both processes stopped. Direct inspection after the real
  candidate DELETE found only the other contributor's raw form and preserved
  the independent approved alias and classified legacy row. Logs:
  `.pytest_cache/curation-storage-{http,owned-http}.txt`.
- `node scripts/check_ui_bindings.js`: **402 bindings across 9 states** passed.
  `.resume/Scripts/python.exe -m compileall -q src/app/curation/models.py
  alembic/versions/0028_owned_curation.py tests/test_curation_storage_migration.py
  tests/test_migrations.py` passed. `git diff --check` passed with existing
  LF-to-CRLF warnings. No browser needed for this schema-only contract.

Self-review, 2026-09-28: HEAD `5480498` plus this session's model/migration/test
diff and CURATION.md addition, preserving prior uncommitted work. Specification
review checked each storage criterion, exact legacy row preservation, no inferred
ownership/promotion, bounded strings, optional real operator FK, and zero runtime
references to new models/tables outside their definitions. Correctness review
traced the existing non-null profile-source candidate FK and cascades, older-app
default compatibility, source/candidate deletion order, independent repeated
observations, alias survival, migration registration and rollback behavior.
Added validation of operator deletion, schema parity/legacy writer defaults,
Unicode boundaries and rolled-back source transactions during review. No remaining
acceptance-blocking finding in this schema scope. This is self-review, not an
independent review; no lifecycle, browser or live-provider guarantee is claimed.
The later optional smoke extension was also self-reviewed for scratch-only SQL,
real saved-source provenance, exact survivor assertions and process cleanup;
it changes validation only, not application behavior.

Focused-run warnings are SQLite expression-index reflection/autogenerate limitations.
The local PostgreSQL runner depends on the previously downloaded ignored
portable runtime; it is evidence, not a portable installation procedure. Neither
the runner nor the smoke reads live provider credentials or migrates working data.

Final checks: compilation also passed for `scripts/smoke_curation_input.py`;
`.resume/Scripts/python.exe .pytest_cache/check_curation_storage_docs.py --final`
checked the eight session documents' links/statuses. `git diff --check` passed.
Working database SHA256 remains
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
No working-data migration, cleanup, publication or deployment occurred.
Next: [D2b2](#r1-s1-t3b-d3d2d2b2). D2b/D2 and wider parents remain open.

## <a id="r1-s1-t3b-d3d2d2b2"></a>R1-S1-T3b-D3d2d2b2 - Owned curation runtime and reviewer switch

Status: done (2026-10-05); split before implementation (2026-09-29).
Parent: [D2b](#r1-s1-t3b-d3d2d2b). Prerequisite: D2b1.

### <a id="r1-s1-t3b-d3d2d2b2--bounded-children"></a>Bounded children

| Child | Acceptance ownership | Status |
|---|---|---|
| [D2b2a](#r1-s1-t3b-d3d2d2b2a) | Owned-store capture, survivor snapshots, fixed expiry, atomic promotion/ignore, purge and overlay composition; transaction/order validation. No production wiring. | Done |
| [D2b2b](#r1-s1-t3b-d3d2d2b2b) | Switch source capture, service/API/reviewer UI and maintenance together; authenticated API/browser/restart validation. | Done |

Transaction/aggregation semantics and the coupled source/maintenance/reviewer
contracts were split before implementation. D2b2a completed the store lifecycle;
D2b2b activated all production callers together. New raw observations use owned
review exclusively. Both children are complete; linked records own their evidence.

Implement the remaining [approved policy](#r1-s1-t3b-d3d2d2) together:
capture after durable source save; survivor-only raw aggregates; fixed creation
time and 30-day expiry on every read/resolve; startup and documented daily purge;
explicit approved alias/canonical/category promotion; ignore deletes raw input;
no free-text reviewer notes or supplied identity; legacy rows hidden from ordinary
queue/capture while legacy resolved overlays remain compatible. Use D2b1's
source-derived ownership and separate approved table. Do not route new raw
observations through legacy resolution, even temporarily.

Acceptance includes refused source writes, erasure/capture/resolve/expiry races,
same-key contributors and tenants, repeated observations preserving original
lifetimes, surviving display/source/count derivation, authenticated/unauthorized
reviewers, explicit aliases differing from submitted raw text, restart/purge and
normalization compatibility. Record response snapshot and delayed purge limits.

Required: red/green focused tests, full pytest, migrated HTTP/restart, controlled
PostgreSQL concurrency, real reviewer browser journeys and final diff self-review.
Legacy inventory/disposition stays D2c. Parent retention finding remains open.

## <a id="r1-s1-t3b-d3d2d2b2a"></a>R1-S1-T3b-D3d2d2b2a - Owned curation store lifecycle

Status: done (2026-09-29). Parent: [D2b2](#r1-s1-t3b-d3d2d2b2).

### <a id="r1-s1-t3b-d3d2d2b2a--acceptance-and-scope"></a>Acceptance and scope

Implement an inactive owned store on migration 0028. Only durable source IDs can
capture raw observations; ownership/source type derive from the saved source.
Repeats insert independent timestamps. List/get aggregate only surviving rows
younger than 30 days, including representative display, counts and source types;
pagination and all components use one SQL snapshot. No legacy raw queue content.

Promotion requires explicit bounded alias/canonical/category and map/create;
ignore retains no raw decision record. Atomically delete matching observations
and persist only approved vocabulary, with optional real admin FK, no notes or
supplied reviewer name. Competing resolves have one winner; erased/expired-only
terms cannot promote, including expiry while waiting on a database lock. Failed
approval rolls back raw deletion. Approved vocabulary survives erasure, composes
with legacy resolved overlays and preserves static taxonomy precedence.

Purge physically removes expired observations without changing earlier lifetimes,
approved aliases or legacy content. Reads are statement snapshots; concurrent
fresh captures may reappear. Startup/daily invocation, production capture timing,
HTTP auth and reviewer browser contract belong to D2b2b, not this inactive store.

Required: red/green behavioral regressions on migrated SQLite and PostgreSQL,
controlled competing connections for capture/delete, resolve/delete, concurrent
resolve and expiry/purge; rollback, survivor, repeat, exact cutoff and pagination
checks; full pytest; scratch application HTTP/restart plus direct store lifecycle
journey; migration compatibility up/down/up; bindings and recorded diff self-review.
No browser gate because no visible screen/API contract changes in this child.

### <a id="r1-s1-t3b-d3d2d2b2a--implementation-and-review"></a>Implementation and review

`CurationStore` gains separate owned methods; existing production methods are
unchanged. Capture uses INSERT from the durable source, bounded original input,
independent timestamps and its FK cascade. Listing uses a single CTE/window query
for paged aggregates and distinct source types, without persisting aggregates.
Resolution claims rows with DELETE RETURNING and checks the clock after lock
acquisition; alias insertion shares that transaction. Expired-only resolution
removes expired rows then returns generic not-found. Alias conflicts/FK failures
roll back raw deletion. No schema change or working-data operation.

Self-review: HEAD `5480498` plus this session's `curation/store.py`, new
`test_curation_owned_store.py`, smoke extension and task/documentation changes.
Specification review traced each owned-store criterion and confirmed production
capture/review/overlay wiring still uses legacy methods. Correctness review
covered FK deletion order, statement snapshots, mutable pagination, raw-free
decision receipts, ignored-row deletion, failure rollback and alias precedence.
Added mixed-expiry/operator/static-precedence and capture-first ordering checks
to cover evidence gaps. No remaining blocking finding in this bounded store
scope; this is self-review, not independent review.

Limits: service-level canonical/category taxonomy validation and authorization
stay with activation, as do safe HTTP conflict handling, startup/daily scheduling,
and removal of legacy write/resolve callers. Concurrent new captures may reappear;
reads and approval eligibility have snapshot boundaries, not delivery locks.
An alias uniqueness conflict currently raises IntegrityError and rolls back;
activation must return a safe conflict response. Legacy cleanup stays D2c.

### <a id="r1-s1-t3b-d3d2d2b2a--evidence"></a>Evidence

The initial test collection had a test-module import error; it is not red evidence.
After correcting the import, ran the new test against the exact pre-session
`curation/store.py` from HEAD using a try/finally restore harness:
`.resume/Scripts/python.exe -m pytest -q tests/test_curation_owned_store.py
-k requires_saved_source --tb=short`: **1 failed, 1 skipped, 66 deselected**.
Failure: owned capture method absent; no fixture/import failure. Implementation
was restored byte-for-byte. Log: `.pytest_cache/curation-owned-red.txt`.

Initial green before added review checks: `.resume/Scripts/python.exe -m pytest
-q tests/test_curation_owned_store.py --tb=short`: **24 passed, 24 skipped**,
24 SQLite reflection warnings.

Final reviewed application/test state: `.resume/Scripts/python.exe -m pytest -q
--tb=short`: **2627 passed, 302 skipped, 98 warnings**, 887.18s, exit 0. Log:
`.pytest_cache/curation-owned-full.txt`. Warnings: existing Starlette/httpx and
Chroma deprecations plus SQLite expression-index reflection/autogenerate limits.

PostgreSQL 18.6, timezone Asia/Calcutta: `.resume/Scripts/python.exe
.pytest_cache/run_curation_owned_postgres.py` created a fresh disposable local
cluster, ran Alembic upgrade head / downgrade base / upgrade head, then:
`.resume/Scripts/python.exe -m pytest tests/test_curation_owned_store.py
tests/test_curation_storage_migration.py tests/test_migrations.py
tests/test_curation_store.py tests/test_curation_overlay.py -q --tb=short`:
**113 passed, 13 skipped, 66 warnings**, 328.12s. Controlled PG lock waits use
`pg_blocking_pids` before releasing the owner: delete-first capture/resolve for
candidate and source, resolve-first competing resolve/delete/purge, lock-wait
expiry and purge-first refusal. Existing storage insert/delete and populated
migration roundtrips also pass. Skips are PostgreSQL-only cases on SQLite.
Clean cluster shutdown exit 0. Logs: `.pytest_cache/curation-owned-pg-*.txt`.
Three tests added during review are included in the full suite. Their additional
PostgreSQL run, `.resume/Scripts/python.exe
.pytest_cache/run_curation_owned_review_postgres.py`, uses the same disposable
cluster/migration procedure and runs `.resume/Scripts/python.exe -m pytest
tests/test_curation_owned_store.py -k "map_operator_identity or refuses_free_text
or capture_first" -q --tb=short`: **5 passed, 1 skipped, 68 deselected,
3 warnings**, 8.45s. The capture-first race confirms a waiting candidate erasure
sweeps the actual store insert. Logs: `.pytest_cache/curation-owned-review-pg-*.txt`.
The second cluster also shut down cleanly (exit 0).
These are focused PostgreSQL runs, not a full-PG suite. Local runners depend on
the existing ignored portable runtime; they do not read live credentials or
migrate working storage.

`.resume/Scripts/python.exe scripts/smoke_curation_input.py --owned-lifecycle`:
**25/25 passed** on migrated scratch SQLite. Real HTTP startup creates two
candidates/sources; direct owned-store capture/promotion/expiry/purge runs while
the app is stopped; restart and real HTTP erasure prove surviving owned fields
and approved aliases. Direct ignore removes remaining observations. Existing
legacy ingestion/normalization/auth and safe failure-log checks pass. Both server
processes stopped. This is HTTP plus direct-store evidence, not activated owned
capture or a browser. Log: `.pytest_cache/curation-owned-http.txt`.

`node scripts/check_ui_bindings.js`: **402 bindings across 9 states** passed.
`.resume/Scripts/python.exe -m compileall -q src/app/curation/store.py
tests/test_curation_owned_store.py scripts/smoke_curation_input.py` and
`git diff --check` passed (existing LF-to-CRLF warnings). Working DB SHA256 remains
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.

Next: [D2b2b activation](#r1-s1-t3b-d3d2d2b2b). No browser or live-provider
claim; production retention is still open. Prior edits and working data preserved.
Final `.resume/Scripts/python.exe .pytest_cache/check_curation_owned_docs.py
--final` passed: 8 documents, 91 local links and parent/child/next-task statuses.
Final `git diff --check` passed. No publication or deployment occurred.

## <a id="r1-s1-t3b-d3d2d2b2b"></a>R1-S1-T3b-D3d2d2b2b - Activate owned capture and reviewer contract

Status: done (2026-10-05). Parent: [D2b2](#r1-s1-t3b-d3d2d2b2). Prerequisite: D2b2a.

Switch production ingestion, curation service/API, startup/daily maintenance and
reviewer UI together to the owned store. Capture only after saved source commit;
retain D2a original-input/log boundaries. No new raw terms in legacy storage or
legacy resolution. Explicit approved alias/canonical/category, no notes or supplied
identity; authenticated operator ID only when available, NULL for shared keys.
Hide legacy raw queue content while retaining approved normalization compatibility.

Acceptance: the full [approved A policy](#r1-s1-t3b-d3d2d2), using D2b2a's store
evidence without repeating its audit. Test refused writes and response snapshots,
erasure/expiry/capture races, contributors across tenants, repeat lifetimes, admin
and unauthorized actors, alias different from raw text, ignore/reappearance,
restart, startup purge and a documented runnable daily purge command. Document
delayed physical purge and process-local overlay limits. Remove obsolete reachable
legacy write/resolve paths and update affected contracts/tests.

Required: red/green focused regressions, full pytest, migrated HTTP/restart,
controlled PostgreSQL integration ordering, real reviewer browser journeys
(success, reload, expiry/erasure error, auth refusal), bindings and final diff
self-review. D2c retains legacy disposition; wider retention finding stays open.

Implementation contract: keep the queue page shape and pending/default filters;
resolved/ignored filters return empty pages because decisions no longer retain raw
terms. Resolve returns a raw-free decision receipt. Promotion requires explicit
alias/canonical/category; map validates the supplied category against taxonomy.
Reject notes and supplied identity fields. Uniqueness conflicts return generic
409 and roll back raw deletion. Startup purge fails startup on failure; daily
purge is an explicit operator command, not an in-process scheduler. Legacy writes
and resolution methods are removed; historical overlay reads remain compatible.


### <a id="r1-s1-t3b-d3d2d2b2b--implementation-and-self-review"></a>Implementation and self-review

Production GitHub/LinkedIn capture now follows saved-source commit and uses only
owned observations. Service/API/UI review, startup purge, daily command and
approved overlays switched together. Legacy write/list/resolve methods are removed;
legacy resolved normalization reads only key/canonical/category. Queue snapshots
expose no legacy content or decision notes. Promotion never copies the raw key.
[CURATION.md](../../CURATION.md) owns the current contract and maintenance command.

Self-review: HEAD `5480498` plus this session's uncommitted curation schema/store/
service, source capture, service composition, curation routes, operator template,
validation scripts and affected regressions. Prior unrelated edits were preserved.
Specification review traced each approved A criterion to store/runtime/API/browser
checks; legacy disposition remains D2c. Correctness review checked commit/capture
ordering, FK erasure, expiry after lock waits, rollback on alias conflict, session/
CSRF attribution, raw-free responses/logs, paging, stale async replies, errors and
normalization compatibility. No remaining blocking finding in activation scope.
Same-agent self-review; no independent review or live-provider claim.

Findings fixed before final checks: medium, operator editor listed unsupported
categories (`frontend/Veritas.dc.html`); a reviewer following that list could not
create vocabulary. Replaced it with actual taxonomy categories and exercised a
`data` create in Chrome. Added two-tenant uploaded-resume provenance/survivor
coverage during specification review. Its first fixture used the wrong org response
shape; corrected it and confirmed the two different org stamps before assertions.
An old owned-store test still seeded legacy data through the removed writer;
converted it to an explicit historical fixture. Neither fixture error is red evidence.

### <a id="r1-s1-t3b-d3d2d2b2b--evidence"></a>Evidence

Red before implementation: `.resume/Scripts/python.exe -m pytest -q
 tests/test_curation_activation.py -k "capture_uses_committed or explicit_alias"
 --tb=short`: **2 failed, 2 deselected**, expected absent owned capture and exposed
legacy queue, not setup errors. `.pytest_cache/curation-activation-red.txt`.
Initial green: same file without `-k`: **4 passed**. Final added runtime/service
checks: `.resume/Scripts/python.exe -m pytest -q tests/test_curation_activation.py
 tests/test_curation_service.py --tb=short`: **17 passed, 1 warning**, 6.15s.

`.resume/Scripts/python.exe .pytest_cache/run_curation_activation_postgres.py`:
fresh disposable PostgreSQL **18.6**, Asia/Calcutta, migration upgrade head /
downgrade base / upgrade head, then `.resume/Scripts/python.exe -m pytest
 tests/test_curation_activation.py tests/test_curation_owned_store.py
 tests/test_curation_storage_migration.py tests/test_curation_api.py
 tests/test_curation_service.py tests/test_curation_input_boundary.py
 tests/test_profile_source_erasure.py tests/test_migrations.py
 tests/test_curation_store.py tests/test_curation_overlay.py -q --tb=short`:
**185 passed, 15 skipped, 70 warnings**, 288.57s. Controlled competing connections
use `pg_blocking_pids` to establish capture/delete, resolve/delete, competing
resolves, purge and lock-wait expiry order. Raw claim/approval failure rollback,
input boundaries and authenticated API integration passed. Clean shutdown exit 0.
Logs: `.pytest_cache/curation-activation-pg-*.txt`. Final review's new tenant test
has an additional disposable PG run recorded below. These are focused PG runs.

Migrated SQLite journeys (synthetic providers; all server processes stopped):
- `.resume/Scripts/python.exe scripts/smoke_curation_activation.py`: **14/14**,
  real capture, refused writes, survivor fields, explicit alias, ignore/reappearance,
  restart, physical startup purge, daily command and compatible legacy normalization.
- `.resume/Scripts/python.exe scripts/check_ui_curation_browser.py`: **28/28**,
  includes the HTTP/restart base plus real Chrome operator login, blank alias,
  422 recovery, map/create/ignore, reload, network-failure draft recovery, 409 draft/
  raw preservation, stale expiry/erasure 404 and revoked access returning to login.
  No console errors or uncaught exceptions. Chrome uses a fresh profile and shipped
  CDN assets; internet is required. No offline-browser reproducibility claim.
- `.resume/Scripts/python.exe scripts/smoke_curation_input.py --owned-lifecycle`:
  **25/25**; original-input/log boundaries and historical direct-store modes updated
  to the activated contract, including restart and real HTTP erasure.
- `.resume/Scripts/python.exe scripts/smoke_r1_s1_t3b_d3d2b.py`: **29/29**, affected
  source erasure/restart journey and saved-survivor queue assertions.
- `.resume/Scripts/python.exe scripts/smoke_s63.py`: **16 checks / SMOKE OK**, updated
  explicit map/create fields, ignored reappearance and raw erasure.

Logs: `.pytest_cache/curation-activation-{http,browser-final,input-http,source-http,
s63-http}.txt`. Bindings: `node scripts/check_ui_bindings.js`, **425 bindings / 10
states**. `node --check frontend/api.js` and `node --check frontend/support.js`
passed. Compilation and final full regression/doc/diff results follow below.
A preliminary full run was deliberately stopped after the review added the tenant
regression; it is not a completed full-suite result.

Limits: delayed daily maintenance/downtime can physically retain expired raw input
past 30 days; responses are snapshots and concurrent fresh captures may reappear.
Overlays refresh only in the resolving process and reload on restart. Legacy aliases
remain a compatibility exception, not anonymization. No working-data cleanup,
deployment, OS scheduling, representative model-quality or full-PG-suite claim.


Additional PostgreSQL review regression:
`.resume/Scripts/python.exe .pytest_cache/run_curation_activation_review_postgres.py`
created another disposable PG 18.6 cluster, repeated migration up/down/up and ran
`.resume/Scripts/python.exe -m pytest tests/test_curation_activation.py -k two_tenant
-q --tb=short`: **1 passed, 9 deselected, 1 warning**, 4.36s; shutdown exit 0.
Logs: `.pytest_cache/curation-activation-review-pg-*.txt`.

Final focused command: `.resume/Scripts/python.exe -m pytest -q
 tests/test_curation_activation.py tests/test_curation_service.py
 tests/test_curation_api.py tests/test_curation_capture.py tests/test_curation_schema.py
 tests/test_curation_store.py tests/test_curation_input_boundary.py
 tests/test_profile_source_erasure.py tests/test_curation_owned_store.py
 tests/test_curation_storage_migration.py tests/test_silent_swallows.py --tb=short`:
**116 passed, 75 skipped, 55 warnings**, 95.67s. Skips are PG-only ordering/backend
cases on SQLite; warnings are Starlette/httpx and SQLite expression-index reflection.

Final compilation passed:
`.resume/Scripts/python.exe -m compileall -q src/app/curation
 src/app/profile_sources/service.py src/app/services/__init__.py src/app/api/routes.py
 tests/curation_helpers.py tests/test_curation_activation.py tests/test_curation_service.py
 tests/test_curation_api.py tests/test_curation_schema.py tests/test_curation_store.py
 tests/test_curation_input_boundary.py tests/test_curation_owned_store.py
 tests/test_curation_storage_migration.py tests/test_profile_source_erasure.py
 tests/test_silent_swallows.py scripts/purge_curation.py scripts/smoke_curation_activation.py
 scripts/check_ui_curation_browser.py scripts/smoke_curation_input.py scripts/smoke_s63.py
 scripts/smoke_r1_s1_t3b_d3d2b.py`.

Final full regression: `.resume/Scripts/python.exe -m pytest -q --tb=short`:
**2637 passed, 302 skipped, 98 warnings**, 614.55s (0:10:14), exit 0.
Log: `.pytest_cache/curation-activation-full-final.txt`. Warnings: existing
Starlette/httpx and Chroma deprecations plus SQLite expression-index reflection/
autogenerate limits. Final docs/status/link and whitespace checks are recorded
below. Working DB SHA256 remains
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Next: [D2c legacy disposition](#r1-s1-t3b-d3d2d2c). D2/D3d2d/T3/F05 remain open.

Final `.resume/Scripts/python.exe .pytest_cache/check_curation_activation_docs.py
--final`: **12 documents, 133 local links and task/parent/next-task statuses** passed.
`git -c core.safecrlf=false diff --check` passed. All required activation gates
are recorded; D2c is the exact next task. Prior edits and working data were preserved.

## <a id="r1-s1-t3b-d3d2d2c"></a>R1-S1-T3b-D3d2d2c - Legacy curation disposition and policy validation

Status: done (2026-10-05; tooling/policy validation only). Parent:
[D2](#r1-s1-t3b-d3d2d2). Prerequisite: D2b (done).

Deliver a counts-only dry-run inventory and explicit operator-selected legacy
review/removal procedure. Never infer ownership or auto-delete old data. Preserve
approved mappings until explicit disposition, and document that legacy aliases
may themselves contain personal text. Working-data application requires separate
authorization; exercise only synthetic migrated stores in this task.

Acceptance: dry-run performs no writes or raw-text disclosure; selected cleanup
is bounded, repeatable and crash-safe; unrelated rows and approved vocabulary
survive; unresolved legacy disposition remains an explicit parent-closure gap.
Review the integrated D2 policy against its recorded acceptance and carry exact
remaining risks into D3d2d3 rather than silently closing them.

Required evidence for code: focused regression/full pytest, migrated subprocess
journey, PostgreSQL/migration checks when affected, diff self-review, and honest
browser/provider limits. Link D2a/D2b evidence instead of duplicating their logs.

### <a id="r1-s1-t3b-d3d2d2c--session-contract-2026-10-05"></a>Session contract (2026-10-05)

Add an offline CLI with an explicitly supplied existing database, read-only by
default. Inventory returns fixed numeric status counts, never raw values or IDs.
A strict JSON manifest selects at most 200 legacy row IDs: remove, or map/create
with an explicit approved alias/canonical/category. Dry-run changes no files or
rows; apply claims the selected legacy rows and commits deletion plus approvals
in one transaction. Replays skip absent IDs; conflicts roll back the whole batch.
Reject nonlegacy selections, unknown fields and conflicting unrelated mappings.
No inferred owners, supplied identities/notes, automatic migration or backups.

Test migrated SQLite and PostgreSQL, competing disposition/alias writes,
rollback and retry, no disclosure/no-write failures, preserved unrelated rows
and approved normalization. Run a migrated CLI/app restart journey and the
existing D2 focused/API/browser journeys to validate the integrated policy.
Working-data disposition remains a separate authorization/closure gap.

### <a id="r1-s1-t3b-d3d2d2c--implementation-and-policy-review"></a>Implementation and policy review

CLI: `scripts/dispose_legacy_curation.py`; transaction/manifest logic:
`app.curation.legacy`; regression: `tests/test_curation_legacy.py`. No HTTP/UI
contract or migration change. The existing pure canonical/category validator is
now static and reused. [CURATION.md](../../CURATION.md#explicit-legacy-disposition-procedure)
owns operator instructions and operational limits.

Integrated A review reuses [D2a](#r1-s1-t3b-d3d2d2a) and
[D2b activation](#r1-s1-t3b-d3d2d2b2b), without repeating their logs:
raw-length/control and safe-log regressions; commit-before-capture/refused writes;
candidate/source cascades and colliding-contributor survivor snapshots; fixed
expiry/repeat lifetime and physical startup/daily purge; explicit promotion,
ignore, authenticated attribution and normalization precedence; legacy migration
compatibility and the selected cleanup/reload/retry journey. Synthetic stores
prove these mechanics, not anonymous strings or representative model quality.

Separate self-review: HEAD `5480498` plus preserved uncommitted work; reviewed
`legacy.py`, CLI, static validator change, extended activation smoke and new tests,
with the relevant capture/store/models/normalizer/routes/startup callers. Checked
every acceptance criterion, read-only enforcement, all-or-nothing deletion plus
promotion, repeated/competing selection, unique-alias and retained-legacy conflicts,
input bounds, generic errors and unrelated storage. No independent review.

Findings fixed:
- **Medium, CLI selection dispatch:** a JSON `null` manifest bypassed selection
  processing. Dispatch now depends on the supplied selection path, so invalid
  roots fail with no write/success; null/object/scalar regressions cover it.
- **Medium, CLI schema gate:** removal could otherwise reach a partly classified
  schema without both owned tables. Empty schema probes now precede disposition;
  old/partly classified schema regressions verify refusal and unchanged bytes.
- Test-only setup corrections: the existing category set excludes `tool`; the
  custom-domain fixture now uses `analytics`. Explicit short parameter IDs avoid
  Windows' 32767-character environment-variable limit for the oversized manifest.

No acceptance-blocking finding remains in this implementation review. New code
state SHA256 prefixes: legacy `E2BFC811A0C2`, CLI `5B9CEDE9A6EC`, service
`3EDFD40616CC`, smoke `9D0B34206BA7`, regression `6E0D7051EF53`.

### <a id="r1-s1-t3b-d3d2d2c--evidence"></a>Evidence

New-feature red command: `.resume/Scripts/python.exe -m pytest -q
tests/test_curation_legacy.py --tb=short`: **2 failed, 2 skipped**, specifically
missing inventory/selected-disposition assertions, not import/fixture errors.
Log: `.pytest_cache/curation-legacy-red.txt`.

Initial expanded run had **1 failed, 32 passed, 23 skipped, 4 setup/teardown
errors** from the fixture issues above; not counted as acceptance evidence.
After corrections, the added read-only/unmigrated checks passed (**4 passed,
2 skipped, 56 deselected**) before the final partial-schema cases were added.

Final leaf command: `.resume/Scripts/python.exe -m pytest -q
tests/test_curation_legacy.py --tb=short`: **39 passed, 25 skipped, 22 warnings**;
`.pytest_cache/curation-legacy-sqlite-final.txt`. Missing disposable PG and the
three PG lock-order cases explain the skips.

`.resume/Scripts/python.exe .pytest_cache/run_curation_legacy_review_postgres.py`:
fresh disposable PG **18.6**, Asia/Calcutta, migration head/base/head, then the
same leaf command with `DEE_TEST_DB_URL`: **61 passed, 3 skipped, 22 warnings**;
the three SQLite instances of PG-order tests skip. Both dialect fixtures run.
Logs: `.pytest_cache/curation-legacy-review-pg-*`; clean shutdown passed.

Integrated focused command: `.resume/Scripts/python.exe -m pytest -q
tests/test_curation_legacy.py tests/test_curation_activation.py
tests/test_curation_owned_store.py tests/test_curation_storage_migration.py
tests/test_curation_api.py tests/test_curation_service.py
tests/test_curation_input_boundary.py tests/test_profile_source_erasure.py
tests/test_migrations.py tests/test_curation_store.py tests/test_curation_overlay.py
--tb=short`: **160 passed, 99 skipped, 91 warnings**. PG-configured counterpart:
`.resume/Scripts/python.exe .pytest_cache/run_curation_legacy_postgres.py`:
**241 passed, 18 skipped, 91 warnings**, migration head/base/head and clean shutdown
passed. These collections preceded the additional schema/read-only cases; the
final leaf runs above cover all 64 cases on the reviewed state. Logs:
`.pytest_cache/curation-legacy-focused-final.txt`, `curation-legacy-pg-*`.

Application: `.resume/Scripts/python.exe scripts/smoke_curation_activation.py
--legacy-disposition`: **22/22** on final code (migrated scratch app, real CLI
process death before commit, conflict rollback, dry-run bytes, retry, normalization
reload, hidden retained history and fresh-source erasure).
`.resume/Scripts/python.exe scripts/smoke_curation_activation.py --browser`:
**28/28** real Chrome actions, network/conflict recovery, expiry/erasure, revoked
auth and no console errors. No browser contract changed after that check.

`node scripts/check_ui_bindings.js` (**425 bindings / 10 states**),
`node --check frontend/api.js`, `node --check frontend/support.js`, compilation
of changed Python and `git diff --check` passed. Existing Git LF/CRLF warnings.

Final full regression: `.resume/Scripts/python.exe -m pytest -q --tb=short`:
**2677 passed, 327 skipped, 120 warnings**, 1171.40s.
Log: `.pytest_cache/curation-legacy-full-final.txt`. Warnings retain the existing
SQLite expression-index reflection, Starlette/httpx and embedding-config
deprecations; no test failure. Logs use
`.pytest_cache/curation-legacy-*`. Chrome requires CDN access; no offline-browser,
live-provider, independent-review, CI, full-PG-suite or working-data cleanup claim.

Legacy inventory/application against working data was **not** performed. The
working DB SHA256 remains
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Unselected legacy keys, displays, notes and supplied reviewer names may retain
personal text indefinitely;
the compatibility exception and backup/physical-reclamation limits remain explicit
parent-closure gaps. D3d2d3 must carry these forward and cannot close T3/F05 on
synthetic tooling evidence alone. Physical expiry depends on maintenance and
overlay propagation depends on worker restart; response boundaries remain snapshots.

Next: [D3d2d3](#r1-s1-t3b-d3d2d3). D2 implementation/validation is complete;
D3d2d/T3/F05/R1-S1-Q remain open. Detailed D2 children are archived under the
workflow's closed-group rule, preserving IDs/status and links; the policy summary
stays in tasks.

Documentation/archive validation: `.resume/Scripts/python.exe
.pytest_cache/check_curation_legacy_docs.py` passed **16 documents, 182 local links**,
task statuses, next pointer and preserved working DB hash. Seven records moved
with inbound/outbound link updates; no evidence/ID/status loss. Final `git diff
--check` passed after archival (existing LF/CRLF warnings only).

## <a id="r1-s1-t3b-d3d2d3"></a>R1-S1-T3b-D3d2d3 - Final combined erasure validation

Status: done (2026-10-06; combined synthetic validation only).
Parent: [D3d2d](#r1-s1-t3b-d3d2d). Prerequisite: D3d2d2.

Prerequisite policy implementation/validation is done; [D2c evidence](#r1-s1-t3b-d3d2d2c)
owns final policy checks. At the time of this synthetic validation, working-data
legacy inventory had not run. [D4](#r1-s1-t3b-d3d2d4) subsequently verified an
empty actual inventory and settled the named-database row-retention gap. The
mapping below records D3-time limits; its legacy blocker is now settled, while
F05 awaits R1-S1-Q. Do not infer ownership or apply cleanup under this validation
task; carry retained legacy text, delayed physical maintenance, worker restart
and response-snapshot limits into ancestor mapping.

After aggregate-read and curation-policy remediation, map actual evidence to
the parent's combined acceptance and the D3d/D3/D/T3b/T3 contracts. Reuse the
existing leaf regressions and smoke harnesses; do not repeat the repository audit.

Required journey: migrated scratch app, both erasure doors, multiple subjects and
tenants, report/source/login/screening/derived state, fresh upload/signup, retries,
rollback and process restart. Verify the agreed curation policy and disclosure
snapshots; distinguish exact atomic cleanup from pre-delete report counts and
responses already past their final read. Use synthetic providers only.

Run full pytest and relevant SQLite/PostgreSQL HTTP/concurrency/migration gates
on the reviewed final code, plus browser checks only where a UI contract changed.
Record a separate diff self-review and every remaining finding. Close ancestors
only when all required contracts are satisfied; sprint R1-S1-Q remains a separate
task. Missing required evidence leaves this task awaiting validation.

### <a id="r1-s1-t3b-d3d2d3--session-acceptance"></a>Session acceptance

One combined migrated HTTP/restart journey seeds evaluated screening subjects
in two tenants, sources/owned curation, login sessions/challenges, interviews,
consents/audits, fingerprints and feature vectors. Both deletion routes must
preserve complete state on failed/interrupted transactions, remove the target
after retry, refuse old credentials and stale retries, and preserve survivors.
Check independent report lifetime after resume deletion and permitted fresh
upload/signup. Reuse leaf controlled interleavings for stale writes and disclosure
snapshots; characterize the pre-delete report count explicitly. Validate SQLite
and disposable PostgreSQL, migrations head/base/head, full pytest, bindings and
a separate self-review. No UI behavior change is planned; prior browser evidence
remains historical. Map supported mechanics and remaining retention/response
limits to each ancestor without closing the working-data legacy gap.

### <a id="r1-s1-t3b-d3d2d3--combined-result-and-ancestor-mapping"></a>Combined result and ancestor mapping

New validation only: `scripts/smoke_r1_s1_t3b_d3d2d3.py` reuses the existing
scratch database/login/smoke helpers. `tests/test_aggregate_erasure.py` adds
both-route insert/delete interleavings after the report-count read. No application,
schema or UI behavior changed. These characterize supported boundaries rather
than reproduce a new defect; no red/green implementation claim.

| Ancestor | Evidence mapped to its contract | Remaining limit / closure decision |
|---|---|---|
| [D3d2d](#r1-s1-t3b-d3d2d) / [D3d2](#r1-s1-t3b-d3d2) | Combined both-door rollback, actual pre/post-commit worker death, retry/restart, two tenants, survivors, source/portal refusals and owned curation; explicit report-count drift. | Legacy disposition still blocks closure. Count is pre-delete, not transaction rowcount; lost response can follow commit. |
| [D3d](#r1-s1-t3b-d3d) | Reused ingest/report/source HTTP boundaries and leaf interleavings, plus full retained-state comparisons around deletion. | Independent ingest/source/report commits and final response reads are not a whole-request lock. |
| [D3](#r1-s1-t3b-d3) | Screening completion/refusal, owned retry-input cascades, unresolved-input pause, and materialization/training/matching audit regressions. | Completed anonymous scalars/counts remain; unidentified older input is paused with its original TTL across tenants, not immediately erased. |
| [D](#r1-s1-t3b-d) | Controlled vector/ingest/fingerprint writes, wrong-owner/duplicate/error cases, skipped stale retries and preserved survivors; fresh upload/signup uses new IDs. | Consent/identity races remain R1-S2; independently committed fresh work can reappear. |
| [T3b](#r1-s1-t3b) | Controlled interview start/answer/completion and audit rollback, plus combined completed content-scored advisory interviews and derived-store cleanup. | Snapshot/delivery and retained legacy gaps propagate from D; no representative model-quality claim. |
| [T3](#r1-s1-t3) | Report/outcome stale-write regressions, defined refusals, both erasure doors, independent report lifetime after resume-only deletion and all mapped child evidence. | T3/F05 remain open for legacy disposition; R1-S1-Q stays a separate sprint task. |

[D2 policy](#r1-s1-t3b-d3d2d2) and [D2c evidence](#r1-s1-t3b-d3d2d2c)
remain the owners of retention/disposition. New raw observations follow durable
source ownership, survivor snapshots and fixed expiry; approvals keep explicit
human-selected vocabulary. No working-data inventory/disposition was run.
Delayed maintenance can extend physical retention beyond 30 days; other workers
reload overlays on restart; approval is not anonymization. No wider parent closes.
Storage-copy/backup and physical-reclamation limits remain in D2c; these checks
prove logical SQL/HTTP behavior, not forensic removal from every storage copy.

### <a id="r1-s1-t3b-d3d2d3--separate-self-review"></a>Separate self-review

Reviewed HEAD `5480498` plus preserved uncommitted login/aggregate/curation diff
and this session's smoke/characterization changes. Specification pass mapped
each ancestor above and traced both erasure routes, PortalService.erase,
CandidateStore deletion, login issuance/redemption/session ownership, report
counts, source commit/capture/exact-row checks, aggregate responses, curation
read/resolve/purge/legacy overlay, migration 0028 and screening erasure triggers.
Correctness pass checked rollback/cascade ordering, lease/retry/isolation,
recognized-error handling, private logging, maintenance/restart and HTTP limits.
The new smoke holds comparison clocks stable and uses only owned scratch stores,
capture email and NullLLM; all process exits are asserted. Same-agent self-review,
not independent review. No new application finding requiring remediation.

Findings corrected:
- **Low, validation contract**, new smoke `gone()`: the initial completed-item
  score assertion expected null and falsely rejected supported D3a scalar
  retention. It now checks the unchanged completed score; final SQLite 15/15
  verifies erasure of raw input/links while preserving that scalar.
- **Low, authorization contract**, D4 acceptance: requiring approval before
  read-only inventory would stall already-authorized investigation. D4 now
  permits read-only/reversible preparation and reserves new approval for working-
  data cleanup; final documentation checks validate that boundary/next pointer.

Review refinements: the alias SQL probe uses `norm_key`, and retained-state
snapshots include candidate credentials.
Final reviewed smoke SHA256 prefix `E768129A6CD9`; aggregate tests `2F4CA820F977`.
Application hashes are unchanged from session entry. Existing legacy retention
remains a high-severity parent finding, not a failed synthetic tooling assertion.

### <a id="r1-s1-t3b-d3d2d3--evidence"></a>Evidence

Commands/results already complete (PowerShell, project root):

| Exact command, using `.resume/Scripts/python.exe` for Python | Result |
|---|---|
| `-m pytest -q tests/test_aggregate_erasure.py --tb=short` | 30 passed, 30 skipped, 1 warning; 46.04s. Includes four new SQLite characterizations; unconfigured PG counterparts skip. |
| `-u scripts/smoke_r1_s1_t3b_d3d2d3.py` | Final SQLite 15/15; migrated scratch state, both doors and actual worker death/restart. Initial run failed only on the incorrect completed-score expectation above. |
| `-u scripts/smoke_r1_s1_t3b_d3d2b.py --aggregates` | SQLite 41/41; observed erasure refusals versus post-final-read 200 snapshots. |
| `-u scripts/smoke_r1_s1_t3b_d3d2a.py` | SQLite 29/29; report-only deletion and exact-row response boundaries. |
| `-u scripts/smoke_r1_s1_t3b_d3b2b2.py` | SQLite 17/17; interrupted unresolved ingest, conservative pause, isolated reads and permitted fresh upload. |
| `-m py_compile scripts/smoke_r1_s1_t3b_d3d2d3.py tests/test_aggregate_erasure.py` | Passed. |
| `node scripts/check_ui_bindings.js`; `node --check frontend/api.js`; `node --check frontend/support.js` | Passed; 425 bindings / 10 states. |
| `git -c core.safecrlf=false diff --check` | Passed on the reviewed state. |

SQLite focused then full command runner:
`.resume/Scripts/python.exe .pytest_cache/run_combined_erasure_sqlite.py`.
Focused SQLite: **494 passed, 327 skipped, 94 warnings**, 490.22s; missing PG
configuration and SQLite variants of PG-only lock inspections explain the skips.
Final full regression: `.resume/Scripts/python.exe -m pytest -q --tb=short`:
**2682 passed, 331 skipped, 120 warnings**, 829.09s. Existing SQLite expression-
index reflection, Starlette/httpx and embedding-config deprecations; no failures.
PG runner: `.resume/Scripts/python.exe .pytest_cache/run_combined_erasure_postgres.py`;
fresh PG 18.6, Asia/Calcutta, migration head/base/head already passed. These reuse
the existing local portable distribution; no portable setup guarantee.
PG-configured focused: **785 passed, 36 skipped, 94 warnings**, 1291.51s;
both dialect fixtures ran, with SQLite variants of PG-only cases skipped.
PG HTTP/restart commands (same interpreter, `-u` before each script):

| Script and exact arguments | Result |
|---|---|
| `scripts/smoke_r1_s1_t3b_d3d2d3.py --postgres` | 15/15 |
| `scripts/smoke_r1_s1_t3b_d3d1.py --postgres` | 36/36 |
| `scripts/smoke_r1_s1_t3b_d3d2a.py --postgres` | 29/29 |
| `scripts/smoke_r1_s1_t3b_d3d2b.py --postgres` | 29/29 |
| `scripts/smoke_r1_s1_t3b_d3d2b.py --postgres --aggregates` | 41/41 |
| `scripts/smoke_r1_s1_t3b_d3b2b2.py --postgres` | 17/17 |

PG migration head/base/head, all six journeys and clean cluster shutdown passed
(runner exit 0; `stop: exit=0`). Final hash check confirmed all 12 reviewed
source/test files unchanged after validation; working DB hash still matches
[PROGRESS.md](../PROGRESS.md). No working-data inventory/disposition ran.

The focused collection covers aggregate/report/ingest responses; report,
interview, vector, ingest and fingerprint races; materialization/training/matching
audits; screening completion/refusal/unresolved/durable/report input and tenancy;
login cleanup/issuance/redemption; source erasure; curation input/owned/activation/
legacy/storage migration and general migrations (28 files). The commands are
`-m pytest -q` followed by these exact file arguments and `--tb=short` in both
runners; full regression is exactly `-m pytest -q --tb=short`:

```text
tests/test_aggregate_erasure.py tests/test_report_erasure_concurrency.py
tests/test_report_response_erasure.py tests/test_ingest_response_erasure.py
tests/test_ingest_erasure_concurrency.py tests/test_fingerprint_erasure_concurrency.py
tests/test_feature_erasure_concurrency.py tests/test_interview_erasure_concurrency.py
tests/test_interview_erasure.py tests/test_materialization_audit_erasure.py
tests/test_training_audit_erasure.py tests/test_match_disclosure_erasure.py
tests/test_screening_erasure_concurrency.py tests/test_screening_refusal_retention.py
tests/test_screening_unresolved_input.py tests/test_screening_durable_input.py
tests/test_screening_report_input.py tests/test_screening_tenancy.py
tests/test_login_erasure_atomic.py tests/test_login_issuance_erasure.py
tests/test_login_redemption_erasure.py tests/test_profile_source_erasure.py
tests/test_curation_input_boundary.py tests/test_curation_owned_store.py
tests/test_curation_activation.py tests/test_curation_legacy.py
tests/test_curation_storage_migration.py tests/test_migrations.py
```

Local synthetic logs: `.pytest_cache/combined-erasure-*`. No browser execution
in this task: no UI
contract changed. Prior [D2c browser evidence](#r1-s1-t3b-d3d2d2c)
is historical; bindings are not browser evidence. No live-provider, independent
review, CI, full-PostgreSQL-suite, deployment or working-data cleanup claim.

Documentation check: `.resume/Scripts/python.exe
.pytest_cache/check_combined_erasure_docs.py` passed **12 documents, 144 local
links**, task/next-pointer consistency and new-file whitespace. Final
`git -c core.safecrlf=false diff --check` passed. Documentation self-review
confirmed D3 done, D4 pending, all wider ancestors/F05 open, prior work preserved
and no approval gate added to read-only preparation.

Next: [D4](#r1-s1-t3b-d3d2d4), read-only working-data inventory and concrete
disposition decision. Cleanup needs separate authorization. All wider ancestors
remain open for that gap; R1-S1-Q is not started. This task's validation is complete.

## <a id="r1-s1-t3b-d3d2d4"></a>R1-S1-T3b-D3d2d4 - Working-data legacy inventory and disposition decision

Status: done (2026-10-06; empty named-database inventory, no cleanup required).
Parent: [D3d2d](#r1-s1-t3b-d3d2d). Prerequisite:
[D3d2d3](#r1-s1-t3b-d3d2d3).

This is a distinct authorization/retention contract for the closure gap identified
by [D2 policy](#r1-s1-t3b-d3d2d2), not another implementation review or test rerun.
Option A and its tooling are already approved and validated. Standing authorization
covers read-only investigation and reversible preparation. Applying disposition
to working data was expressly excluded; "continue" alone does not authorize cleanup.

### <a id="r1-s1-t3b-d3d2d4--acceptance-and-proposed-first-step"></a>Acceptance and proposed first step

- Prepare a counts-only inventory of the explicitly named `data/veritas.db`.
  Inspect schema read-only; if the tool requires migration, take a consistent
  private disposable snapshot and migrate only that copy. Preserve original
  bytes and prior edits; report fixed counts without raw terms, notes, supplied
  reviewer names, secrets or inferred subject identities. Record commands, copy
  handling and unchanged original hash. No working-store writes/removals.
- Use that concrete inventory to record whether disposition is deferred or a
  separately reviewed selection/removal/explicit vocabulary approval is authorized.
  Before asking for cleanup approval, prepare its concrete scope/selection and
  validation contract. Document retained legacy keys, display/note/reviewer fields and the
  storage-copy/backup/physical-reclamation scope. Approval is not anonymization.
- If application is authorized, define a bounded execution child before starting
  it; require operator-selected IDs/vocabulary, preserved unrelated rows, retry/
  rollback checks, verified working-store results and appropriate copy handling.
  Do not execute that child in this decision session.
- Keep D3d2d/D3d/D3/D/T3b/T3/F05 open until the actual disposition gap is settled.
  A deferred decision or synthetic inventory does not close it; an actual empty
  inventory may settle the row-retention gap at its verified snapshot. R1-S1-Q remains
  a separate task after the development prerequisites close.

This decision task requires status/link checks and a recorded self-review. No
application regression rerun solely for documentation. If the decision requires
new tooling, split it with a distinct acceptance contract before implementation.
[CURATION.md](../../CURATION.md#explicit-legacy-disposition-procedure) owns the
operator procedure; this record owns only the working-data decision/evidence.

### <a id="r1-s1-t3b-d3d2d4--inventory-and-decision-2026-10-06"></a>Inventory and decision (2026-10-06)

Actual target: `data/veritas.db`, opened with SQLite `mode=ro` and
`PRAGMA query_only=ON`. Schema inspection found `0023_correction_pins_the_name`,
no provenance/owned tables, DELETE journaling and no WAL/SHM/journal sidecars.
The existing CLI requires 0028, so SQLite's backup API took a consistent snapshot
from a read transaction into a unique `%LOCALAPPDATA%/Temp/Veritas-D4-*` directory
outside OneDrive. Protected ACLs allowed only the current Windows user and SYSTEM.
Only that copy was upgraded through 0024-0028, using an explicit Alembic URL,
private working directory and an environment without provider/config secrets.
No application startup, working migration or `.env` read occurred.

| Fixed inventory field | Count |
|---|---:|
| Total unattributed legacy rows | 0 |
| Pending | 0 |
| Ignored | 0 |
| Resolved compatibility mappings | 0 |
| Other status | 0 |

Nonempty `norm_key`, `display_name`, `note` and `decided_by` field counts were
each zero. The copy's newly created alias/observation tables were also empty;
this does not claim the original had those tables. SQLite comparison of all
original curation columns returned zero differences; copy `quick_check` passed.
The CLI's read-only inventory left copy bytes unchanged. No raw strings, IDs,
notes, identities or inferred ownership were emitted.

**Decision: no disposition is required for this verified database snapshot.**
There are no rows to select, remove or approve; no manifest or approval request
was created and `--apply` was never used. This is actual working-data inventory,
not synthetic evidence or a deferred cleanup decision. The active curation
row-retention gap is settled at the preserved hash below. D3d2d/D3d2/D3d/D3/D/T3b/T3
can close using [D3's acceptance mapping](#r1-s1-t3b-d3d2d3) and this result.
F05 and R1-S1 remain open until the separate **R1-S1-Q** sprint review passes.
Any later nonempty inventory requires a new exact selection and authorization;
this decision supplies neither ownership nor future cleanup permission.

Scope: only the named active database was inventoried. Existing backups, exports,
other databases and OneDrive/version history were not discovered, inspected or
removed; there is no zero-retention claim for them. The generated copy and its
empty directory were removed after validating their exact absolute target and
expected contents, without recursive deletion. No generated database remains.
That file removal is not secure-media or physical storage reclamation evidence.
No working bytes, other user data, scheduler or runtime behavior changed.

### <a id="r1-s1-t3b-d3d2d4--commands-preservation-and-self-review"></a>Commands, preservation and self-review

- Read-only schema probe: PowerShell literal Python stdin executed with
  `.resume/Scripts/python.exe -`; fixed result saved to
  `.pytest_cache/d4-readonly-schema.json`.
- Investigation: `.resume/Scripts/python.exe .pytest_cache/d4_inventory_working.py`
  passed consistent-copy/migration, counts-only CLI, integrity, column comparison,
  unchanged-copy and unchanged-original assertions. It invokes
  `scripts/dispose_legacy_curation.py --database <private-copy>` without selection
  or apply. Counts-only result: `.pytest_cache/d4-inventory-counts.json`.
- Copy handling: native PowerShell `Set-Acl`/`Get-Acl` verified the restricted ACL;
  validated `Remove-Item -LiteralPath` removed only the generated file and empty
  directory. Both preparation and removal succeeded.

Original SHA256 before inspection, after copying/migration/inventory and after
copy removal:
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B`.
Original revision remains 0023; no SQLite sidecars appeared.

Separate self-review: HEAD `5480498` plus preserved prior uncommitted work and
this session's documentation/link moves. Specification pass checked the actual
target/counts, authorization boundary, copy handling, parent acceptance mapping
and next sprint prerequisite. Correctness pass inspected the temporary helper,
CLI schema/read-only gates and migrations 0024-0028; all original reads were
read-only, migration targeted only the private copy, and output was restricted
to fixed counts/metadata. Reviewed the final session diff and archival link/status
checks; no acceptance-blocking finding remains. Same-agent review, not independent.

Documentation/preservation checks are recorded below. No tracked application,
test, script or migration code changed; no pytest, API/browser, PostgreSQL or
live-provider rerun was needed or claimed for this inventory/documentation task.
Earlier application validation remains in D3/D2 evidence. Stop here; next task
is R1-S1-Q, not another development task.

Final checks: `.resume/Scripts/python.exe .pytest_cache/check_d4_inventory_docs.py`
passed **63 documents / 353 local links**, the done-development/pending-sprint
prerequisites, preserved IDs/prose for **9 archived records**, and unchanged
hashes for **622 existing non-Markdown files**, including the working database.
It also rechecked original schema/zero rows read-only and absence of the generated
copy. Session diff: `.pytest_cache/d4-session-doc-diff.txt`; **27 documents**
changed/moved. `git diff --check` passed (existing LF/CRLF notices only).
The first docs-check invocation rejected pre-existing roadmap trailing spaces;
the check now rejects newly introduced whitespace while preserving historical
text. No product or data finding arose from that checker correction.

## <a id="r1-s1-t3b-i"></a>R1-S1-T3b-I - Defined interview refusals during erasure

Status: done. Parent: [T3b](#r1-s1-t3b). Date: 2026-09-21.

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

## <a id="r1-s2-q"></a>R1-S2-Q — Integrated current authorization and identity review

Status: done (2026-10-09; bounded sprint acceptance). PI/sprint: R1/R1-S2. Audit: F01/F04
residuals, F06 current-system gate, F09 concurrency only.
Prerequisites: [T1](#r1-s2-t1), [T2](#r1-s2-t2), [T3](#r1-s2-t3),
[T4](#r1-s2-t4); all done. [Workflow](WORKFLOW.md) owns gates.

### <a id="r1-s2-q--bounded-acceptance"></a>Bounded acceptance

| ID | Observable criterion | Evidence/result |
|---|---|---|
| AC1 | The same active snapshots/labels lose gated serving/filter/export/training access after revoke/expiry at an earlier cut; first-party values and a permitted survivor remain usable. | Passed: combined HTTP/library journey, serving/join regressions, CSV and actual/absent Parquet. |
| AC2 | Candidate and org grants, jobs, reports and contact challenges remain isolated; cached labels cannot authorize a foreign org. | Passed: two principals/orgs, API denials and scoped library calls; T4B report ownership. |
| AC3 | Exact login/contact OTPs remain single-use and owned; asserted contacts cannot move proved login subjects or infer legacy proof. | Passed: T3/T4, all-plane validity regressions, competing SQLite/PG connections and migrated identity journeys. |
| AC4 | Erasure invalidates queued proof, cookie/key, derived snapshots/labels and contact outcomes across restart while preserving the other subject. | Passed: Q restart, cached export/join rejection, erasure regressions and survivor credentials. |
| AC5 | Reviewed final state passes full pytest, required PG/migration checks, bindings and preservation/docs checks. | Passed: commands below, separate self-review, reviewed hashes and unchanged working DB/prior work. |

Use current app composition, synthetic/capture/null providers and migrated
scratch SQLite/PostgreSQL only. Existing login/change/merge refusal and human
review contracts stand. No application/UI contract change is planned; browser
applies if one changes. No live delivery, model-quality, independent-review,
working migration/repair, review-flag clearing or cleanup claim.

Source scope: features serving/export/training, matching boundary, auth
redemption/store, candidate binding/ingest/erasure, verification challenges,
their API callers and migration 0029. Extend a bounded integrated smoke using
the existing harness; retain the meaningful T1–T4 regressions. A review task
needs no invented defect/red run if no implementation finding occurs.

### <a id="r1-s2-q--execution-and-review"></a>Execution and review

- Initial combined migrated SQLite HTTP/library/restart journey: 33/33.
  Initial harness syntax error was corrected before that run; not defect evidence.
- Review finding (high): auth consumption validated ID/digest but omitted current
  expiry/attempt predicates. A committed exhaustion/expiry after preflight still
  created a proved candidate/session. Valid reproducer: project Python via
  `.pytest_cache/run_r1_s2_q.py validity-red -m pytest
  tests/test_login_redemption_validity.py -k committed -q --tb=short`:
  **2 failed, 2 skipped, 2 deselected, 1 warning**, 3.12s; both failures were
  missing `ChallengeRefused`, with a candidate/session actually created.
- Fix: reload/lock the exact challenge, sample production time after both lock
  waits and atomically predicate consumption on current expiry/budget. All
  planes share it; invalid requests retain `400 invalid_code`, no binding/session.
  Explicit test clocks remain supported. No migration or UI shape change.
  Regressions include all planes, actual competing commit/rollback transactions,
  expiry after both lock waits and legitimate rollback success.
- Reviewed state starts at HEAD `5480498` plus the preserved prerequisite work,
  Q's auth service/store/route fix, auth-store caller tests, new validity tests and
  integrated smoke. Separate review and required gates below are complete.

### <a id="r1-s2-q--final-state-validation"></a>Final-state validation

All Python commands use `.resume/Scripts/python.exe`. Session-only runners strip
inherited DEE settings, disable external providers and never select working data.
Logs/runners below are ignored local evidence, not portable setup guarantees;
permanent regressions and the new integrated smoke remain in the repository.

- `.pytest_cache/run_r1_s2_q.py auth-reviewed -m pytest
  tests/test_login_redemption_validity.py tests/test_auth_service.py
  tests/test_auth_store.py tests/test_auth_api.py -q --tb=short`:
  **111 passed, 12 skipped, 1 warning**, 21.73s. Includes both locked clock cuts,
  three planes, commit/rollback, generic API refusal/no cookie and valid flows.
- `.pytest_cache/run_r1_s2_q_selected.py` invokes `-m pytest` on the 33 selected
  consent/serving/matching, contact/auth/binding/ingest, erasure/rights/migration
  files with `-q --tb=short`: **501 passed, 166 skipped, 19 warnings**, 307.00s
  (runner 314.25s). PostgreSQL-only cases skipped without DEE_TEST_DB_URL;
  actual PyArrow **25.0.1** from the existing ignored scratch target was enabled.
- `.pytest_cache/run_r1_s2_q_arrow.py journey-reviewed -u
  scripts/smoke_r1_s2_q.py`: **33/33**, 41.69s. Migrated SQLite startup, HTTP
  serving/identity/consent/OTP/erasure, direct feature/training CSV and actual
  Parquet, two restarts and survivor preservation on the final auth fix.
- `.pytest_cache/run_r1_s2_q.py sqlite-migrations
  .pytest_cache/migrate_r1_s2_t4a_sqlite.py`: head/base/head passed, 7.14s;
  `.pytest_cache/run_r1_s2_q_postgres.py` migration up/down/up also passed.
  Seeded 0029 legacy compatibility/uniqueness checks are in the selected suites.
- `node scripts/check_ui_bindings.js`: **425 bindings / 10 states**, passed.
  `-m compileall -q src/app/auth src/app/api/routes.py
  tests/test_login_redemption_validity.py scripts/smoke_r1_s2_q.py` passed.
  `.pytest_cache/check_r1_s2_q.py`: reviewed hashes, unrelated prior work,
  unchanged working DB SHA256 and `git diff --check` passed.
- `.pytest_cache/run_r1_s2_q.py full` invokes `.resume/Scripts/python.exe -m
  pytest -q --tb=short`: **2852 passed, 476 skipped, 113 warnings**, 969.52s
  (runner 980.15s), exit 0 on the reviewed production code. Skips include
  unconfigured PG and optional Parquet. During the run only the skipped PG-only
  test caller was adapted; production code stayed unchanged. That entire file
  was rerun afterward: `.pytest_cache/run_r1_s2_q.py atomic-caller -m pytest
  tests/test_login_erasure_atomic.py -q --tb=short`: **8 passed, 8 skipped,
  1 warning**, 13.98s; PG cases executed in the recheck below.
- Broad configured `.pytest_cache/run_r1_s2_q_postgres.py`: **662 passed,
  2 failed, 3 skipped, 19 warnings**, 954.92s. Both failures were the PG-only
  caller's unset start event after its omitted time argument, not production
  assertion failures. `.pytest_cache/run_r1_s2_q_postgres.py --recheck` reran
  `test_login_erasure_atomic.py` and `test_login_redemption_validity.py`:
  **38 passed, 2 skipped, 1 warning**, 64.07s; both prior failing variants now
  observe actual PG blocking and commit/rollback outcomes. Other broad-run
  assertions remain applicable to the unchanged code. No full PG-suite claim.
- Recheck's migrated PG HTTP/library/restart journeys: Q **33/33** (56.18s),
  T1 **22/22** (21.41s), T2 **25/25** (23.57s), T3 **19/19** (22.18s),
  T4A **15/15** (21.55s), T4B **16/16** (24.05s), each exit 0. PG **18.6**,
  Asia/Calcutta, read committed; fresh-cluster up/down/up passed again (6.37s).
  Both owned clusters stopped successfully (22.97s / 13.34s).
- Final core `.pytest_cache/run_r1_s2_q.py journey-final -u
  scripts/smoke_r1_s2_q.py`: **33/33**, 37.90s, including optional Parquet
  unavailability without artifacts. Arrow-enabled runs above prove actual format.
  `.pytest_cache/check_r1_s2_q.py --docs` checks final hashes/preservation,
  links, task/PI status and next pointer. Logs use `r1-s2-q-*` prefixes;
  PG final journey logs use `r1-s2-q-pg-recheck-journey-*`.
  Warnings are existing Starlette/httpx and SQLAlchemy/Alembic reflection/deprecation
  warnings. No dependency change or working migration occurred.

### <a id="r1-s2-q--separate-diff-self-review"></a>Separate diff self-review

Specification pass: traced T1–T4's serving, library export/join, scoped matching,
exact redemption/contact challenges, protected ingest and erasure callers.
The integrated smoke uses the same two subjects/cached inputs through revocation,
expiry and two restarts; T4A/B preserve conflict, review and upload/refusal coverage.
Matching currently ranks first-party terms; its existing direct-store regression
extends the real compiler to prove gated filters/scores without claiming a shipped
gated requisition. Historical/raw values remain unchanged by authorization reads.

Correctness pass after the fix: reviewed the auth service/store and route delta,
callers, all three planes, CSRF/generic failures, ID/digest/budget/expiry predicates,
address → challenge → candidate lock order, rollback and erasure races; reviewed
migration 0029's seeded compatibility tests and no inferred proof. CSV iterator
and buffered Parquet rechecks, missing grants, org scopes, label joins, fallback,
advisory behavior and direct label-source callers remain covered by prerequisite
regressions. No acceptance-blocking finding remains in this reviewed scope.

Reviewed source/test/journey hashes are recorded in ignored
`.pytest_cache/r1-s2-q-reviewed.json`. Review is same-agent **self-review**, not
independent review. One earlier single-use test mocked the store read with an
obsolete one-argument lambda; it now injects the stale preflight at `_live_scopes`
and keeps the real locked reread. Its TypeError was a test adaptation failure,
not defect reproduction. PostgreSQL additionally found the old direct consumer
function reference in `test_login_erasure_atomic.py` omitted the new explicit
time argument (two PG-only variants). Adapted that caller and reviewed it;
production code is unchanged. Its entire file and the new validity regressions
passed the affected SQLite/PG reruns, with all six migrated PG journeys on a
fresh disposable cluster. No acceptance-blocking finding remains.

### <a id="r1-s2-q--handoff"></a>Handoff

Q, R1-S2 and PI-R1 are done within this bounded current-system scope. F01/F04's
scheduled residual gate and F06's current-system gate close; F05/F06 future media
remains R5-S1-T4, and F09 delivery/workflow remains R3-S1-T2. Authorization/response
reads remain snapshots, not locks across delivery/model use; delivered artifacts
cannot be recalled. Contact/login changes and merges still explicitly refuse.
The unchanged working DB at 0023 has unknown historical proof needing explicit
review. No working migration/repair, review-flag clearing or user-data cleanup.

No browser gate applies to unchanged screens/handlers/UI response contracts.
Capture/null providers prove mechanics only; no live delivery, independent
review, CI, deployment or representative scoring-quality claim. Prior work and
working DB bytes are preserved. Next: **R2-S1-T1 — Validate model response
structures**; not started. Complete only Q and stop.

## <a id="r1-s2-t1"></a>R1-S2-T1 — Apply current consent to serving

Status: done (2026-10-06). Audit: F06; R1-S2/PI-R1 remain open.
Prerequisite: [R1-S1-Q](#r1-s1-q).

### <a id="r1-s2-t1--acceptance-contract"></a>Acceptance contract

- After active-consent materialization, revocation or expiry must exclude gated
  values from search filters, normalization pools, scores and contributions even
  when the caller requests an earlier `as_of`. Ungated values remain usable.
- Search is an authenticated platform-admin operation without an organization
  parameter: it requires any **current ledger_read** grant, consistent with the
  existing platform materialization basis. JobStore must require current
  ledger_read for the requesting organization (or a wildcard grant), including
  direct callers and the dashboard's matching path.
- Check each candidate separately; another candidate's grant, another purpose,
  future grants and another organization's grant cannot authorize scoped use.
  Mask before the pure filter/ranking engines; never use cached consent.allowed.
- Preserve raw historical vectors, materialization consent and timestamps.
  Present permission cannot fill historically withheld values. Existing job
  ranking uses only first-party/synthetic terms; preserve its results and audits.
- Consent-read failures must propagate without serving cached gated values.
  Authorization is a current read snapshot, not a lock across response delivery.

Exports/training and invalidation/re-materialization policy belong to T2. No
schema, frontend or API shape changes are planned. No browser gate is required
unless implementation changes a visible screen, handler or UI contract.

### <a id="r1-s2-t1--required-evidence"></a>Required evidence

Behavioral red/green search regression; materialization round-trip and direct
JobStore/policy tests with two candidates/orgs; controlled revoke after vector
read; focused and full pytest; migrated scratch HTTP/startup/restart journey
with offline providers; targeted SQLite/PostgreSQL consent/erasure checks;
separate recorded diff self-review and preservation checks. No independent
review, live-provider or empirical scoring-quality claim.

### <a id="r1-s2-t1--execution-evidence"></a>Execution evidence

- Added `features.serving.current_consent_vectors` at search and direct JobStore
  boundaries. It uses existing grant reads/pure consent rules and masks copies
  before pure engines. All registered gated versions protect a stored name
  because historical vectors lack member-version metadata. Store/clock failures
  propagate; no migration or API/frontend shape change.
- Reproducer: `python -m pytest tests/test_talent_search_api.py -k historical_search
  -q --tb=short` using project Python: **4 failed, 9 deselected, 1 warning**,
  9.37s before the fix. Each denial still scored 0.707777… instead of the
  first-party-only 0.133333…. Initial enum/range fixture mistakes were corrected
  before this valid red run; they are not defect evidence.
- Focused interim: **65 passed, 24 skipped, 1 warning**, 33.16s. Tests cover
  normalization-pool exclusion, exists/missing/comparison filters, explanations,
  current purpose/scope/wildcards, expiry at the read, historical preservation,
  consent-store failure and a competing-connection revoke after vector loading.
  The JobStore probe extends the real pure compiler with a gated term/filter in
  tests to observe the boundary; shipped requisition ranking remains first-party.
- Scratch SQLite app HTTP/restart journey: **22/22** checks passed; actual
  migration/startup and two orgs/candidates. Expiry ages only a scratch grant
  after active materialization; no arbitrary wait or working-store mutation.
- Separate self-review against HEAD `5480498` plus the eight task code/test/smoke
  files and the session-only route diff: checked acceptance, both callers,
  org/purpose scope, pre-normalization masking, error propagation, version
  compatibility, immutable historical evidence and existing erasure/audit
  retries. Low finding: `FEATURES.md` promised withholding could never lower
  rank; removing a high-valued term or changing its pool can change rank. Replaced
  that promise with the actual dropped-term/no-penalty behavior, demonstrated by
  the score/pool regression. No acceptance-blocking findings remain. Authorization may change
  after its read; no atomic delivery/revocation guarantee or independent review.
  Source diff/hashes are ignored local artifacts (`r1-s2-t1-source.diff`,
  `r1-s2-t1-reviewed-code.json`). No underlying SQL/schema changes.
- Bindings: **425 / 10 states**, passed. No browser execution required or claimed.
  Normal `git diff --check` passed. A check with autocrlf disabled falsely treated
  pre-existing CRLF lines as whitespace; the normal repository configuration was
  then used successfully. Prior source changes and the working DB remain intact.

### <a id="r1-s2-t1--final-validation"></a>Final validation

Project Python was used for every command; runners strip inherited DEE settings
and use synthetic stores/refusing providers. Ignored runners/logs are local
conveniences, not portable setup guarantees.

- `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t1_postgres.py`:
  PostgreSQL **18.6**, Asia/Calcutta session timezone, disposable owned cluster.
  Alembic **head/base/head** passed. Focused final-code run below:
  **134 passed, 2 skipped, 1 warning**, 187.13s (runner 192.60s).
  `scripts/smoke_r1_s2_t1.py --postgres`: **22/22**, 19.43s. Shutdown passed.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t1_sqlite.py`:
  `scripts/smoke_r1_s2_t1.py` on migrated scratch SQLite: **22/22**, 21.03s.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t1_full.py`:
  `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2706 passed,
  339 skipped, 110 warnings**, 564.08s (runner 573.55s), exit 0.
- PG focused child command: `.resume/Scripts/python.exe -m pytest
  tests/test_feature_serving_consent.py tests/test_talent_search_api.py
  tests/test_job_store_match.py tests/test_features_materialize.py
  tests/test_match_disclosure_erasure.py tests/test_feature_erasure_concurrency.py
  tests/test_materialization_audit_erasure.py tests/test_feature_store.py
  -q --tb=short`. This is a mixed-dialect selection: only configured database
  fixtures run PostgreSQL; ordinary TestClient/unit fixtures stay SQLite.
- Local runner startup errors (BOM decoding and a mistyped test filename) were
  corrected before successful validation. The failed filename selection ran no
  tests and stopped its cluster. Preservation checker also corrected its
  treatment of already-deleted tracked paths; these are harness corrections,
  not application defect evidence.

Final preservation: `check_r1_s2_t1_preservation.py` verifies unchanged reviewed
code, original working DB SHA256, prior files outside the task allowlist and
`git diff --check`. `check_r1_s2_t1_docs.py` passed local links, task/PI status,
roadmap entry and the next pointer; T2 remains pending and unstarted.
No working migration, data cleanup, publish/deployment or
external message. No browser, independent review, CI or live-provider claim.
Current grant reads are snapshots; one read per candidate with gated fields is
not a throughput benchmark. Raw export/training consumers still await T2.

Next: **R1-S2-T2 — Apply current consent to exports and training**. Not started.

## <a id="r1-s2-t2"></a>R1-S2-T2 — Apply current consent to exports and training

Status: done (2026-10-08). Audit: F06; R1-S2/PI-R1 remain open.
Prerequisite: [T1 policy/evidence](#r1-s2-t1).

### <a id="r1-s2-t2--acceptance-contract"></a>Acceptance contract

- CSV and optional Parquet feature/training writers require an explicit ledger
  store and registry; check current ledger_read after consuming each input row.
  Platform use requires any active grant; an explicit org requires that org or
  a wildcard. Another candidate/purpose, future, revoked or expired grants fail.
- Training joins require both the historical materialization permission and
  current permission. Denied outcomes are not fetched; gated features and every
  label value (including coding, event time and lag) are withheld. Cached labels
  are checked again on export; audit=False does not bypass authorization.
- Recheck after outcome reads and before returning the assembled set. The
  metrics LedgerLabelSource must obey the same present and historical bounds.
  Errors propagate; erased subjects remain omitted.
- Historical vectors, cached decisions and timestamps are preserved. Revocation
  invalidates present use via read-time masking, not destructive snapshot edits.
  Re-materialization still records consent at its cut; a new grant cannot fill
  withheld cuts/labels. Regenerate exports/training after authorization changes;
  already delivered files and trained models cannot be recalled by this change.
- Preserve column/null/dtype behavior, leakage-free strict-after labels,
  first-party values, and ParquetUnavailable without consuming inputs when the
  optional dependency is missing. No API/frontend/schema change.

### <a id="r1-s2-t2--required-evidence"></a>Required evidence

Behavioral red/green export and training regressions; two candidates/orgs,
revocation/expiry/purpose/scope, historical preservation, cached labels,
iterator/outcome timing, failure and erasure paths; focused/full pytest;
migrated scratch HTTP materialize/revoke plus direct exports/training/restart;
targeted SQLite/PostgreSQL competing reads; bindings; separate diff self-review
and preservation checks. No browser gate applies to unchanged UI contracts.
No independent review, live-provider or empirical-quality claim.

### <a id="r1-s2-t2--implementation-and-review"></a>Implementation and review

- Reproducer: `.resume/Scripts/python.exe -m pytest
  tests/test_features_current_consent.py -q --tb=short`: **2 failed, 2 skipped**,
  5.29s before the fix. CSV returned revoked reputation `0.9`; training read
  both subjects' outcomes instead of only the authorized survivor. Fixture
  collection mistakes later corrected are not defect reproduction evidence.
- Shared `current_consent` and copy masking in `features.serving` now serve
  exports, training and metrics labels. Writers require store/registry arguments;
  all repository callers were updated. The pure label reducer is unchanged;
  pure example assembly requires an explicit boundary decision. No SQL/schema,
  API/frontend, scorer or working-data changes.
- Separate self-review against HEAD `5480498` plus the task's uncommitted code,
  tests and four smoke files: checked all writers/direct callers, pre/post-read
  and iterator timing, historical ceilings, org/purpose isolation, optional
  dependency behavior, label field coverage, audit/error paths and prior erasure.
  Medium finding in `features/training.py:current_training_example` and the
  feature writer loops in `features/export.py`: an existence read before the
  new consent read could return a cached subject erased during that later read.
  Moved existence after consent; `test_erasure_during_final_consent_read_is_omitted`
  covers all writers and training. The metrics source
  also omits the specific missing-subject historical audit failure and erasure
  during its final consent read. No acceptance-blocking findings remain.
  Same-agent self-review only; source diff/hashes are ignored local artifacts.
- Interim focused run: **91 passed, 113 skipped**, 215.39s, before the final
  erasure-order review correction. Initial compatibility run had **3 failed,
  50 passed, 29 skipped** due to synthetic exporter IDs lacking candidate rows;
  fixed the fixture. One earlier collection error was a duplicate registry
  keyword in the caller-update harness; no tests ran in that attempt.
- First HTTP journey passed consent checks but its redundant restart `/health`
  probe returned 404. Removed it; the shared server context already requires
  real `/healthz` readiness. This is a harness correction, not an application fix.

### <a id="r1-s2-t2--final-validation-and-handoff"></a>Final validation and handoff

All commands used project Python and isolated synthetic stores/refusing providers.
PyArrow **25.0.1** was installed only to ignored `.pytest_cache/r1-s2-t2-arrow`
and added to selected runners' PYTHONPATH; core dependencies remain unchanged.
Install command: `.resume/Scripts/python.exe -m pip install --only-binary=:all: --target .pytest_cache/r1-s2-t2-arrow pyarrow`.

- `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t2_postgres.py`:
  PostgreSQL **18.6**, Asia/Calcutta timezone, fresh owned disposable cluster;
  Alembic **head/base/head** passed. Final-code focused suite: **215 passed,
  1 skipped**, 304.40s (child runner 310.40s); mixed-dialect fixtures run SQLite
  and PostgreSQL, ordinary unit fixtures stay SQLite. HTTP/restart journey
  `scripts/smoke_r1_s2_t2.py --postgres`: **25/25**, 34.48s. Shutdown passed.
- Focused child command: `.resume/Scripts/python.exe -m pytest
  tests/test_features_current_consent.py tests/test_features_export.py
  tests/test_features_build_training_set.py tests/test_features_training_export.py
  tests/test_training_audit_erasure.py tests/test_feature_serving_consent.py
  tests/test_signal_quality_labels.py -q --tb=short`.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t2.py sqlite-final-arrow
  -u scripts/smoke_r1_s2_t2.py`: final-code SQLite **25/25**, 20.93s;
  real HTTP setup/materialization/revocation/restart and direct library consumers.
  `check_r1_s2_t2_sqlite_migration.py` verifies scratch Alembic head
  `0028_owned_curation`; its initial short-ID expectation was corrected to read
  the actual migration head. Both dialects exercise actual Parquet output.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t2.py
  review-regressions-arrow -m pytest tests/test_features_current_consent.py
  tests/test_signal_quality_labels.py -k 'erasure_during_final or
  omits_erasure_during_join' -q --tb=short`: **7 passed, 5 skipped,
  142 deselected**, 8.88s; the PG focused run covers the skipped dialect too.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t2.py full` runs
  `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2752 passed,
  432 skipped, 110 warnings**, 1149.36s (runner 1161.93s), exit 0 on the final
  reviewed code. Full-suite PostgreSQL/optional-format skips are complemented by
  the targeted configured run above; no full PostgreSQL-suite claim. Warnings
  include existing SQLAlchemy expression-index reflection/deprecation warnings.
- `node scripts/check_ui_bindings.js`: **425 bindings / 10 states**, passed.
  Python compilation and `git diff --check` passed. No browser execution applies
  to unchanged UI contracts; none is claimed.
- Compilation command: `.resume/Scripts/python.exe -m compileall -q src/app/features/export.py src/app/features/training.py src/app/features/serving.py src/app/features/training_schema.py src/app/signal_quality/labels.py scripts/smoke_s42.py scripts/smoke_s44.py scripts/smoke_r1_s1_t3b_d3c2.py scripts/smoke_r1_s2_t2.py`.

Final `check_r1_s2_t2_preservation.py` checks the recorded reviewed-code hashes,
original working DB SHA256, unchanged prior files outside the task allowlist and
`git diff --check`. `check_r1_s2_t2_docs.py` checks links, task/PI status, roadmap
entry and next pointer. These session runners/artifacts are local ignored tooling,
not portable setup guarantees; permanent regressions and journey are in the repo.

Acceptance gates complete. Current checks remain per-subject read snapshots;
permission can change after a check or an earlier CSV row is serialized. An
allowed audit can precede later denial. Cached/delivered files and trained models
are not recalled; consumers must regenerate/revalidate use. No working migration,
data cleanup, deployment, external message, browser, independent review, CI,
live-provider or representative model-quality claim. Prior work/data preserved.

Next: **R1-S2-T3 — Close contact-verification attempt races**. Not started.

## <a id="r1-s2-t3"></a>R1-S2-T3 — Close contact-verification attempt races

Status: done (2026-10-08). Audit: F09/F04 residual; R1-S2/PI-R1 stay open.
Prerequisite: [T2](#r1-s2-t2).

### <a id="r1-s2-t3--acceptance-contract"></a>Acceptance contract

- Serialize challenge issuance and confirmation for the same candidate in the
  database. Concurrent wrong guesses charge distinct attempts; exhaustion fails
  once, removes the secret and audits once. Correct codes cannot bypass a stored
  exhausted budget, expiry, consumed state or a superseded challenge.
- Exactly one correct confirmation succeeds and writes one completion audit.
  Later/repeated confirmation fails with ChallengeError (HTTP 400), without
  extending outcome expiry or changing its completion time. This is single use,
  not an idempotent repeated-success response.
- Concurrent issuance honors candidate/channel cooldown and replaces old secrets
  atomically. Confirmation and resend have a defined transaction order: whichever
  acquires the candidate lock first acts on current state; stale secrets cannot
  verify the replacement. Other candidates/channels remain isolated.
- Re-read verification/challenge state and default current time after lock wait.
  Preserve explicit test clocks, destination binding, candidate ownership,
  atomic audit/outcome writes, erasure cascades, advisory assurance and login OTP.
  Refuse issuing into terminal or non-challenge/mismatched-channel rows.
- No schema, login, identity-binding, API shape or frontend change. Use existing
  candidate rows as the lock target (PG row lock; SQLite first no-op write with
  unchanged updated_at), rather than new scope tables. Phone delivery remains
  unavailable through NullNotifier; synthetic/capture evidence proves mechanics.

### <a id="r1-s2-t3--required-evidence"></a>Required evidence

Behavioral red/green lost-increment and exhaustion regressions; controlled
SQLite/PostgreSQL competing transactions for failures, success, resend/cooldown,
expiry while waiting, rollback and erasure; service/API ownership and retries;
migrated scratch HTTP/restart journey with refusing/capture providers; final full
pytest, bindings, separate diff self-review and preservation/documentation checks.
No browser gate applies unless a visible UI contract changes. No independent
review, live delivery, CI or model-quality claim.

### <a id="r1-s2-t3--evidence-and-handoff"></a>Evidence and handoff

Implemented candidate locking in `VerificationStore` for issuance, confirmation
and trusted completion. SQLite's first write preserves `updated_at`; PostgreSQL
locks the candidate row and then fetches current verification/challenge state.
Single-use status/budget/consumed/channel guards and legacy ambiguity refusal
prevent stale success. Outcome, secret deletion and completion audit stay atomic.
`VerificationService.start` forwards only an explicit clock to challenge issuance.
No schema, API shape, frontend or login change; NullNotifier sends nothing.

Behavioral reproduction (project Python through ignored safe environment runner):
- `red -m pytest tests/test_verification_concurrency.py -q --tb=short`:
  **3 failed, 3 skipped**, 4.31s. Two wrong guesses persisted one attempt; both
  correct requests succeeded; an already exhausted budget accepted its code.
- `legacy-red -m pytest tests/test_verification_concurrency.py -k legacy_competing
  -q --tb=short`: **1 failed, 1 skipped, 24 deselected**, 2.62s. A legacy competing
  code could still confirm before the ambiguity guard.
- `clock-red -m pytest tests/test_verification_service.py -k issuance_uses_store_clock
  -q --tb=short`: **1 failed, 1 passed, 18 deselected**, 3.50s. Default service
  issuance supplied a pre-lock time; explicit injection correctly stayed fixed.
- Initial focused attempt collected nothing (two guessed filenames did not exist).
  Corrected selection: **1 failed, 119 passed, 20 skipped**, 52.12s; the capture
  notifier used the wrong method signature. Corrected the test to the real seam.
  These are harness errors, not additional application reproductions.

Separate self-review against HEAD `5480498` plus this task's uncommitted
`store.py`, `service.py`, three existing test diffs, new concurrency tests and
`smoke_r1_s2_t3.py`:
- Specification: checked lock order, remaining-budget and single-use semantics,
  post-lock clocks, candidate/channel supersession, ownership/destination guards,
  audit atomicity, erasure cascades and honest delivery claims against each
  acceptance criterion. Controlled regressions cover both race orderings.
- Correctness/maintenance: inspected every production challenge caller and
  trusted completion caller, SQL predicates/isolation, model FK deletion and
  candidate timestamp defaults, existing login locks and API error mapping.
  Candidate locks do not acquire login locks, avoiding an inverted lock order.
- Medium findings resolved: historical competing challenge rows could verify
  (`store.py:confirm_challenge`) and default service clocks bypassed the post-wait
  sample (`service.py:start`). Each has the behavioral failure above and a fix.
  No acceptance-blocking findings remain. Same-agent self-review, not independent
  review; final reviewed source hashes are retained in ignored local evidence.

### <a id="r1-s2-t3--validation-record"></a>Validation record

Commands below use `.resume/Scripts/python.exe` and isolated synthetic stores.
The ignored `.pytest_cache/run_r1_s2_t3.py <name> ...` wrapper strips inherited
DEE settings and pins refusing providers; its full mode runs `-m pytest -q --tb=short`.

- Before the final service-clock correction, focused store/service/API/erasure/
  login selection: **121 passed, 21 skipped**, 1 warning, 5473.39s. Earlier
  original-reproducer green run: **44 passed, 3 skipped**, 1 warning, 22.70s.
- Final service/API command: `run_r1_s2_t3.py service-final -m pytest
  tests/test_verification_service.py tests/test_verification_api.py -q --tb=short`:
  **34 passed**, 1 warning, 11.21s. Warning is existing Starlette/httpx deprecation.
- `run_r1_s2_t3.py sqlite-final -u scripts/smoke_r1_s2_t3.py`: **19/19**, 50.62s,
  actual migrated startup, wrong/foreign/replay refusal, supersession/cooldown,
  exhausted/expired correct-code refusal, consent/org scope, restart and erasure
  with a surviving second candidate. `check_r1_s2_t3_sqlite_migration.py` read-only
  confirms scratch head `0028_owned_curation`.
- Interim `run_r1_s2_t3_postgres.py`: PostgreSQL **18.6**, Asia/Calcutta, fresh
  owned disposable cluster; Alembic **head/base/head** passed. Focused **175 passed,
  2 skipped**, 1 warning, 4845.10s; predates the service-clock review fix/two new
  clock cases. HTTP/restart **19/19**, 36.84s, on final service code; shutdown
  passed. Final-code PostgreSQL rerun below supersedes that focused result.
- Final `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t3_postgres.py --final`:
  fresh owned PostgreSQL **18.6**, Asia/Calcutta, **read committed** default;
  Alembic **head/base/head** passed. **177 passed, 2 skipped**, 1 warning, 261.41s
  (runner 269.55s). SQLite/PostgreSQL parameterized cases use both dialects;
  configured store/service/API fixtures also use PostgreSQL. Two skips are SQLite
  variants of PostgreSQL-only login lock inspection; that PG evidence ran.
  Final-code HTTP/restart `scripts/smoke_r1_s2_t3.py --postgres`: **19/19**, 20.67s;
  shutdown passed. The permanent concurrency suite observes `pg_blocking_pids`
  before releasing each contending transaction, rather than inferring locking
  from sequential successes or SQLite's SQL-entry scheduling.
- Final PG child command: `.resume/Scripts/python.exe -m pytest
  tests/test_verification_concurrency.py tests/test_verification_store.py
  tests/test_verification_service.py tests/test_verification_api.py
  tests/test_verification_erasure.py tests/test_verification_org_api.py
  tests/test_verification_consent.py tests/test_auth_challenges.py
  tests/test_login_erasure_atomic.py tests/test_login_redemption_erasure.py
  -q --tb=short`.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t3.py full` runs
  `.resume/Scripts/python.exe -m pytest -q --tb=short`: **2782 passed, 445 skipped,
  110 warnings**, 1011.82s (runner 1022.86s), exit 0 on the reviewed final code.
  Skipped PostgreSQL cases are complemented by the selected configured run above;
  no full PostgreSQL-suite claim. Warnings include existing Starlette/httpx and
  SQLAlchemy/Alembic expression-index reflection/deprecation warnings.
- `node scripts/check_ui_bindings.js`: **425 bindings / 10 states**, passed.
  `.resume/Scripts/python.exe -m compileall -q src/app/verification/store.py
  src/app/verification/service.py tests/test_verification_concurrency.py
  scripts/smoke_r1_s2_t3.py` and `git diff --check` passed.
- `check_r1_s2_t3_preservation.py` verifies reviewed source hashes and unchanged
  prior work/working DB. Initial hardcoded SHA comparison had a letter-case
  mismatch; corrected it. The recorded DB bytes matched the snapshot throughout.

Final `check_r1_s2_t3_preservation.py` checks reviewed-code hashes, prior work and
the unchanged working DB SHA256, plus `git diff --check`.
`check_r1_s2_t3_docs.py` checks task/PI status, links, roadmap and next pointer.
These runners/logs are ignored local evidence, not portable setup guarantees;
permanent regressions and HTTP/restart journey are in the repository.

Acceptance gates complete. No browser gate applies to unchanged UI contracts.
No live email/SMS, independent review, CI, deployment or model-quality claim.
Login OTP retains its existing contract. Identity-binding residual T4, delivery
work R3-S1-T2, F09's remaining flows and sprint/PI gates stay open. Candidate-wide
serialization is deliberate; SQLite still has a database-wide writer lock.
Legacy ambiguity recovery requires a resend after cooldown. No working migration,
data cleanup or overwrite occurred; prior work/data and project dependencies are
preserved. This session completes only T3 and stops.

Next: **R1-S2-T4 — Separate asserted contacts from identity changes**. Not started.

## <a id="r1-s2-t4"></a>R1-S2-T4 — Separate asserted contacts from identity changes

Status: done (2026-10-08; bounded development acceptance). F01 residual.
Prerequisite: [T3](#r1-s2-t3). Sprint integration remains [PI-R1/Q](PI-R1.md#r1-s2-q--sprint-integration-review).

An upload cannot move a proved principal's ownership. Exact mailbox OTP pins
the private login address; asserted contacts stay document claims and dedup hints.
This release explicitly refuses login changes, aliases and profile merges.
Contact requests can receive a recorded non-applied review; no manual identity
write or clearing review flags is authorized. AUTH.md owns the detailed contract.

- [T4A](#r1-s2-t4a): done — durable proof, safe initial claim,
  ambiguity/conflict/review refusal, atomic redemption and erasure, legacy
  migration compatibility. Existing credentials retain their subjects.
- [T4B](#r1-s2-t4b): done — compatible unique-email dedup, protected
  phone/contact policy and concurrent stale-match rollback, explicit changes/
  merges refusal, actual read-only inventory and combined two-principal/org
  upload/API plus migrated SQLite/PostgreSQL HTTP/restart acceptance.

Both leaf contracts and the combined parent journey passed on the reviewed
state; the leaves own regression, migration, journey and self-review evidence.
F01's bounded development residual is complete. The separate [R1-S2-Q](#r1-s2-q) gate completed on 2026-10-09;
R1-S2 and PI-R1 close within its recorded current-system scope. No independent/live-provider/quality evidence claimed.

The working-file inventory found one historical-login subject at unmigrated
0023, with unknown proof; no duplicate hints. This authorizes no migration,
repair or cleanup. Dedup/cardinality and final reads remain snapshots; unusual
submissions can create separate subjects. T4A records missing-history/downgrade
limits. Current next task: [PROGRESS.md](../PROGRESS.md).

## <a id="r1-s2-t4a"></a>R1-S2-T4A — Pin verified mailbox ownership

Status: done (2026-10-08). Parent: [T4](#r1-s2-t4); F01 residual.
Prerequisite: [T3](#r1-s2-t3).

### <a id="r1-s2-t4a--acceptance-contract"></a>Acceptance contract

- Store a nullable unique verified login email hash and its proof timestamp on
  the candidate, separate from asserted resume email/phone hashes. Only successful
  exact login OTP redemption establishes it; login itself gives no identity
  assurance. Wrong/expired/replayed/foreign-plane codes cannot create a binding.
- A proved mailbox resolves its durable bound candidate even if asserted hints
  later change or duplicate. It never silently moves to another candidate. A
  different mailbox cannot claim an already bound candidate via a changed hint.
  An unbound, uniquely matching asserted email may be initially claimed after
  OTP proof; missing match creates a bare subject; ambiguous matches refuse.
- Candidate locks re-read state before initial binding; login challenge consume,
  binding, audit and session commit/rollback together. Existing address locks
  serialize same-mailbox login; controlled PostgreSQL transactions cover competing
  hint changes, same-mailbox redemption and erasure. No external send under locks.
- Erasure clears login challenges/issuances for both the bound address and the
  stored asserted address, plus cascaded sessions/outcomes. A stale hint pointing
  at another candidate's proved address cannot cancel that owner's login state.
  Failed erasure/login
  transactions cannot leave partial bindings or resurrect erased subjects.
- Migration adds empty nullable columns and a unique index without inferring or
  backfilling historical ownership. Existing pre-migration sessions have no
  proved address recorded: mark subjects of sessions or session-create audits for explicit binding review
  rather than guessing it from a mutable hint. The review flag persists after
  session expiry/purge and refuses new binding; existing sessions/keys keep their subjects;
  existing ambiguous or differently owned data fails safely. Migrated SQLite/PG
  head/base/head and seeded pre-migration rows prove compatibility/rollback.
- No contact change/alias/profile merge workflow is introduced. No upload policy
  overhaul, working-data migration/repair/inventory or UI change in this child;
  those parent requirements remain T4B. Login/contact delivery stays unchanged.

### <a id="r1-s2-t4a--validation-and-review"></a>Validation and review

Behavioral red/green pin-versus-hint/duplicate/conflicting claim regressions;
offline service/API/portal ownership, failures, retries and erasure tests;
controlled SQLite/PostgreSQL connections, scratch migration gates and actual
migrated HTTP/cookie/restart journey with capture/refusing providers; full pytest,
bindings, compilation, separate diff self-review and preservation/docs checks.
Browser is required only if visible UI contracts change; none is planned.

### <a id="r1-s2-t4a--implementation-and-evidence"></a>Implementation and evidence

`CandidateRow`/0029 add unique nullable proof hash/time and a persistent legacy
review flag. `CandidateStore.bind_verified_login_email` joins exact OTP consume,
session/audit creation and existing address locks; candidate row locks refresh
current hints. Durable proof wins over hints; unsafe initial claims refuse with
existing 409 registration-error transport. Both erasure doors share proof/hint
cleanup and preserve another proved owner's address. AUTH.md owns the contract.

All Python commands used `.resume/Scripts/python.exe`. The ignored safe runner
`.pytest_cache/run_r1_s2_t4.py <log-name> <arguments>` strips inherited DEE_
configuration, pins a missing config file, disables live providers and writes
local logs. Tests use isolated stores and synthetic/capture providers.

- Red: runner `red -m pytest tests/test_candidate_login_binding.py -q --tb=short`:
  **3 failed**, 5.72s. Actual defects: changed hints redirected the original
  mailbox to a shadow subject; a different mailbox claimed the old subject;
  duplicate hints arbitrarily selected one candidate. No fixture failure counted.
- Initial green: runner `green -m pytest tests/test_candidate_login_binding.py
  tests/test_auth_service.py tests/test_auth_store.py tests/test_candidate_store.py
  tests/test_portal_identity.py tests/test_login_redemption_erasure.py
  tests/test_login_erasure_atomic.py tests/test_migrations.py -q --tb=short`:
  **138 passed, 28 skipped, 16 warnings**, 99.71s.
- API: runner `api -m pytest tests/test_portal_identity.py tests/test_auth_api.py
  tests/test_candidate_auth_api.py tests/test_auth_service.py -q --tb=short`:
  **80 passed, 1 warning**, 36.01s. Two principals, ignored supplied candidate ID,
  disjoint portal resumes, unchanged assurance, legacy-cookie subject preserved.
- Extended layers: runner `layers-final -m pytest tests/test_candidate_login_binding.py
  tests/test_candidate_login_binding_concurrency.py tests/test_candidate_login_binding_migration.py
  -q --tb=short`: **19 passed, 7 skipped, 4 warnings**, 20.84s. Invalid proofs,
  exact retry/replay, session/audit rollback, distinct-address cleanup, survivor,
  hint-writer commit/rollback, single redemption and erasure ordering.
- Reviewed SQLite migration: runner `migration-reviewed -m pytest
  tests/test_candidate_login_binding_migration.py -q --tb=short`: **2 passed,
  2 skipped, 3 warnings**, 6.81s. Seeded active/expired/revoked/purged-audit
  subjects, duplicate hints, stable IDs/credentials/audits, surviving sessions,
  persistent refusal flag and nullable proof uniqueness; 0028/head/0028/head.
  Runner `sqlite-migrations .pytest_cache/migrate_r1_s2_t4a_sqlite.py` additionally
  passed fresh SQLite head/base/head, ending at 0029 (9.88s runner).
- Actual scratch SQLite subprocess: runner `journey scripts/smoke_r1_s2_t4a.py`:
  **15/15 checks**, 30.59s runner. Real migrated boot, captured OTP/cookies, F01
  shared-phone actors, changed/duplicate hints, conflicting and ambiguous claim
  refusal, replay, restart and portal erasure with surviving owner/proof.
- Disposable PostgreSQL 18.6 / Asia/Calcutta / READ COMMITTED:
  `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t4a_postgres.py --final`
  passed head/base/head and the broader selected auth/store/API/migration/erasure
  suite: **238 passed, 2 skipped, 19 warnings**, 473.09s. Selection was the green
  list above plus new binding concurrency/migration, auth API, candidate auth API
  and auth challenges. The subsequent final migration correction was separately
  covered by `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t4a_postgres_reviewed.py
  --final`: fresh head/base/head and all three new binding files, **26 passed,
  4 warnings**, 65.22s. Real competing connections observed `pg_blocking_pids`
  against the controlled owner before release; no SQL-lock mocks.
- Corrected final journeys: safe runner `journey-final scripts/smoke_r1_s2_t4a.py`
  passed **15/15 SQLite** checks (20.99s runner); `.resume/Scripts/python.exe
  .pytest_cache/run_r1_s2_t4a_postgres_reviewed.py --journey-only` passed fresh
  head/base/head and **15/15 PostgreSQL** HTTP/restart checks (19.69s journey).
  All three owned PG clusters stopped successfully. CaptureEmail sends no real
  email; these checks establish mechanics, not live-provider delivery.
- Final full regression: `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t4.py
  full-reviewed` runs project Python `-m pytest -q --tb=short`: **2805 passed,
  452 skipped, 113 warnings**, 951.38s (964.21s runner), exit 0. PostgreSQL cases
  are separately evidenced above; the broader PG run's two skips are SQLite
  variants of PostgreSQL-only lock inspection. No live-provider/quality/CI claim.
- `node scripts/check_ui_bindings.js`: **425 bindings / 10 states**, passed;
  project-Python compileall of the ten reviewed code/test/journey files and
  `git diff --check` passed. No screen/handler/cookie/DTO contract changed;
  existing frontend 409 conflict handling applies. No browser execution claimed.

Early `layers` run: **1 failed, 14 passed, 5 skipped** from a new fixture using
the wrong credential column and missing its ID. Corrected to the reflected
schema; subsequent layers/migration runs pass. An incomplete preliminary full
run was stopped for the migration review correction; it supplies no gate result.
Both first PG journeys failed at a smoke-only synthetic hash longer than the
64-character PG column. Removed the provisional hash and seeded the ambiguity
directly from the actual extracted hash. Application/test code was unchanged;
journeys and script compilation rerun after a supplemental harness review.
A final formatting invocation disabled normal CRLF handling and produced false
whitespace findings. Repository-default `git diff --check` passed on rerun;
seven new task files also passed explicit trailing-space checks.

### <a id="r1-s2-t4a--separate-self-review"></a>Separate self-review

Reviewed HEAD `5480498` plus the current ten uncommitted implementation/test/
journey files; hashes recorded in ignored `r1-s2-t4a-reviewed.json`. Specification
pass mapped proof, initial claim, lock/rollback, erasure, legacy migration and
scope exclusions to behavior checks. Correctness pass traced auth issuance/
redemption, both erase doors, store callers, DTOs and frontend error handling.
This was same-agent self-review, not independent review.

- High, migration 0029: a purged session may leave a session-create audit.
  Session-row-only review marking would allow a mutable hint to claim that old
  subject. Flag those audit subjects too; seeded purged-audit regression checks
  preservation and refusal metadata across downgrade/re-upgrade.
- High, candidate cleanup: an asserted hint at another proved owner's address
  must not delete that owner's codes. Check ownership under its address lock;
  standalone/full erasure and real HTTP survivor checks cover the guard.
- Harness, seeded migration: unordered row comparison could fail after a PG
  update changes row order. Compare ordered IDs, preserve sessions/keys/audits.
  Concurrency hooks release and remove listeners on failure.
- Maintainability: reused local UTC conversion; kept the old asserted-hash lookup
  helper's return contract rather than adding an unrelated behavior change.

Final regression/journey gates passed. Preservation passed: 118 unrelated
pre-existing paths unchanged; ten reviewed files unchanged;
working database retained SHA256
`4FF974BB964D160163B179742F26CBF8FB1FCB42FFBA5F1F841BA3EB7D24956B` at 0023.
No remaining implementation finding in A's reviewed scope.
Live delivery, working migration/inventory, absent historical session+audit
recovery, downgrade proof retention, upload contact policy and review/change/
merge workflows are outside this proof. T4B owns the latter parent requirements.

Final project-Python checks: `.pytest_cache/check_docs_r1_s2_t4a.py --final`
validated **57 links** and child/parent/PI/next-task status;
`.pytest_cache/preserve_r1_s2_t4a.py` verified the hashes above;
`.pytest_cache/check_static_r1_s2_t4a.py` passed default Git/new-file whitespace.
Documentation/status and final preservation/diff checks passed; evidence
owners remain leaf/parent/PI/handoff. Only A completed; parent T4 remains in progress.
Next: R1-S2-T4B — Asserted contact policy, identity-change refusal and inventory.

## <a id="r1-s2-t4b"></a>R1-S2-T4B — Asserted contact policy, identity-change refusal and inventory

Status: done (2026-10-08). Parent: [T4](#r1-s2-t4); F01 residual.
Prerequisite: [T4A](#r1-s2-t4a).

### <a id="r1-s2-t4b--acceptance-contract"></a>Acceptance contract

- AC1: Email dedup requires one asserted match compatible with its proved login
  address; ambiguous or conflicting hints never select an arbitrary subject.
  An unmatched email never falls back to phone (F01). Phone-only dedup remains
  available for one unproved subject, excluding proved/legacy-review subjects.
  Unsafe matches create a separate submission, without merging existing rows.
- AC2: Uploads cannot backfill/change asserted contact columns on proved or
  legacy-review subjects, write proof fields or clear the review flag. Extraction
  JSON retains the actual document claims. Unproved unique-email uploads retain
  backfill, versioning, corrected-name protection and per-upload org ownership.
- AC3: Concurrent proof/contact state changes cannot bypass these rules between
  resolution and write; refuse a stale match atomically without re-resolving,
  partial resumes/extractions or resurrecting an erased subject. Retries preserve
  their existing resume/tenant boundary. SQLite and PostgreSQL competing writes
  include commit and rollback; preserve T4A OTP/erasure contracts.
- AC4: Login address changes, aliases and profile merges have explicit refusal:
  this release has no identity-change apply endpoint or manual SQL recovery authorization. Contact
  correction requests can be reviewed/resolved with applied=false; apply=true
  refuses without changing request/identity. Another mailbox's OTP alone cannot
  change a proved subject, select a supplied target or clear legacy review.
- AC5: Read-only aggregate inventory of the explicitly named working SQLite
  database reports duplicate/missing email/phone hints, proof/review anomalies
  where columns exist, and missing proof-schema coverage honestly. No PII, hash
  values, credentials or candidate IDs in output. No migration/repair/data cleanup;
  source bytes preserved. Synthetic legacy/current fixtures test the inventory.
- AC6: Two-principal public upload/API and actual migrated HTTP/restart journeys
  prove disjoint portal ownership, unchanged assurance, preserved cookies/keys,
  cross-org upload isolation and refusal/retry behavior. Parent acceptance is
  assessed using A and B evidence; R1-S2-Q remains a separate session.

### <a id="r1-s2-t4b--validation-plan"></a>Validation plan

Behavioral red/green store regressions, two-actor API/correction tests, real
SQLite/PG competing transactions, migrated scratch app HTTP/restart journeys,
full pytest, bindings/compilation, separate recorded diff self-review, docs and
preservation checks. No schema/UI change planned; migration compatibility is
exercised on scratch stores only. Browser is required if UI contracts change.
Source: candidates/store, rights/service+schema; callers screening/ingest and
portal/auth routes. Reuse offline fixtures, capture provider and T4A journey.

### <a id="r1-s2-t4b--evidence-and-review"></a>Evidence and review

All commands use `.resume/Scripts/python.exe`. The existing safe runner
`.pytest_cache/run_r1_s2_t4.py <log-name> <arguments>` strips inherited DEE_
configuration, disables live providers and isolates storage. Logs are ignored;
durable final results will be recorded below.

Reproducer: safe runner `b-red -m pytest tests/test_asserted_contact_policy.py
-q --tb=short`: **7 failed**, 2.34s pytest / 11.21s runner, all expected behavioral
defects (arbitrary duplicate-email selection, conflicting proof/hint match,
protected phone matching and protected email/phone backfill). No harness error
counted as reproduction. Initial focused green: runner `b-green -m pytest
tests/test_asserted_contact_policy.py tests/test_candidate_store.py
tests/test_ingest_erasure_concurrency.py tests/test_upload_ownership.py
tests/test_candidate_login_binding.py tests/test_rights_service.py -q --tb=short`:
**83 passed, 9 skipped, 1 warning**, 21.53s pytest / 27.19s runner.

Implementation: unique compatible asserted-email resolution, exclusion of
proved/review subjects from phone-only matching, SQL CASE guarded missing-hint
backfill, and match recheck after candidate UPDATE obtains its write lock.
Stale matches roll back with one safe domain error translated by shared ingest
into existing HTTP 422 / failed-batch transport. No schema/DTO/UI change. Rights
refusal text now states the separate proof contract and refuses unsupported
changes/merges instead of suggesting an unimplemented manual identity write.

Actual named-file inventory: project Python
`scripts/inventory_candidate_contacts.py --database data/veritas.db`: **1
candidate; email missing 0; phone missing 1; no-contact 0; email/phone duplicate
groups and rows all 0; historical login subject rows 1**, both evidence tables
available. Revision **0023_correction_pins_the_name** lacks all proof/review
columns: `proof_schema_available=false`, `proof=null`. Its historical subject
requires explicit binding review after any separately authorized migration;
this inventory proves no mailbox ownership. Source bytes retain the handoff's
SHA256; only `veritas.db` was present (no WAL/journal sidecars). No repair,
migration or cleanup. Other files/databases/backups/OneDrive history are outside
this selected-file snapshot. Synthetic current/legacy fixtures and CLI cover
counts, preserved bytes, no identifiers, unavailable coverage and refusal of
missing/unsupported files without creating a DB.

### <a id="r1-s2-t4b--separate-self-review"></a>Separate self-review

Same-agent review of HEAD `5480498` plus the current uncommitted candidate,
shared-ingest, rights service/schema changes and new policy/race/API/batch/
inventory tests and scripts. Specification pass mapped AC1–AC6 to store, API,
controlled transactions, migrated HTTP/restart and aggregate inventory evidence.
Correctness pass traced upload/admin/org/batch callers, resume-bound retry,
T4A exact-OTP binding and both erasure doors, rights decisions, SQL expression
and lock timing, private proof fields, inventory lifetime and frontend generic
422/error handling. No independent review is claimed.

- High, candidate backfill/write boundary: an in-memory proof check alone can
  lose a concurrent proof/review or overwrite another contact writer. SQL CASE
  checks current proof/review and missing contact, then row-locked re-read rejects
  stale matches. Controlled commit/rollback tests include proof, review and hint
  writers. Refused work keeps original resume/extraction counts and survivor.
- Inventory resource/legacy handling: explicitly close the read-only SQLite
  connection; absent/empty revision metadata remains unknown. Do not label the
  unmigrated working subject unproved or invent a mailbox from hints/audits.
- Harness corrections: first API run assumed a nonexistent org resume-list
  route (**1 failed, 17 passed, 8 skipped**, 19.29s); replaced with existing own/
  foreign report HTTP checks and SQL resume ownership. First smoke stopped at
  nested org response ID after five checks; fixed to `org.org.id`. Corrected
  API/inventory **10 passed**, 7.46s; corrected SQLite smoke **16/16**, 20.21s
  runner. These failures are fixture mistakes, not application reproducers.

No remaining implementation finding in the reviewed bounded scope. Final gates
passed. Advisory dedup/cardinality remain snapshots; a new ambiguous upload
may create an additional subject. No document truth/authorship, physical-media
erasure, live delivery, independent review, CI or working-migration claim.

### <a id="r1-s2-t4b--final-validation"></a>Final validation

- Safe runner `b-layers-reviewed -m pytest tests/test_asserted_contact_policy.py
  tests/test_asserted_contact_concurrency.py tests/test_asserted_contact_api.py
  tests/test_asserted_contact_batch.py tests/test_candidate_contact_inventory.py
  tests/test_candidate_login_binding.py tests/test_candidate_login_binding_migration.py
  -q --tb=short`: **44 passed, 14 skipped, 4 warnings in 33.24s** (39.92s runner). Twelve SQLite commit/rollback
  races passed; twelve PG cases and two PG migration variants skipped here.
  API tests include two cookies, protected hints/document claims, two org-owned
  rows/retry/foreign-report 404, unchanged assurance/key subject and non-applied
  reviewed contact refusals. Batch records safe stale-match error, no partial
  candidate/resume and owner-only retry. F01 and old binding/erasure remain green.
- `.resume/Scripts/python.exe .pytest_cache/run_r1_s2_t4b_postgres.py --final`:
  PostgreSQL **18.6**, Asia/Calcutta, READ COMMITTED. Fresh head/base/head passed;
  **225 passed, 2 skipped, 4 warnings in 304.81s (0:05:04)**. Selected files: all four new policy/concurrency/API/inventory files,
  candidate store, ingest erasure concurrency, upload ownership, portal identity,
  rights service/API, auth service/API and the three T4A binding files. Actual
  competing connections inspect `pg_blocking_pids` against the held owner before
  commit/rollback. Both SQLite and PG variants run here; skips are existing
  dialect-specific cases. No mocked SQL locks. Owned cluster stopped successfully.
- Final migrated HTTP/restart: safe runner `b-parent-journey
  scripts/smoke_r1_s2_t4a.py` **15/15 SQLite**; runner `b-journey-corrected
  scripts/smoke_r1_s2_t4b.py` **16/16 SQLite**. The PG runner above executes
  both scripts with `--postgres`: **15/15 + 16/16 PostgreSQL**. Real app boot,
  captured OTP/cookies, upload ownership, contact freezes/document claims, changes/
  review refusals, conflicting hints, repeated original proof, stable keys/
  timestamps, restart and erased-cookie/surviving-principal behavior. Capture
  sends no email; no live-provider or browser claim.
- Safe runner `b-sqlite-migrations .pytest_cache/migrate_r1_s2_t4a_sqlite.py`:
  fresh SQLite **head/base/head**, ending at 0029, passed (9.00s runner).
  Seeded legacy-session/audit migration compatibility passed in layers/PG above;
  no schema change or working migration in B.
- Final full regression: `.resume/Scripts/python.exe
  .pytest_cache/run_r1_s2_t4.py b-full-reviewed` invokes project Python
  `-m pytest -q --tb=short`: **2837 passed, 464 skipped, 113 warnings in 1102.61s (0:18:22)**, exit 0. PostgreSQL SQL cases separately
  passed above; runner duration **1115.59s**. Warnings are the existing Starlette, SQLAlchemy reflection and
  dependency deprecations reported by pytest; no scoring-quality/CI claim.
- `node scripts/check_ui_bindings.js`: **425 bindings / 10 states**, passed.
  Project-Python compileall, `git diff --check`/new-file whitespace, docs links
  and preservation checks passed. Reviewed 11 code/test/script files are pinned
  in ignored `r1-s2-t4b-reviewed.json`. No screen/handler/cookie/DTO shape changed;
  existing generic 422/batch-error handling applies, so no browser gate applies.

Final project-Python `.pytest_cache/check_r1_s2_t4b.py --final` passed compilation,
default Git/new-file whitespace, **192 local links**, child/parent/PI status and
next-task checks. `.pytest_cache/preserve_r1_s2_t4b.py` verified **124 unrelated
pre-existing paths**, the working DB SHA256 recorded above and A's link-only
archive move. All 11 reviewed code/test/script hashes remain unchanged. The
archive contains 33 leaf records plus its README. Only B completed this session;
parent T4 closes through combined acceptance, while Q remains pending.

### <a id="r1-s2-t4b--handoff"></a>Handoff

B and the combined parent T4 bounded acceptance are done. A's proof/migration/
OTP/erasure criteria and B's AC1–AC6 have final reviewed regressions and both
HTTP/restart journeys. Archived leaf evidence owns commands; parent/PI link here.
R1-S2 and PI-R1 remain open for their separate gate. Next: **R1-S2-Q** — integrated
current-consent and identity/OTP ownership review. Read WORKFLOW, PI-R1's R1-S2
journey/Q section and the T1–T4 parent evidence; create Q's bounded brief.
Working DB remains byte-identical at 0023; its one historical-login subject has
unknown mailbox proof and needs explicit review, never automatic repair.
No working migration, cleanup, deployment or external message occurred.
