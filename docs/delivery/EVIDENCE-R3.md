# PI-R3 completed evidence

Reference history, consolidated 2026-10-18. Start with [the handoff](../PROGRESS.md)
and [PI-R3](PI-R3.md) for current status. Each task's original contract,
decisions, validation and limits are retained below; historical next-task pointers
and commands describe their recorded date, not today's execution order or paths.
Moved pytest cases now live in their product-area modules. No old result is a new
execution, independent review, live-provider check or broader quality claim.

- [R3-S1-Q](#r3-s1-q)
- [R3-S1-T1](#r3-s1-t1)
- [R3-S1-T2](#r3-s1-t2)
- [R3-S2-Q](#r3-s2-q)
- [R3-S2-T1](#r3-s2-t1)
- [R3-S2-T2](#r3-s2-t2)
- [R3-S2-T3](#r3-s2-t3)
- [R3-S2-T3A](#r3-s2-t3a)
- [R3-S2-T3B](#r3-s2-t3b)
- [R3-S3-Q](#r3-s3-q)
- [R3-S3-T1](#r3-s3-t1)
- [R3-S3-T2](#r3-s3-t2)
- [R3-S3-T2A](#r3-s3-t2a)
- [R3-S3-T2B](#r3-s3-t2b)
- [R3-S3-T3](#r3-s3-t3)

## <a id="r3-s1-q"></a>R3-S1-Q — Evaluation and verification integration review

Status: done (2026-10-13). PI/sprint: R3/S1. Audit: F09/F10.
Prerequisites: [T1](#r3-s1-t1), [T2](#r3-s1-t2), done.

### <a id="r3-s1-q--contract"></a>Contract

Close only R3-S1 by reviewing the combined T1/T2 delta and exercising the actual
application composition on migrated scratch SQLite/PostgreSQL with fake models
and captured email. One authenticated browser journey must cover org text/PDF
intake, saved report and human feedback, visible invalid-input/service failures,
reload/session loss, operator intake and candidate contact request/confirmation.
The combined HTTP journey must retain reports, outcomes and contact status after
restart and enforce two-actor ownership, CSRF, single use and erasure.
Fix only acceptance regressions. No live email/SMS, deployment, working migration,
data cleanup, scoring change or operator-administration work is authorized here.

| ID | Observable criterion | Required evidence | Result |
|---|---|---|---|
| AC1 | Authorized text/PDF intake returns an actual saved report; feedback/reload use the correct account plane and report | Combined Chrome/HTTP; report/input/outcome regressions | Passed |
| AC2 | Invalid input, unavailable service, duplicate/late actions and session loss settle honestly; foreign actors cannot read/write | Chrome errors; offline JS; two-actor HTTP | Passed |
| AC3 | Captured contact delivery supplies a confirmable code; failed/unavailable sends, rollback, expiry/budgets and erasure preserve privacy/ownership | Chrome/HTTP/restart; SQLite/actual PG transaction regressions | Passed |
| AC4 | Combined changes preserve advisory/style/version semantics, transient inputs and existing data | Historical/batch Chrome; full pytest; separate self-review and preservation | Passed |

Required: fresh focused/full project pytest, offline JS, combined migrated HTTP
and actual Chrome, T2's actual PostgreSQL competing transactions/migrations,
bindings/syntax, recorded specification/correctness self-review and preservation.
F09 may close its bounded delivery/contact gate with R1-S2-T3 and this sprint;
F10 remains open for later administration/browser tasks. PI-R3 remains open.

### <a id="r3-s1-q--evidence-and-review"></a>Evidence and review

Separate self-review of HEAD `5480498`, combined T1/T2 delta and Q fixes; **27
reviewed hashes** and combined diff in `.pytest_cache/r3-s1-q-reviewed.json` /
`r3-s1-q-combined.diff`; Q delta in `r3-s1-q-session.diff`. Pre-Q frontend
copies reconstructed from retained T2 evidence match the session-start hashes.
Specification pass follows AC1-4. Correctness pass
traces org/admin report/outcome routes, CSRF/session transitions, candidate-only
contact binding, send/commit rollback, confirmation clocks/locks/erasure, log
privacy, transient inputs, duplicate/late responses and owned scratch processes.
No independent review or live-provider/quality claim.

Acceptance findings fixed in Q:

| Severity / location | Trigger and consequence | Resolution / regression |
|---|---|---|
| Medium — `frontend/Veritas.dc.html`, `recordOutcome` | Stalled feedback POST leaves busy indefinitely; lost acknowledgment may have saved the judgment | Bound mutation/refresh reads, retain notes and warn to reload before recording again; read-only feedback recovery. Intended Node failure plus actual saved HTTP acknowledgment withheld in Chrome |
| Medium — same handler/session cleanup | Pending old-account feedback blocks the new account; its late response clears new reviewer notes on the same report | Actor/request token guards and session/unmount cleanup; intended Node failures protect newer notes/busy state |
| Medium — `frontend/api.js`, 401 callback | Old session's delayed 401 signs out a newly established account | Compare request/current CSRF cookie before global session loss; current cookie expiry still clears the UI. Intended Node failure; actual expired-session 401 withheld until operator login in Chrome |

Reproduction: `node --test --test-name-pattern='feedback deadline|late feedback'
scripts/test_ui_evaluate.js`: **2 failed** for intended busy/new-account guards;
`--test-name-pattern='late 401'`: **1 failed**, old callback invoked once instead
of zero. Artifacts: `.pytest_cache/r3-s1-q-{feedback,late-401}-red.txt`.
The shared feedback handler already changed in T1 and is part of sprint acceptance;
these fixes stay within Q. No backend, SQL, migration or scoring change in Q.

| Layer | Actual command/result | Artifact |
|---|---|---|
| Focused baseline | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_q.py focused -m pytest -q --tb=short` plus combined T1/T2 focused files and `tests/test_verification_consent.py`: **262 passed, 28 skipped, 2 warnings, 247.86s** | `.pytest_cache/r3-s1-q-focused.txt`; before feedback fixes |
| Final affected | Same runner `affected-final -m pytest -q --tb=short tests/test_ui_evaluate.py tests/test_ui_verification.py tests/test_ui_mount.py tests/test_screening_outcome_api.py tests/test_report_review_context.py`: **31 passed, 1 warning, 30.41s** | `.pytest_cache/r3-s1-q-affected-final.txt` |
| Offline JS | `node --test scripts/test_ui_verification.js`: **34/34**, including 22 evaluate/client checks | Offline handlers/client; separate browser gate |
| Full | Same runner `full` executes project `-m pytest -q --tb=short`: **3380 passed, 479 skipped, 113 warnings, 1351.68s**, exit 0 | `.pytest_cache/r3-s1-q-full.txt`; initial run stopped after review fixes, not passing evidence |
| Combined SQLite HTTP/restart | Same runner `combined-http-final-state scripts/smoke_r3_s1_q.py`: **20/20**, exit 0, 38.51s | `.pytest_cache/r3-s1-q-combined-http-final-state.txt` |
| Combined Chrome / actual HTTP | Same runner `combined-browser-final scripts/check_ui_evaluate_browser.py`: **31/31**, exit 0, 34.47s; report/feedback/contact, ambiguous saved feedback and actual late 401 | `.pytest_cache/r3-s1-q-combined-browser-final.txt` |
| Final contact Chrome | Same runner `contact-browser-final scripts/check_ui_verification_browser.py`: **19/19**, exit 0, 41.30s | `.pytest_cache/r3-s1-q-contact-browser-final.txt` |
| Historical/batch Chrome | Same runner `historical-browser-final-sequential scripts/check_ui_review_context_browser.py`: **22/22**, exit 0, 33.06s; `batch-browser-final-sequential scripts/check_ui_style_browser.py`: **21/21**, exit 0, 28.24s | `.pytest_cache/r3-s1-q-{historical,batch}-browser-final-sequential.txt`; earlier concurrent fixed-port collision is not passing evidence |
| Final API contracts | Same runner `contract-final scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 39.20s | `.pytest_cache/r3-s1-q-contract-final.txt` |
| Legacy captured HTTP | Same runner `legacy-http scripts/smoke_r1_s2_t3.py`: **19/19**, exit 0, 42.08s; backend unchanged by Q fixes | `.pytest_cache/r3-s1-q-legacy-http.txt` |
| Actual PostgreSQL | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_q_postgres_final.py`: fresh owned PG 18.6, Asia/Calcutta/read committed, head/base/head; **305 passed, 2 skipped, 1 warning, 539.52s**; captured contact HTTP **20/20**, 22.83s, combined HTTP **20/20**, 24.48s; shutdown exit 0 | `.pytest_cache/r3-s1-q-pg-final-{focused,journey,combined-journey,migrations,stop}.txt`; mixed selected SQLite/PG run, not full PG |
| Static | Bindings **474 / 15 states**, JS syntax (`api.js`, `support.js`, both offline scripts), project compileall (combined HTTP/Chrome scripts), `git -c core.safecrlf=false diff --check`: passed | Bindings are separate from Chrome |

The safe runners clear inherited DEE settings and disable live providers; all
data/codes are synthetic. Chrome still requires CDN internet. New combined HTTP
uses real cookie/CSRF sessions in all three planes, two orgs/two candidates,
invalid text/PDF refusals, saved v2 reports/human outcomes, wrong-plane/foreign
denials, failed-send retry, single use, restart and erasure. Contact login uses
its separately proved subject; uploaded resume hints are never treated as proof.
Initial harness errors (nonexistent candidate-list route, wrong-plane 403
expectation, POST acknowledgment versus full outcome-list shape, history label,
CDP awaiting an intentionally held promise) were corrected, not application
reproductions. Final successful gates supersede those attempts.

Final preservation: `.resume/Scripts/python.exe .pytest_cache/verify_r3_s1_q.py`;
documentation: `.resume/Scripts/python.exe .pytest_cache/check_r3_s1_q_docs.py`.
Both passed after archiving/status updates, with reviewed source hashes unchanged.

### <a id="r3-s1-q--handoff"></a>Handoff

AC1-4, required gates and separate specification/correctness self-review complete;
no unresolved acceptance finding. Preservation checks cover **846 prior files**,
working DB, HEAD/unrelated status and **27 reviewed hashes**; local links/status
and final diff checks passed. T1/T2 evidence archived with links repaired.
Warnings are existing Starlette/httpx and SQLite expression-index warnings;
conditional skips do not validate omitted environments. No independent review,
CI, live delivery or measured-quality claim. No working migration/data cleanup.

Mail and DB commits remain non-atomic, synchronous SMTP holds the existing lock,
and aggregate resource limits remain PI-R4. An upload/feedback timeout may follow
a saved write; retry remains explicit. Historical assessments are unchanged.
Owned HTTP/Chrome/PG processes stopped; synthetic evidence retained. Existing demo
health 200 and preserved running; its reload-disabled backend still needs a
controlled restart for T2/PDF changes. Working data and prior edits preserved.

**Q/R3-S1 and bounded F09 done; PI-R3/F10 remain open.** Exact next task:
**R3-S2-T1 — Wire organization administration**, not started. Stop after Q.

## <a id="r3-s1-t1"></a>R3-S1-T1 — Wire Instant check

Status: done (2026-10-12). PI/sprint: R3/S1. Audit: F10.
Prerequisite: [R2-S2-Q](EVIDENCE-R2.md#r2-s2-q), done.

### <a id="r3-s1-t1--contract"></a>Contract

Replace the timer and fixture results with one authorized text/PDF request and
navigation to its saved server report. Org sessions use `/screening/candidates`
and org-scoped report/outcome routes; operators use `/evaluate` and `/report`.
Candidates have no evaluation action. Explain persistence before submission:
org uploads store candidate/resume/report; operator ad-hoc checks store a report.
Reuse the existing report's factual/style/version and human-review presentation.
No backend/schema/migration/scoring change, verification delivery, operator
administration, publishing, live providers or working-data cleanup in scope.

Progress describes file reading, server wait and report loading, with no invented
graph progress. Preserve inputs on refusals; guard duplicate submissions and late
responses after session loss/navigation. Timeout/network errors cannot prove that
the server saved nothing; retry is explicit and may create another saved run.
Only a report ID is kept in the URL for authorized reload; resume text stays in
component memory and is cleared at signout/session loss.

### <a id="r3-s1-t1--acceptance--validation"></a>Acceptance / validation

| ID | Observable criterion | Required evidence | Result |
|---|---|---|---|
| AC1 | Text/PDF and both domains show the actual saved report and ID with truthful retention copy | Offline handler regression; migrated HTTP; Chrome text/PDF | Passed |
| AC2 | Empty/invalid input, 403, network/timeout settle visibly and preserve input for manual retry; 401 clears state and requests sign-in | Handler/API client regressions; actual refusal/CSRF/session-expiry Chrome | Passed |
| AC3 | Rapid duplicate clicks send one request; late responses never hijack another screen/account or show fake success | Deferred handler regressions; Chrome duplicate/navigation | Passed |
| AC4 | Org/admin routes, outcomes, reload and erased/missing report recovery preserve ownership and historical/current presentation | HTTP two actors; Chrome org/operator/reload/404; existing report contracts | Passed |

Required: meaningful failing behavioral reproducer, focused/full project pytest,
offline Node handler/client tests, migrated scratch HTTP and real Chrome with fake
providers, bindings/JS syntax, separate same-agent diff review and preservation.
No PostgreSQL gate: SQL, transactions, constraints and migrations are unchanged.

### <a id="r3-s1-t1--evidence-and-review"></a>Evidence and review

Initial reproducer: `node --test --test-name-pattern='organisation submits'
scripts/test_ui_evaluate.js` failed for the intended reason: **0 POST requests,
expected 1**. After implementation, offline checks cover both planes, domains,
PDF/text replacement, refusals/manual retry, duplicate clicks, invalid success,
read-only report retry, reload, session loss/unmount and request deadlines.

Separate self-review: HEAD `5480498` plus the session delta against
`.pytest_cache/r3-s1-t1-before/`, six final file hashes in
`.pytest_cache/r3-s1-t1-reviewed.json`. Specification pass traced AC1-4;
correctness pass checked actual org/admin routes and schemas, CSRF, tenant
redaction, URL encoding/reload, transient inputs, report/outcome guards,
ambiguous-save copy, timeout body reading/timer cleanup and owned scratch
processes. No backend, SQL, scoring or historical-data changes.

Resolved findings:

| Severity / location | Trigger and consequence | Resolution / regression |
|---|---|---|
| Medium — `frontend/Veritas.dc.html`, `signOut` | Pending logout retained sensitive input and allowed late evaluation; clearing immediately then handling late logout success could reset a newly signed-in view | Clear immediately, omit the extra completion mutation; offline signout/late-response checks and final Chrome |
| Medium — same file, `openReport`; `frontend/api.js`, `request` | Stalled report/body read could leave loading forever | Bound report/outcome reads as well as submission, clear timers and retain read-only retry; offline body-timeout/success checks and Chrome error recovery |
| Low — `scripts/check_ui_review_context_browser.py` | Old queue-on-reload/fixture-result assertions described obsolete behavior | Assert saved report reload and empty-input refusal; final historical Chrome **22/22** |

No acceptance-blocking finding remains after specification/caller review and
final affected checks. Same-agent review only.

| Layer | Actual command/result | Artifact |
|---|---|---|
| Focused | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t1.py focused -m pytest -q --tb=short` + files below: **134 passed, 12 skipped, 2 warnings, 86.56s**; final logout adjustment followed by affected rerun below | `.pytest_cache/r3-s1-t1-focused.txt` |
| Offline JS | `node --test scripts/test_ui_evaluate.js`: **19/19** | Included in pytest wrapper |
| Full | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t1.py full` executes `-m pytest -q --tb=short`: **3365 passed, 476 skipped, 113 warnings, 685.98s**, exit 0 | `.pytest_cache/r3-s1-t1-full.txt` |
| Affected pytest after final review fix | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t1.py affected-final -m pytest -q --tb=short tests/test_ui_evaluate.py tests/test_ui_mount.py`: **11 passed, 1 warning, 9.83s**, exit 0 | `.pytest_cache/r3-s1-t1-affected-final.txt` |
| Chrome Instant check / actual HTTP | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t1.py browser-final scripts/check_ui_evaluate_browser.py`: **23/23**, exit 0, 33.87s; migrated 0029 SQL, captured OTP, org text/PDF in both domains, actual IDs/summary, CSRF, outcomes, two-actor ownership, reload/erasure and actual cookie expiry; operator ad-hoc/outcomes/reload and candidate absence | `.pytest_cache/r3-s1-t1-browser-final.txt` |
| Chrome historical/context | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t1.py historical-browser-final scripts/check_ui_review_context_browser.py`: **22/22**, exit 0, 35.31s; plain/polished, exact factual observations, historical/unknown/missing versions, reload/404 recovery and clean console | `.pytest_cache/r3-s1-t1-historical-browser-final.txt` |
| Chrome existing batch | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t1.py batch-browser scripts/check_ui_style_browser.py`: **21/21**, exit 0, 31.43s | `.pytest_cache/r3-s1-t1-batch-browser.txt` |
| HTTP contracts | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t1.py contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 27.58s | `.pytest_cache/r3-s1-t1-contract.txt` |
| Static | `node scripts/check_ui_bindings.js`: **450 bindings / 14 states**; `node --check frontend/api.js`, `node --check frontend/support.js`, `node --check scripts/test_ui_evaluate.js`, `git -c core.safecrlf=false diff --check`: passed | Bindings are separate from real Chrome |
| Preservation | `.resume/Scripts/python.exe .pytest_cache/verify_r3_s1_t1.py`: **220 prior files, 46 prior reviewed source hashes preserved, six task hashes unchanged**, DB/HEAD/unrelated status intact; documentation links passed | Reuses previous Q preservation manifest; this task's frontend delta is reviewed against its start copies |

Focused files under `tests/`: `test_ui_evaluate.py`, `test_ui_mount.py`,
`test_screening_api.py`, `test_screening_outcome_api.py`,
`test_screening_report_input.py`, `test_resume_input_boundary.py`,
`test_report_review_context.py`, `test_cookie_posture.py`, `test_auth_sessions.py`.
The safe runner clears inherited DEE settings and disables live providers.
Initial validation mistakes (nonexistent focused file, incorrect browser labels,
outcome response shape and navigation timing) were corrected in the harness.
An obsolete historical fixture assertion failed before its update. The earlier
full run was intentionally stopped after the final logout review fix; it is not
claimed as passing evidence. Final source hashes are now fixed for regression.

### <a id="r3-s1-t1--handoff"></a>Handoff

AC1-4, required regression/journey/static gates and separate self-review complete.
Inputs are transient; authorized server reports/outcomes persist and reload.
Warnings are the existing Starlette/httpx deprecation and SQLite expression-index
reflection/comparison; conditional skips do not prove PostgreSQL/optional formats.
Chrome needs CDN internet. Browser timeout/network/503 failures inject synthetic
transports; uploads, refusals/CSRF/expiry, ownership, report reads/outcomes and
erasure use actual HTTP with fake providers. No independent/live-provider or
measured-quality claim. A deadline cannot undo a server commit; manual retry may
save another run. No backend/scoring/historical rewrite or working migration.
Working DB/prior edits preserved; task-owned servers/Chrome stopped, synthetic
evidence retained and local demo healthy (200). No deployment, message or cleanup.

T1 is done; R3-S1, PI-R3 and F10 remain open. Exact next task: R3-S1-T2 — Connect
contact-verification delivery, not started. Stop after T1.

Combined sprint acceptance closes at [R3-S1-Q](#r3-s1-q).
The next-task pointers above record the original session handoffs.

## <a id="r3-s1-t2"></a>R3-S1-T2 — Connect contact-verification delivery

Status: done (2026-10-12). PI/sprint: R3/S1. Audit: F09.
Prerequisites: [R3-S1-T1](#r3-s1-t1), [R1-S2-T3](EVIDENCE-R1.md#r1-s2-t3), done.

### <a id="r3-s1-t2--contract"></a>Contract

The production verification builder currently uses a silently discarding
NullNotifier although login already has a configured email client. Share that
client through an email notifier; unavailable email/phone must refuse explicitly
before issuing secrets. Provider failure must return a safe failure, never a sent
notice or debug code. Addresses/codes must stay out of logs and error responses.
Use captured/fake delivery only in this task; no real email/SMS is authorized.

Dispatch a new code within the existing candidate-locked issuance transaction,
before committing it: failure rolls back the new secret and supersession,
preserving an older active code and avoiding cooldown from an unsent request.
Mark the newly started attempt failed using the existing completion path after
delivery failure. No schema/migration or login/identity/consent/scoring change.
Holding the existing lock through the existing email client's send is the direct
choice; SMTP retains its per-operation socket timeouts, and SQLite holds its
writer lock during delivery. Aggregate latency/resource limits remain PI-R4.
No new worker, queue or outbox. SQL transaction
semantics change, so isolated PostgreSQL evidence is required.

Add a bounded candidate-portal contact form using existing start/confirm/list
APIs: destination on record, email/phone, delivered code, visible pending/error/
success, manual retry and server status after reload. Preserve candidate-only
access, CSRF, hashed destination binding, cooldown, expiry, attempts, single use,
erasure and advisory assurance. Contact control never verifies employment.

### <a id="r3-s1-t2--acceptance--validation"></a>Acceptance / validation

| ID | Observable criterion | Required evidence | Result |
|---|---|---|---|
| AC1 | Production composition delivers email containing a confirmable code to the bound contact, with no default debug echo | Builder/service/API regressions; migrated captured HTTP and Chrome | Passed |
| AC2 | Unavailable email/phone and provider failure refuse safely; no active unsent secret/cooldown, false sent state or payload disclosure | Refusal/privacy and rollback tests; real refusal HTTP/Chrome; rendered logs | Passed |
| AC3 | Confirmation, concurrent resend/confirm, expiry/attempts and erasure preserve R1-S2-T3 ordering/ownership; failed dispatch preserves prior active challenge | SQLite/PostgreSQL competing transactions, existing service/store tests; HTTP/restart | Passed |
| AC4 | Portal shows actual response/status and held/expired assurance, retains destination for retry, guards duplicate/late actions and clears codes at session loss; reload reads persisted results | Offline handler tests, real candidate Chrome, denied actors/CSRF | Passed |

Required: intended failing behavioral reproduction, focused/full project pytest,
production-builder regression, migrated scratch HTTP/restart with fake/captured
providers, actual Chrome, isolated PostgreSQL transaction evidence, UI bindings/
syntax, separate same-agent diff review, preservation and documentation checks.

### <a id="r3-s1-t2--evidence-and-review"></a>Evidence and review

Reproducer: `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t1.py t2-red
-m pytest -q --tb=short tests/test_verification_delivery.py`: **6 failed**,
1 warning, 30.82s. No captured production email; unavailable email/phone and a
failed provider returned success; SMTP exception logs exposed synthetic contact/
code. Fixtures/import/response-shape corrections are separate from reproduction.

Separate self-review of HEAD `5480498` plus the task delta against
`.pytest_cache/r3-s1-t2-before/`: **21 file hashes** in
`.pytest_cache/r3-s1-t2-reviewed.json`, delta in `r3-s1-t2-session.diff`.
Specification pass traces AC1-4. Correctness pass follows production/shared email
construction, every challenge caller, candidate locks and rollback, clocks,
supersession/cooldown, completion/erasure, debug guards, exception/log privacy,
candidate/CSRF boundaries, transient UI fields, terminal/reload/retry handling
and task-owned scratch providers/processes. Same-agent review only.

| Severity / location | Trigger / consequence and resolution | Regression |
|---|---|---|
| High — `services/email.py`, SMTP error handling | Provider exceptions can contain destination/code; emit only type and a generic exception, suppress raw exception chaining | Intended rendered-log failure; final privacy tests/HTTP/Chrome |
| Medium — verification service/store/delivery | Discarding or failed send could claim success/leave a live code; preflight capability and send before locked commit, roll back failure, record failed outcome | Intended capture/refusal failures; rollback/concurrent confirmation/erasure tests and actual PG blockers |
| Medium — portal contact handlers | Stale/terminal or malformed replies could leave a wrong target/code action or claim sent; guard actor/action/list generations, require expected ID/method/status, clear terminal code fields | Offline handlers plus final Chrome expiry/reload/session-loss |
| Medium — portal assurance mapping / binding fixture | Rendered review showed a verified email as Not held: UI and fixture used nonexistent `methods_held`; read actual `methods`/`expired_methods`, update fixture and assert Held/Expired | `node --test --test-name-pattern='portal assurance shows' scripts/test_ui_verification.js`: intended **1 failed**, Not held vs Held; final offline and actual Chrome held/expired checks |

Delivery lives in one adapter module because pure OTP math is also imported by
login/candidate stores; importing the services package from that module caused
a circular import, caught and corrected before validation. Existing contact
mechanics tests now explicitly select capture; the default still refuses.
The old HTTP journey now selects capture and checks its local debug code against
that capture. Nullable `debug_code: null` remains API-compatible and exposes no
code. No remaining acceptance-blocking finding; final full regression passed. The
earlier full run was stopped after the assurance review fix; it is not passing
evidence. Final application state was reviewed/hashed again before restart.

| Layer | Actual command/result | Artifact |
|---|---|---|
| Initial focused | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t1.py t2-focused -m pytest -q --tb=short` + files below: **132 passed, 16 skipped, 1 warning, 86.71s** | `.pytest_cache/r3-s1-t1-t2-focused.txt` |
| Offline JS | `node --test scripts/test_ui_verification.js`: **31/31**, including 19 reused evaluate/client checks | Pytest wrapper runs offline; separate Chrome gate |
| Final focused | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t2.py focused-final -m pytest -q --tb=short` + files below: **132 passed, 16 skipped, 1 warning, 84.35s**, exit 0 | `.pytest_cache/r3-s1-t2-focused-final.txt` |
| Full | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t2.py full` executes `-m pytest -q --tb=short`: **3377 passed, 479 skipped, 113 warnings, 1273.21s**, exit 0 | `.pytest_cache/r3-s1-t2-full.txt` |
| Migrated SQLite HTTP/restart | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t2.py http scripts/smoke_r3_s1_t2.py`: **20/20**, exit 0, 16.24s | `.pytest_cache/r3-s1-t2-http.txt` |
| Actual PostgreSQL | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t2_postgres.py`: fresh owned **PG 18.6**, Asia/Calcutta/read committed, head/base/head; **209 passed, 2 skipped, 1 warning, 284.62s**; captured HTTP/restart **20/20**, 16.30s, shutdown exit 0 | `.pytest_cache/r3-s1-t2-pg-{focused,journey,migrations,stop}.txt`; mixed selected run, not full PG |
| Affected pytest after assurance fix | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t2.py affected-assurance-final -m pytest -q --tb=short tests/test_verification_delivery.py tests/test_ui_verification.py tests/test_ui_evaluate.py tests/test_ui_mount.py`: **18 passed, 1 warning, 19.57s**, exit 0 | `.pytest_cache/r3-s1-t2-affected-assurance-final.txt` |
| Chrome candidate / actual HTTP | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t2.py browser-assurance-final scripts/check_ui_verification_browser.py`: **19/19**, 20.91s, exit 0; captured signup/contact, actual CSRF/unavailable/failure/duplicate/wrong/foreign/expired/exhausted/success/reload/session loss, visible held/expired assurance and clean console/logs | `.pytest_cache/r3-s1-t2-browser-assurance-final.txt` |
| Chrome evaluate regression | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t2.py evaluate-browser scripts/check_ui_evaluate_browser.py`: **23/23**, 28.56s, exit 0 | `.pytest_cache/r3-s1-t2-evaluate-browser.txt` |
| Legacy contact HTTP | `.resume/Scripts/python.exe .pytest_cache/run_r3_s1_t2.py legacy-http scripts/smoke_r1_s2_t3.py`: **19/19**, 18.89s, exit 0, now explicitly captured email | `.pytest_cache/r3-s1-t2-legacy-http.txt` |
| Static | `node scripts/check_ui_bindings.js`: **474 bindings / 15 states**; JS syntax for `frontend/api.js`, `frontend/support.js`, `scripts/test_ui_verification.js`; project Python `-m compileall -q src/app/verification src/app/services/email.py scripts/smoke_r3_s1_t2.py scripts/check_ui_verification_browser.py`; `git -c core.safecrlf=false diff --check`: passed | Binding checks are separate from Chrome |

Focused files under `tests/`: `test_verification_delivery.py`,
`test_verification_delivery_transactions.py`, `test_verification_service.py`,
`test_verification_api.py`, `test_verification_store.py`,
`test_verification_concurrency.py`, `test_verification_erasure.py`,
`test_verification_org_api.py`, `test_verification_otp.py`, `test_email_seam.py`,
`test_ui_verification.py`, `test_ui_evaluate.py`, `test_ui_mount.py`,
`test_ratelimit_wiring.py`. PG adds consent and login race regressions. Its new
transaction tests parameterize SQLite/PG and observe `pg_blocking_pids` through
the existing race harness. Tests use isolated stores/fake providers; capture
files contain synthetic test OTPs only. No real delivery or quality claim.
The first assurance Chrome assertion selected an inner DC binding span; rendered
review showed Held correctly after the application fix. Corrected the selector
to assert the row's status; the final 19/19 result supersedes that harness failure.

### <a id="r3-s1-t2--handoff"></a>Handoff

AC1-4, required checks and separate self-review complete. Email uses the shared
configured capability; unavailable email/phone refuse, send failure leaves no
new usable code, old active codes survive rollback and all confirmation guards
remain. Candidate controls show actual status and held/expired assurance.
Preservation verified **832 prior files**, **21 reviewed hashes**, working DB,
HEAD and unrelated status; local documentation links/diff checks passed.
Warnings are the existing Starlette/httpx and SQLite expression-index warnings;
conditional skips do not prove environments they omit. The PG result is a mixed
selected SQLite/PG run with actual PG blockers and HTTP, not a full PG suite.
Capture/fake provider evidence proves mechanics, not live delivery or identity/
employment accuracy. No independent review, schema/scoring or working migration.

Mail delivery cannot be atomic with the database: an acknowledgment/commit
failure can leave a delivered, unusable code. SMTP is synchronous with its
existing socket timeouts and holds the candidate/SQLite writer lock; aggregate
latency/resource limits remain PI-R4. Codes/destinations stay out of logs/errors;
test captures are synthetic and ignored. Task-owned servers/Chrome/PG stopped,
synthetic evidence retained. The existing demo is healthy (200) and was preserved
running; its reload-disabled backend needs a controlled restart to load this
change. No live email/SMS, deployment, cleanup or prior-data overwrite occurred.

T2 done; R3-S1/PI-R3/F09 remain open. Exact next task: **R3-S1-Q — Evaluation and
verification integration review**, not started. Stop after T2.

Combined sprint acceptance closes at [R3-S1-Q](#r3-s1-q).
The next-task pointers above record the original session handoffs.

## <a id="r3-s2-q"></a>R3-S2-Q — Sprint integration review

Status: done (2026-10-14). PI/sprint: R3/S2. Audit: F10.
Prerequisites: [T1](#r3-s2-t1), [T2](#r3-s2-t2),
[T3](#r3-s2-t3) and its T3A/T3B children, all done.

### <a id="r3-s2-q--contract"></a>Contract

Prove organization, operator-account and guarded curation behavior together
through the actual migrated scratch app with capture/fake providers. Add a
bounded combined journey using existing smoke/CDP helpers. Review the combined
sprint diff separately. Fix only findings that block this sprint's acceptance.
No working migration, demo restart, cleanup, deployment, live provider or scoring
change. No independent-review or empirical-quality claim.

| ID | Observable criterion | Required evidence | Result |
|---|---|---|---|
| AC1 | One operator creates an org, changes reliability/rotates its key, creates another operator and maps/creates/ignores vocabulary; browser reload and app restart agree with saved state | Combined actual Chrome and SQLite/PostgreSQL HTTP/restart | Passed |
| AC2 | Second operator cannot consume a stale snapshot; missing/null revisions, CSRF, revoked accounts and anonymous/org/candidate planes refuse without mutation or disclosure | Combined two-actor HTTP/Chrome; focused regressions | Passed |
| AC3 | Navigation, failures and session loss preserve honest recovery and clear keys/raw drafts; no fixture counts, unsupported account actions or console exceptions | Offline shipped handlers, combined and existing Chrome/contract journeys | Passed |
| AC4 | Normalization, raw erasure/expiry, explicit attribution, static precedence and existing evaluation/contact behavior remain; prior files/DB/demo preserved | Lifecycle HTTP, focused/full pytest, combined diff self-review, static and preservation checks | Passed |

Required: focused/full project pytest, actual combined browser and migrated
SQLite/PostgreSQL HTTP/restart, existing affected browser/API contracts, offline
handlers, bindings/syntax and separate specification/correctness self-review.
Re-run T3A's PostgreSQL controlled-lock/migration regressions for combined
acceptance; no new schema/SQL change is planned. Bindings/fakes/self-review are
reported separately from browser/live-provider/independent evidence.

### <a id="r3-s2-q--evidence-and-review"></a>Evidence and review

New permanent journeys: `scripts/smoke_r3_s2_q.py` (SQLite or `--postgres`,
optional `--browser`) and `scripts/check_ui_operator_browser.py` (combined CDP
steps called by that smoke). They use existing fake-model/capture composition,
smoke clients, owned schema setup and Chrome helpers. No application change.
No defect reproduction is claimed. First HTTP/Chrome runs found an extra
role-denial org in the test fixture, making expected counts wrong; reused the
already-created second org and fully reran. Those initial failures are retained
in `r3-s2-q-http-initial.txt` / `r3-s2-q-browser-initial.txt`, not passing evidence.

Separate same-agent specification/correctness review: HEAD `5480498` plus
26 source/test/journey hashes in `.pytest_cache/r3-s2-q-reviewed.json`, with
`r3-s2-q-combined.diff` and separate `r3-s2-q-session.diff`, captured by project
Python `.pytest_cache/review_r3_s2_q.py`. Original sprint file copies are checked
against T1's initial hashes; new sprint files are explicit additions. The session
code delta is the two journeys. Specification review maps AC1-4 to actual server
rows, concealed keys, supported account controls, required loaded revisions,
restart/revocation and existing error journeys. Correctness review follows
shared router/session/CSRF gates, operator deletion cascades and nullable alias
attribution, revision membership/time after lock waits and rollback, raw source
erasure/expiry, deterministic static/approved normalization, response validation,
actor/view/load/action tokens and private scratch setup/owned process teardown.
No unresolved acceptance-blocking finding in this bounded review; self-review,
not independent review. SQL/migration/scorer behavior is unchanged. PostgreSQL
checks revalidate existing controlled-lock/migration behavior, not working data.
Low documentation finding: `docs/delivery/archive/README.md` described 39 records
while the initial inventory contained 42. Corrected to 46 after the four sprint
child moves; the final link/status/inventory check validates the actual count.

Safe runner: `.resume/Scripts/python.exe .pytest_cache/run_r3_s2_q.py <tag>
<Python arguments>` clears inherited DEE configuration and disables providers;
an omitted argument list runs project `-m pytest -q --tb=short`. Actual normal
changes/denials/restarts use migrated scratch 0029 storage and captured synthetic
login; inherited browser error transports are synthetic. Chrome needs CDN
internet. No live-provider or measured-quality claim.

Focused arguments: `-m pytest -q --tb=short tests/test_curation_api.py
tests/test_curation_activation.py tests/test_curation_service.py
tests/test_curation_review_revisions.py tests/test_curation_storage_migration.py
tests/test_curation_owned_store.py tests/test_ui_curation.py
tests/test_ui_admin_orgs.py tests/test_ui_admin_users.py tests/test_ui_evaluate.py
tests/test_ui_verification.py tests/test_ui_mount.py tests/test_auth_api.py
tests/test_auth_sessions.py tests/test_cookie_posture.py tests/test_org_scope_guard.py`.

| Layer | Actual command/result | Artifact |
|---|---|---|
| Focused/offline handlers | Safe runner `focused` with arguments above: **155 passed, 85 skipped, 69 warnings, 189.98s**, exit 0 | `.pytest_cache/r3-s2-q-focused.txt` |
| Combined actual Chrome/SQLite HTTP/restart | Safe runner `browser-second scripts/smoke_r3_s2_q.py --browser`: **53/53**, exit 0, 55.97s; combined org create/reliability/rotation/offboarding, user creation/real login/deletion, guarded map/create/ignore, stale second reviewer, browser reload after app restart, three-surface revocation and actual org/candidate browser denials; no console exceptions | `.pytest_cache/r3-s2-q-browser-second.txt` |
| Org Chrome/HTTP/restart | Safe runner `org-browser scripts/check_ui_admin_orgs_browser.py`: **28/28**, exit 0, 52.79s | `.pytest_cache/r3-s2-q-org-browser.txt` |
| User Chrome/HTTP/restart | Safe runner `users-browser scripts/check_ui_admin_users_browser.py`: **29/29**, exit 0, 44.97s | `.pytest_cache/r3-s2-q-users-browser.txt` |
| PostgreSQL locks/migrations | Project Python `.pytest_cache/run_r3_s2_q_postgres.py`, selecting curation API/activation/revisions/storage/owned and auth API/sessions/org-scope tests: **197 passed, 17 skipped, 69 warnings, 398.61s**, exit 0; PG 18.6 / READ COMMITTED / Asia/Calcutta; controlled competing review, expiry/erasure waits, constraints/cascades and existing up/down/up | `.pytest_cache/r3-s2-q-pg-focused.txt` |
| Combined PostgreSQL HTTP/restart | Same owned runner invokes `scripts/smoke_r3_s2_q.py --postgres`: **35/35**, exit 0, 32.98s; owned PG stop exit 0, 47.60s | `.pytest_cache/r3-s2-q-pg-http.txt`, `r3-s2-q-pg-runtime.json` |
| Existing curation/evaluation/contact Chrome | Serial safe runner `.pytest_cache/run_r3_s2_q_journeys.py`: `curation-browser scripts/check_ui_curation_browser.py` **46/46**, exit 0, 53.94s; `evaluate-browser scripts/check_ui_evaluate_browser.py` **31/31**, exit 0, 33.72s; `contact-browser scripts/check_ui_verification_browser.py` **19/19**, exit 0, 29.71s | Corresponding `.pytest_cache/r3-s2-q-<tag>.txt` |
| Contracts/input boundary | Same serial runner: `contract scripts/check_ui_screening_contract.py` **32/32**, exit 0, 20.08s; `input-http scripts/smoke_curation_input.py` **13/13**, exit 0, 22.56s | Corresponding `.pytest_cache/r3-s2-q-<tag>.txt` |
| Erasure HTTP | Same serial runner: `erasure-http scripts/smoke_r1_s1_t3b_d3d2d3.py`: **15/15**, exit 0, 133.47s; both-door rollback/process death/retry/restart, surviving raw and approved vocabulary | `.pytest_cache/r3-s2-q-erasure-http.txt` |
| Offline JS | `node --test scripts/test_ui_admin_orgs.js scripts/test_ui_admin_users.js scripts/test_ui_curation.js`: **111/111**, no failures/skips, exit 0, 779.20ms; includes inherited evaluate/client regressions per suite | `.pytest_cache/r3-s2-q-offline-node.txt` |
| Full pytest | Safe runner `full`, project `-m pytest -q --tb=short`: **3403 passed, 496 skipped, 127 warnings, 1037.02s**, exit 0 on reviewed source | `.pytest_cache/r3-s2-q-full.txt` |
| Static | `node scripts/check_ui_bindings.js`: **559 bindings / 17 states**; `node --check frontend/api.js`, `frontend/support.js`; project `-m compileall -q scripts/smoke_r3_s2_q.py scripts/check_ui_operator_browser.py`; `git -c core.safecrlf=false diff --check`: passed | Bindings are separate from actual Chrome |

### <a id="r3-s2-q--handoff"></a>Handoff

AC1-4, required gates and separate self-review passed; Q and R3-S2 are done.
T1/T2/T3A/T3B detailed records were archived with inbound/outbound links repaired;
T3's group summary remains in `tasks/`. Warnings are existing Starlette/httpx
and SQLite expression-index warnings; conditional skips do not prove omitted
environments. No new application/SQL/migration/scoring change or compatibility
transition; T3B's required HTTP revisions remain. No independent/live-provider
or empirical-quality claim. Unpaged org/account APIs, allowed self/last-operator
deletion, ambiguous commits, later fresh capture, per-term observation resource
growth and process-local overlay refresh remain explicit limits assigned to
their existing contracts/R4 gates. The preserved demo's older backend still
needs its separately controlled restart for prior backend/PDF changes.

Final project Python `.pytest_cache/verify_r3_s2_q.py`: **866 prior files**,
working DB/HEAD/unrelated status and **26 reviewed hashes** preserved; demo health
200, owned PG stopped. Project Python `.pytest_cache/check_r3_s2_q_docs.py
--closed`: **14 records / 311 local links**, acceptance/status, 46-record archive
inventory and next-task consistency passed. Final `git -c core.safecrlf=false
diff --check` and new journey/evidence whitespace checks passed. Owned
app/Chrome/PG stopped, synthetic artifacts retained. No cleanup or deployment.
PI-R3/F10 remain open; F10's broader browser regression remains R5-S2-T1. Exact
next task: **R3-S3-T1 — Repair and version the interview rubric**, not started.
Stop after Q.

## <a id="r3-s2-t1"></a>R3-S2-T1 — Wire organization administration

Status: done (2026-10-13). PI/sprint: R3/S2. Audit: F10.
Prerequisite: [R3-S1-Q](#r3-s1-q), done.

### <a id="r3-s2-t1--contract"></a>Contract

Replace `adminorgs` fixtures with authorized `/ledger/orgs` operations: list,
create, reliability update, key rotation and hard-cascade offboarding. Inspect
actual row fields from the existing list; no detail/rename/suspend API exists.
Use local filtering and 20-row pagination because the existing API returns an
unpaged list. No backend/SQL/migration, scoring, user administration, curation,
live providers, deployment, working migration or data cleanup in this task.

Show actual loading/empty/error states and persisted server results after reload.
No optimistic success. Reliability is a nonnegative finite multiplier (neutral
1; 0 mutes evidence), not a calibrated accuracy score. Rotation/offboarding need
explicit two-step confirmation with their existing credential/cascade effects.
New keys are displayed only in memory, concealed initially, and cleared on
selection change, leaving the screen, reload or session loss. Do not log/store
keys or put them in URLs. Bound reads/mutations; ambiguous failures advise refresh
before retry. Guard duplicate clicks and late replies across account/navigation.

| ID | Observable criterion | Evidence | Result |
|---|---|---|---|
| AC1 | Operator list/detail/filter/pagination/empty state use actual rows and fields; other account planes do not fetch/display org data | Offline handlers; migrated HTTP/Chrome | Passed |
| AC2 | Create/reliability persist and reload; invalid/conflict/403/timeout failures settle visibly without fake success | Behavioral regressions; actual browser/API mutations/refusals/restart | Passed |
| AC3 | Rotation/offboarding require confirmation, target only the selected org and invalidate the old key/delete actual state; one-time keys clear on lifecycle changes | Offline guards; two-org HTTP/Chrome | Passed |
| AC4 | Duplicate/late replies, 401/session loss and failed refresh preserve ownership/privacy and existing flows/data | Offline regressions; real Chrome expiry; full pytest; self-review/preservation | Passed |

Required: intended failing reproducer, focused/full project pytest, offline JS,
migrated scratch HTTP/restart and actual Chrome with fake/capture providers,
bindings/syntax, recorded specification/correctness self-review and preservation.
No PostgreSQL gate: existing SQL/transaction/migration behavior is unchanged.

### <a id="r3-s2-t1--evidence-and-review"></a>Evidence and review

Reproducer: `node --test --test-name-pattern='operator landing'
scripts/test_ui_admin_orgs.js`: **1 failed**, expected `/ledger/orgs` GET,
received none. Initial fixtures were not loading actual rows. Artifact:
`.pytest_cache/r3-s2-t1-red.txt`. The later permission regression failed for the
intended wrong consent wording: `node --test --test-name-pattern='failure retains
input' scripts/test_ui_admin_orgs.js`, **4 passed, 1 failed**;
`.pytest_cache/r3-s2-t1-permission-red.txt`.

Separate self-review of HEAD `5480498` plus the delta against
`.pytest_cache/r3-s2-t1-before/`: six reviewed file hashes and session diff in
`.pytest_cache/r3-s2-t1-reviewed.json` / `r3-s2-t1-session.diff`. Specification
pass traces AC1-4. Correctness pass follows actual org schemas/routes, admin/CSRF
gates, ID encoding, real response mapping, finite weight validation, duplicate/
confirmation guards, secret lifecycle, failed refresh/ambiguous saves and owned
scratch processes. No backend/SQL/scoring change. Same-agent review only.

Resolved findings: (medium, `nav`/org action guards) leaving and returning while
a write is pending could reveal its late key in a new view; invalidate that
action at navigation and advise refresh, with offline late-return regression.
(medium, org error mapping) non-CSRF 403 used candidate consent copy; use explicit
admin denial for reads/actions, with intended Node failure and rendered refusal.
No unresolved acceptance finding; required final checks passed on reviewed hashes.

Initial focused command: `.resume/Scripts/python.exe .pytest_cache/run_r3_s2_t1.py
focused -m pytest -q --tb=short` plus `tests/test_ui_admin_orgs.py`,
`test_ui_evaluate.py`, `test_ui_verification.py`, `test_ui_mount.py`,
`test_ledger_api.py`, `test_ledger_store.py`, `test_auth_api.py`,
`test_auth_sessions.py`, `test_org_name_case_insensitive.py`,
`test_auth_org_name_taken.py`, `test_cookie_posture.py`, `test_org_scope_guard.py`:
**129 passed, 1 warning, 47.86s**. This is the pre-permission-fix baseline;
final affected checks below cover that fix.

| Layer | Actual command/result | Artifact |
|---|---|---|
| Final affected | `.resume/Scripts/python.exe .pytest_cache/run_r3_s2_t1.py affected-final -m pytest -q --tb=short tests/test_ui_admin_orgs.py tests/test_ui_evaluate.py tests/test_ui_verification.py tests/test_ui_mount.py`: **13 passed, 1 warning, 6.35s**, exit 0 | `.pytest_cache/r3-s2-t1-affected-final.txt` |
| Offline JS | `node --test scripts/test_ui_admin_orgs.js`: **34/34**, including 22 reused evaluate/client checks | Executed by permanent pytest wrapper; separate Chrome gate |
| Full | Same runner `full` executes project `-m pytest -q --tb=short`: **3382 passed, 479 skipped, 113 warnings, 1060.43s**, exit 0 | `.pytest_cache/r3-s2-t1-full.txt`; initial stopped run is not passing evidence |
| Chrome/actual HTTP/restart | Same runner `browser-reviewed scripts/check_ui_admin_orgs_browser.py`: **28/28**, exit 0, 29.67s; migrated 0029, captured named operator, all supported operations, confirmations, actual key invalidation, two org/candidate actor denials, reliability/session/key persistence after restart, reload/expiry and privacy | `.pytest_cache/r3-s2-t1-browser-reviewed.txt` |
| Existing evaluate/contact Chrome | Same runner `evaluate-browser scripts/check_ui_evaluate_browser.py`: **31/31**, exit 0, 29.59s | `.pytest_cache/r3-s2-t1-evaluate-browser.txt` |
| API contracts | Same runner `contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 17.25s | `.pytest_cache/r3-s2-t1-contract.txt` |
| Static | `node scripts/check_ui_bindings.js`: **520 / 16 states**; JS syntax (`api.js`, `support.js`, `test_ui_admin_orgs.js`), project compileall (browser/wrapper), `git -c core.safecrlf=false diff --check`: passed | Bindings are separate from Chrome |

Final source hashes remain fixed. Safe runner clears inherited DEE configuration
and disables live providers; scratch app uses captured login/fake models. Chrome
requires CDN internet. 403 policy/503/deadline/held-request transports are
synthetic; normal mutations, CSRF/ownership, expiry/restart and returned key
invalidation use actual HTTP. No independent/live-provider or quality claim.
Final preservation: `.resume/Scripts/python.exe .pytest_cache/verify_r3_s2_t1.py`,
**855 prior files**, working DB, HEAD/unrelated status and six reviewed hashes
preserved; existing demo health 200. Documentation: project Python
`.pytest_cache/check_r3_s2_t1_docs.py`; local links/status/next-task boundary and
final diff checks passed. Warnings are existing Starlette/httpx and SQLite
expression-index warnings; conditional skips do not prove omitted environments.

### <a id="r3-s2-t1--handoff"></a>Handoff

AC1-4, required checks and separate self-review complete. T1 done;
R3-S2/PI-R3/F10 remain open. API listing remains unpaged, writes have no version
precondition, and an interrupted create/rotation response can lose a key whose
change already committed. Recovery is explicit refresh/confirmed rotation;
reliability is an operator setting, not calibrated accuracy. No working migration,
data cleanup or deployment. Owned app/Chrome stopped and synthetic evidence
retained; working data/prior edits/demo preserved. Existing demo backend restart
for earlier T2/PDF changes remains pending. Exact next task:
**R3-S2-T2 — Wire user administration**, not started. Stop after T1.

## <a id="r3-s2-t2"></a>R3-S2-T2 — Wire user administration

Status: done (2026-10-13). PI/sprint: R3/S2. Audit: F10.
Prerequisite: [R3-S2-T1](#r3-s2-t1), done.

### <a id="r3-s2-t2--contract"></a>Contract

Replace `adminusers` fixtures with `/admin/users` list/create and confirmed
`DELETE /admin/users/{id}`. Show actual ID, optional label, created date and
enabled/disabled status. All rows are platform operators by the API contract;
there are no editable roles, tenant memberships, last-seen or readable emails
in this API. Do not offer unsupported controls or invent those values.
Use local filtering/20-row paging for the existing unpaged list.

Deletion removes the account and cascades its sessions. The existing API allows
self/last-operator deletion and `/auth/me` does not identify the operator row:
warn explicitly at confirmation that deleting one's own account ends sign-in,
including recovery through another operator or the configured machine admin key.
Do not imply self/last-account protection. Existing own-device session management
remains separate. No backend/SQL/migration, tenant-role changes, curation, scoring,
live providers, working-data changes, publishing or deployment in this task.

| ID | Observable criterion | Required evidence | Result |
|---|---|---|---|
| AC1 | Authorized list/filter/paging/empty/error use server rows and status; other planes neither fetch nor display cached operator data | Offline behavior; actual migrated HTTP/Chrome | Passed |
| AC2 | Creation persists across reload/restart; input/conflict/CSRF/403/deadline/service failures settle without false success and recover | Regression; browser/API | Passed |
| AC3 | Confirmed target deletion revokes its sessions, preserves another operator, and handles self deletion honestly | Offline guards; two-operator HTTP/Chrome | Passed |
| AC4 | Duplicate/late responses across navigation/accounts, stale sessions and malformed data preserve privacy and existing flows | Offline regressions; real Chrome session loss; full pytest; review/preservation | Passed |

Required: intended red regression, focused/full project pytest, offline JS,
real migrated scratch HTTP/restart and Chrome with capture/fake providers,
bindings/syntax, recorded separate specification/correctness self-review.
No PostgreSQL gate unless implementation changes SQL/transaction/migrations.

### <a id="r3-s2-t2--evidence-and-review"></a>Evidence and review

Intended red: `node --test --test-name-pattern='operator account landing'
scripts/test_ui_admin_users.js`: **1 failed**, expected `/admin/users` GET,
received none (`.pytest_cache/r3-s2-t2-red.txt`). Final offline Node command
`node --test scripts/test_ui_admin_users.js`: **36/36**, including 22 inherited
evaluate/client checks; permanent pytest wrapper executes it offline.

Separate same-agent review of HEAD `5480498` plus the bounded session delta:
five code-file hashes and diff recorded by project Python
`.pytest_cache/review_r3_s2_t2.py` in `.pytest_cache/r3-s2-t2-reviewed.json` and
`r3-s2-t2-session.diff`. Specification pass maps AC1-4 to actual routes and UI
outcomes, omits unsupported role/membership/suspension/device actions, and keeps
own-session controls separate. Correctness pass follows admin/session/CSRF gates,
response validation, encoded target IDs, session cascades, actor/view tokens,
duplicate guarding, malformed/ambiguous replies and secret-free scratch setup.
Self/last-operator deletion remains allowed by the API; explicit confirmation
and actual 401 after self deletion prevent false continuity claims. No backend,
SQL, migration or scoring change; no PostgreSQL gate. No unresolved acceptance
finding in this reviewed scope; this is self-review, not independent review.

Safe runner is `.resume/Scripts/python.exe .pytest_cache/run_r3_s2_t2.py <tag>
<Python arguments>`; it removes inherited DEE configuration and disables live
providers. All checks use project Python, offline fakes or captured synthetic
login. Chrome requires CDN internet; injected 403/503/deadline/held transports
are synthetic, while normal changes, CSRF/actor denials, session revocation and
restart persistence use actual HTTP on migrated 0029 scratch SQLite.

| Layer | Actual command/result | Artifact |
|---|---|---|
| Focused | Safe runner `focused -m pytest -q --tb=short tests/test_ui_admin_users.py tests/test_ui_admin_orgs.py tests/test_ui_evaluate.py tests/test_ui_verification.py tests/test_ui_mount.py tests/test_auth_api.py tests/test_auth_service.py tests/test_auth_store.py tests/test_auth_sessions.py tests/test_cookie_posture.py tests/test_org_scope_guard.py`: **143 passed, 1 warning, 43.69s**, exit 0 | `.pytest_cache/r3-s2-t2-focused.txt` |
| Actual Chrome/HTTP/restart | Safe runner `browser-final scripts/check_ui_admin_users_browser.py`: **29/29**, exit 0, 31.90s; two named operators, real creation/login/conflict/CSRF/404/delete/self-delete, disabled fixture/list paging, denied org/candidate/browser planes, expiry, reload/restart, no console exceptions | `.pytest_cache/r3-s2-t2-browser-final.txt`; initial harness run stopped on a wrong organization-name selector, corrected and fully rerun |
| Full | Safe runner `full` executes project `-m pytest -q --tb=short`: **3384 passed, 479 skipped, 113 warnings, 1507.37s**, exit 0 | `.pytest_cache/r3-s2-t2-full.txt` |
| Existing org Chrome/HTTP/restart | Safe runner `org-browser-retry scripts/check_ui_admin_orgs_browser.py`: **28/28**, exit 0, 57.24s; first parallel run stopped before sign-in rendered, separate complete retry passed | `.pytest_cache/r3-s2-t2-org-browser-retry.txt` |
| Existing evaluate/contact Chrome | Safe runner `evaluate-browser scripts/check_ui_evaluate_browser.py`: **31/31**, exit 0, 52.18s | `.pytest_cache/r3-s2-t2-evaluate-browser.txt` |
| API contracts | Safe runner `contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 40.69s | `.pytest_cache/r3-s2-t2-contract.txt` |
| Static | `node scripts/check_ui_bindings.js`: **552 bindings / 17 states**; `node --check frontend/api.js`, `frontend/support.js`, `scripts/test_ui_admin_users.js`; project `-m compileall -q scripts/check_ui_admin_users_browser.py tests/test_ui_admin_users.py`; `git -c core.safecrlf=false diff --check`: passed | Bindings are separate from browser execution |

### <a id="r3-s2-t2--handoff"></a>Handoff

AC1-4 and all required gates passed on the reviewed hashes. Final project Python
`.pytest_cache/verify_r3_s2_t2.py`: **860 prior files**, working DB,
HEAD/unrelated status and five reviewed hashes preserved; demo health 200.
`.pytest_cache/check_r3_s2_t2_docs.py` checks six records' local links, four
acceptance results and task/sprint/PI/next-task consistency; final diff check
passed. Warnings are existing Starlette/httpx and SQLite expression-index
warnings; conditional skips do not validate omitted environments. Owned app/
Chrome stopped and synthetic evidence retained. No deployment or data cleanup.
No invitation is sent; new operators request their own sign-in code. Listing
is unpaged and mutations have no version precondition. A lost response may
follow a committed change: refresh before retry, and reconfirm deletion.
The API exposes no operator identity on `/auth/me`, self/last-operator deletion
protection, role edit, membership or suspension endpoint. No live-provider or
quality claim. T2 is done; exact next task:
**R3-S2-T3 — Wire taxonomy curation**. R3-S2/PI-R3/F10 remain open.

## <a id="r3-s2-t3"></a>R3-S2-T3 — Wire taxonomy curation

Status: done (2026-10-14). PI/sprint: R3/S2. Audit: F10.
Prerequisite: [R3-S2-T2](#r3-s2-t2), done.

Existing source-owned queue/review/map/create/ignore handlers already call the
API. Resolution claims by text key alone: after ignore and fresh capture, an
older review can consume the replacement item. Existing handlers also need
bounded requests, response validation and navigation/session lifecycle checks.

Split before implementation to keep database and UI validation focused:

| Child | Acceptance contract | Status |
|---|---|---|
| [R3-S2-T3A](#r3-s2-t3a) | Snapshot revisions and atomic opt-in stale-review refusal, migrated SQLite/PostgreSQL/API/restart plus current-browser compatibility | Done |
| [R3-S2-T3B](#r3-s2-t3b) | Require revisions in browser review/ignore; actual accepted/ignored reload, stale conflicts, empty/error/denied states and safe request/view lifecycle | Done |

Parent acceptance: persisted map/create/ignore outcomes, no silent stale
overwrite, real queue values and safe operator-only browser behavior. Ignore
deletes raw observations; it does not retain a rejection list, and fresh input
may reappear. Explicit vocabulary is never inferred from submitted raw text.
Both children passed; each owns its evidence, review and limitations. T3B
supersedes the staged optional HTTP precondition with a required revision and
guarded browser decisions. Internal maintenance callers remain optional.
Working data/demo, prior edits and consent/erasure/static-taxonomy behavior were
preserved. Cross-worker overlay refresh stays R4-S3-T1. Combined sprint acceptance
passed at [R3-S2-Q](#r3-s2-q), which owns final review/gate evidence and child
archiving. R3-S2 is done; PI-R3/F10 remain open. T3A/T3B detailed records are now
archived; this parent retains their scope/status. Next task is R3-S3-T1 in a
separate session.

## <a id="r3-s2-t3a"></a>R3-S2-T3A — Guard curation review snapshots

Status: done (2026-10-13). Parent: [R3-S2-T3](#r3-s2-t3).
Prerequisite: [R3-S2-T2](#r3-s2-t2), done.

### <a id="r3-s2-t3a--contract"></a>Contract

GET `/curation/skills/unmapped` supplies an opaque `review_revision` for the
exact surviving observation set, from the same statement as its display/counts.
POST `/curation/skills/resolve` accepts optional `expected_revision`. A supplied
revision must match the live observations atomically claimed by the DELETE,
with time sampled after lock waits. Changed live sets return generic 409 and
roll back all claimed observations; absent/expired-only terms retain 404.
No raw identifiers or reviewer notes in decision receipts or conflict details.

Use a deterministic SHA256 digest of sorted immutable observation identity,
source, timestamp and display fields; no persisted revision/tombstone/migration.
The optional precondition preserves current callers during the staged UI
transition. T3B must submit revisions and enforce them for HTTP callers;
T3A alone does not protect omitted-precondition requests or complete T3.

| ID | Observable criterion | Required evidence | Result |
|---|---|---|---|
| AC1 | Same live snapshot yields a stable opaque revision; capture/erasure/expiry/replacement changes it even when visible aggregates match | Migrated SQLite/PostgreSQL store regressions; API/restart | Passed |
| AC2 | Supplied stale revisions cannot consume new/surviving observations or approve vocabulary; unchanged revisions succeed; no-live stays 404; alias conflicts roll back | Intended red; service/API/store; actual PostgreSQL competing connections | Passed |
| AC3 | Operator identity, CSRF/plane denials, explicit aliases, static precedence, erasure and legacy callers remain correct without exposing raw receipt data | Focused/full pytest; migrated HTTP/restart; existing actual Chrome | Passed |

Source: `src/app/curation/{schema,store,service}.py`, resolve request/route in
`src/app/api/routes.py`; relevant curation tests and smoke/browser harnesses.
Required: intended failure, focused/full project pytest, actual migrated HTTP
SQLite/PostgreSQL/restart, controlled PostgreSQL locks, current Chrome curation
compatibility, syntax/bindings/diff and separate recorded self-review.
No migration change; existing migrated-store tests cover schema compatibility.
No working migration, raw-data cleanup, live delivery, scoring or deployment.

### <a id="r3-s2-t3a--evidence-and-review"></a>Evidence and review

Intended red: safe project runner `red -m pytest -q --tb=short
tests/test_curation_api.py::test_api_stale_review_cannot_consume_replacement`:
**1 failed, 1 warning, 7.65s**, missing `review_revision` in the actual queue
response (`.pytest_cache/r3-s2-t3a-red.txt`); no fixture/import failure.

Separate same-agent specification/correctness review of HEAD `5480498` plus
the bounded session delta: nine code/test/journey hashes and diff captured in
`.pytest_cache/r3-s2-t3a-reviewed.json` / `r3-s2-t3a-session.diff` by project
Python `.pytest_cache/review_r3_s2_t3a.py`. AC1-3 map to exact observation sets,
same-query display/revision, generic stale 409 rollback, post-lock clock and
unchanged explicit vocabulary/identity/CSRF/erasure gates. Followed route →
service → atomic claim → overlay, current callers and scratch teardown. Optional
preconditions are deliberate staged compatibility, not full stale-review
protection. The list now reads members for each selected term to compute exact
revisions: term paging does not bound observations per term; aggregate resource
limits remain PI-R4. Concurrent capture after the DELETE statement snapshot can
remain a later queue item. No persisted revision/raw receipt or schema migration,
no cross-worker overlay claim. No unresolved acceptance-blocking finding in this
bounded diff; this is self-review, not independent review.

Safe runner `.resume/Scripts/python.exe .pytest_cache/run_r3_s2_t3a.py <tag>
<Python arguments>` removes inherited DEE settings and disables live providers.
Chrome requires CDN internet; capture/fake providers are not live validation.
`focused` arguments: `-m pytest -q --tb=short tests/test_curation_api.py
tests/test_curation_schema.py tests/test_curation_service.py
tests/test_curation_review_revisions.py tests/test_curation_owned_store.py
tests/test_curation_activation.py tests/test_curation_overlay.py
tests/test_curation_input_boundary.py tests/test_curation_capture.py
tests/test_curation_store.py tests/test_curation_storage_migration.py`.

| Layer | Actual command/result | Artifact |
|---|---|---|
| Focused SQLite/offline | Safe runner `focused` above: **108 passed, 85 skipped, 69 warnings, 76.56s**, exit 0 | `.pytest_cache/r3-s2-t3a-focused.txt` |
| Actual PostgreSQL | Project Python `.pytest_cache/run_r3_s2_t3a_postgres.py`: **166 passed, 17 skipped, 69 warnings, 327.58s**, focused exit 0; PG 18.6, READ COMMITTED, Asia/Calcutta; controlled expiry/erasure/competing-review waits, existing owned migrations/constraints up/down/up | `.pytest_cache/r3-s2-t3a-pg-focused.txt`; runner selects revision/owned/storage/API/activation/service/schema/input-boundary files |
| HTTP/restart | Safe runner `http scripts/smoke_r3_s2_t3a.py`: **24/24**, exit 0, 9.48s; PG runner executes same script with `--postgres`: **24/24**, exit 0, 32.44s; actual two captured operator sessions, stale replacement/partial erasure, map/create/ignore, CSRF/plane/revocation denials and startup/restart persistence | `.pytest_cache/r3-s2-t3a-http.txt`, `r3-s2-t3a-pg-http.txt` |
| Actual Chrome compatibility | Safe runner `browser scripts/check_ui_curation_browser.py`: **28/28**, exit 0, 37.77s; current optional-precondition flow, actual map/create/ignore/reload/conflict/network/expiry/erasure/session-loss and no console exceptions | `.pytest_cache/r3-s2-t3a-browser.txt`; does not prove guarded UI behavior (T3B) |
| API contracts | Safe runner `contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 17.54s | `.pytest_cache/r3-s2-t3a-contract.txt` |
| Full | Safe runner `full` executes project `-m pytest -q --tb=short`: **3399 passed, 496 skipped, 127 warnings, 898.80s**, exit 0 | `.pytest_cache/r3-s2-t3a-full.txt` |
| Static | `node scripts/check_ui_bindings.js`: **552 bindings / 17 states**; `node --check frontend/api.js`, `frontend/support.js`; project `-m compileall -q src/app/curation src/app/api/routes.py tests/test_curation_review_revisions.py scripts/smoke_r3_s2_t3a.py`; `git -c core.safecrlf=false diff --check`: passed | Bindings are separate from browser execution |

Warnings are existing Starlette/httpx deprecation and SQLite expression-index
reflection/autogeneration warnings; conditional skips do not validate other
omitted environments. No migrations changed or applied to the working database.
PG `pg_ctl stop`'s initial 30s wait timed out during checkpoint (exit 1);
subsequent status returned no server (exit 3), owned port was closed and PID file
absent; server log confirms completed shutdown. No force-kill/restart/retest was
needed. Metadata: `.pytest_cache/r3-s2-t3a-pg-runtime.json`.

### <a id="r3-s2-t3a--handoff"></a>Handoff

AC1-3 and all required gates passed on the nine reviewed hashes. Final project
Python `.pytest_cache/verify_r3_s2_t3a.py`: **861 prior files**, working DB,
HEAD/unrelated status and reviewed code preserved; demo health 200. Project
Python `.pytest_cache/check_r3_s2_t3a_docs.py` checks six records' local links,
three acceptance results and child/parent/sprint/PI/next-task consistency; final
diff check passed. Owned HTTP/Chrome/PG stopped; synthetic evidence retained.
No working migration, data cleanup, deployment, independent review, live-provider
or quality claim. The preserved reload-disabled demo still serves its earlier
backend; new guard validation used freshly started migrated scratch apps.
HTTP preconditions remain optional and current UI requests omit them. Exact next
task: [R3-S2-T3B](#r3-s2-t3b), require/use guarded HTTP/browser decisions and
finish request/privacy lifecycle. Parent T3, R3-S2, PI-R3 and F10 remain open.
Stop after this child.

## <a id="r3-s2-t3b"></a>R3-S2-T3B — Complete guarded curation browser reviews

Status: done (2026-10-14). Parent: [R3-S2-T3](#r3-s2-t3).
Prerequisite: [R3-S2-T3A](#r3-s2-t3a).

### <a id="r3-s2-t3b--contract"></a>Contract

Use each loaded term's `review_revision` for review/map/create/ignore; refuse
missing revisions and prevent stale conflicts from silently retrying fresh
observations. Review accepted and ignored results through actual reload/restart;
ignore remains raw deletion, with later submissions allowed. Preserve explicit
blank approved aliases, static precedence and raw-free decision receipts.

Add bounded request deadlines and response validation. Guard duplicate actions,
refresh/page races, actor/view changes and stale session callbacks. Clear raw
queue/editor state on navigation/session loss; denied planes must neither fetch
nor render cached queue data. Show honest loading/empty/errors/conflicts and
ambiguous-write recovery; counts must come from server observations. Require
`expected_revision` on HTTP resolution after updating shipped clients and
relevant API tests/smokes; omitted/null revisions must refuse before mutation.
Record that compatibility transition. Internal store/service callers may retain
their explicitly unguarded maintenance contract. No unrelated UI redesign or
cross-worker overlay machinery.

Acceptance: offline shipped-handler regressions, focused/full pytest, real
Chrome queue → map/create/ignore → reload, stale two-reviewer/fresh-capture
conflict, paging/empty/error/denied/stale-session behavior, actual migrated
HTTP/restart/CSRF/identity and normalization, bindings/syntax and separate diff
self-review. PostgreSQL gate if SQL/transaction behavior changes beyond T3A.
Record commands/counts here when implementation starts. No working-data/demo
change, live provider, deployment or empirical quality claim. Close parent only
after required evidence; exact following task is R3-S2-Q in a separate session.

| ID | Observable criterion | Required evidence | Result |
|---|---|---|---|
| AC1 | Browser map/create/ignore submit the loaded revision; missing/null HTTP preconditions refuse before mutation; decisions persist on reload/restart | Intended red; offline JS; API/actual HTTP/Chrome | Passed |
| AC2 | Stale review/fresh capture and erasure/expiry conflicts never silently rebind a draft; alias conflicts/invalid input retain a usable review; uncertain writes require a successful read before retry | Offline regressions; real two-reviewer Chrome/HTTP; faults | Passed |
| AC3 | Loading/empty/page/error values come from validated live responses; duplicate requests, invalid replies and deadlines settle; read-only refresh recovers uncertain writes | Offline handlers/client; Chrome rendered states; contracts | Passed |
| AC4 | Navigation/session loss clear raw queue/drafts and invalidate old replies; unmount invalidates replies; non-operators do not fetch/render cached queue; existing workflows/data remain | Offline race/plane regressions; Chrome session/plane/navigation; focused/full pytest; self-review/preservation | Passed |

Use existing source-owned stores/revisions and the API client deadline, with
20-term server paging. No SQL/transaction/migration change is planned; T3A owns
the database-lock implementation/gates. The request schema becomes deliberately
incompatible with old resolution clients: read the queue and send its revision.
Unknown/missing terms with well-formed revisions still return 404. Lost responses
do not prove rollback; refresh before another explicit decision. One child per
session; do not start Q.

### <a id="r3-s2-t3b--evidence-and-review"></a>Evidence and review

Intended red: `node --test --test-name-pattern='guarded browser decision'
scripts/test_ui_curation.js`: **1 failed**, POST omitted the loaded revision
(`.pytest_cache/r3-s2-t3b-ui-red.txt`). Safe project runner `api-red -m pytest
-q --tb=short tests/test_curation_api.py::test_http_resolution_requires_revision_before_mutation`:
**1 failed, 1 warning, 8.70s**, omitted precondition committed ignore (200 instead
of 422; `.pytest_cache/r3-s2-t3b-api-red.txt`). Both failed for intended behavior.

Separate same-agent specification/correctness review of HEAD `5480498` plus
13 bounded code/test/journey file hashes and session diff in
`.pytest_cache/r3-s2-t3b-reviewed.json` / `r3-s2-t3b-session.diff`, captured by
project Python `.pytest_cache/review_r3_s2_t3b.py`. Reviewed AC1-4 through shipped
handlers/client → required request schema → unchanged T3A atomic claim/overlay,
all resolution HTTP callers, authenticated identity/CSRF, exact snapshot use,
page/receipt validation, actor/view/load/action tokens and scratch teardown.
No SQL/store/migration/scorer change; no new PostgreSQL lock/migration gate.

**Medium finding, `frontend/Veritas.dc.html`, `loadCuration` catch:** failed
recovery GET after an uncertain decision discarded the retained approval draft.
Fixed by preserving the read-only selection/draft until a successful read can
confirm its revision or remove it. Read-only VM reproduction substitutes only
the prior reset branch: `node --test --test-name-pattern='uncertain write'
.pytest_cache/repro_r3_s2_t3b_review.js`: **3 failed** on lost alias; final shipped
offline checks **41/41** and final Chrome includes failed-read draft retention.
No unresolved acceptance-blocking finding in this reviewed scope. This is
self-review, not independent review. Stage A's optional HTTP compatibility is
superseded: old clients must now fetch and send revisions; direct internal
store/service callers remain optional. No live-provider or quality claim.

Offline Node: `node --test scripts/test_ui_curation.js`: **41/41**, including 22
inherited evaluate/client checks. First expanded run had two harness mismatches
(CSRF's established sign-in copy and a device-list fake shape); corrected and
fully rerun. Permanent `tests/test_ui_curation.py` runs the shipped JS offline.
All app/store evidence uses migrated scratch, synthetic capture/fake providers;
Chrome requires CDN internet. Safe runner is project Python
`.pytest_cache/run_r3_s2_t3b.py <tag> <Python arguments>`, clearing inherited DEE
configuration/providers. Final required checks passed on the reviewed hashes.

Focused arguments: `-m pytest -q --tb=short tests/test_curation_api.py
tests/test_curation_activation.py tests/test_curation_service.py
tests/test_curation_review_revisions.py tests/test_ui_curation.py
tests/test_ui_admin_orgs.py tests/test_ui_admin_users.py tests/test_ui_evaluate.py
tests/test_ui_verification.py tests/test_ui_mount.py tests/test_auth_api.py
tests/test_auth_sessions.py tests/test_cookie_posture.py tests/test_org_scope_guard.py`.

| Layer | Actual command/result | Artifact |
|---|---|---|
| Focused | Safe runner `focused-final` with arguments above: **115 passed, 17 skipped, 15 warnings, 131.28s**, exit 0 | `.pytest_cache/r3-s2-t3b-focused-final.txt` |
| Actual Chrome/HTTP/restart | Safe runner `browser-final scripts/check_ui_curation_browser.py`: **46/46**, exit 0, 116.47s; real map/create/ignore/reload/restart, two reviewers/fresh-capture conflict, paging/empty/invalid/refused reads, uncertain/failed-read recovery, late-view save, expiry/erasure/revocation and real org/candidate browser plane denials; no console exceptions | `.pytest_cache/r3-s2-t3b-browser-final.txt`; transport faults/held dispatch are synthetic |
| PostgreSQL compatibility/API | Project Python `.pytest_cache/run_r3_s2_t3b_postgres.py`: **20 passed, 1 warning, 76.06s**, API/activation; actual migrated PG HTTP/restart uses `scripts/smoke_r3_s2_t3a.py --postgres`: **26/26**, exit 0, 47.02s; two operators, missing/null/stale refusal, attribution/CSRF/planes, persisted normalization/revocation | `.pytest_cache/r3-s2-t3b-pg-focused.txt`, `r3-s2-t3b-pg-http.txt`; PG 18.6 / READ COMMITTED / Asia/Calcutta; owned stop exit 0 |
| Existing journeys/callers | Safe runner `evaluate-browser scripts/check_ui_evaluate_browser.py`: **31/31**, exit 0, 49.87s; `contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 38.44s; `input-http scripts/smoke_curation_input.py`: **13/13**, exit 0, 39.71s; `erasure-http scripts/smoke_r1_s1_t3b_d3d2d3.py`: **15/15**, exit 0; historical S63 scratch smoke: **16/16 / SMOKE OK**, exit 0, 22.73s | Corresponding `.pytest_cache/r3-s2-t3b-<tag>.txt`; S63 uses a session-only free-port/hidden-child adapter via safe runner `s63 -c "import runpy,sys; sys.path.insert(0,'scripts'); runpy.run_path('.pytest_cache/run_r3_s2_t3b_s63.py',run_name='__main__')"` |
| Full | Safe runner `full`, project `-m pytest -q --tb=short`: **3401 passed, 496 skipped, 127 warnings, 1797.13s**, exit 0 | `.pytest_cache/r3-s2-t3b-full.txt` |
| Static | `node scripts/check_ui_bindings.js`: **559 bindings / 17 states**; `node --check frontend/api.js`, `frontend/support.js`, `scripts/test_ui_curation.js`; project `-m compileall -q` on 10 changed Python files; `git -c core.safecrlf=false diff --check`: passed | Compile arguments: `scripts/check_ui_curation_browser.py scripts/smoke_curation_activation.py scripts/smoke_curation_input.py scripts/smoke_s63.py scripts/smoke_r1_s1_t3b_d3d2d3.py scripts/smoke_r3_s2_t3a.py tests/test_ui_curation.py tests/test_curation_api.py tests/test_curation_activation.py src/app/api/routes.py` |

PG checks confirm compatibility, not a new whole-suite/migration/lock gate; SQL
hashes stayed unchanged and T3A owns that gate. Earlier Chrome runs passed 38/38
then 45/45 before the review fix; final 46/46 owns current evidence. Warnings are
existing Starlette/httpx and SQLite expression-index warnings; skips do not prove
omitted environments. Term paging does not cap observations per term, updates remain process-
local and later concurrent capture can form another item. These are unchanged
R4/resource/snapshot limits, not guarantees of quality or global synchronization.

### <a id="r3-s2-t3b--handoff"></a>Handoff

AC1-4, all required gates and review fixes passed. Final project Python
`.pytest_cache/verify_r3_s2_t3b.py`: **858 prior files**, working DB,
HEAD/unrelated status and 13 reviewed hashes preserved; demo health 200; owned PG
stop exit 0. Project Python `.pytest_cache/check_r3_s2_t3b_docs.py` checks seven
records' links, four acceptance results and closed T3/open Q/sprint/PI/next-task
consistency; final diff check passed. Owned app/Chrome/PG stopped; synthetic
evidence retained. No working migration, deployment, data cleanup, independent
review, live-provider or measured-quality claim. The preserved reload-disabled
demo's older backend remains separate from fresh migrated validation apps.
T3A/T3B and parent T3 are done. R3-S2, PI-R3 and F10 remain open. Exact next task:
**R3-S2-Q — Sprint integration review**, in a separate session; not started here.

## <a id="r3-s3-q"></a>R3-S3-Q — Sprint integration review

Status: done (2026-10-16). Prerequisites: T1, T2A/T2B/parent T2, T3 done.
Scope: combined R3-S3 acceptance; no next-sprint work or working-data migration.

### <a id="r3-s3-q--acceptance-and-validation-contract"></a>Acceptance and validation contract

- AC1: One actual browser candidate saves typed and synthetic microphone answers
  in the same interview, reloads/resumes, finishes and sees the persisted advisory
  assessment, scorer version and evidence limitations. Known keyword repetition
  cannot produce strong evidence. Historical/mixed version explanations remain.
- AC2: Recording, ASR refusal/timeout, uncertain acknowledgements, duplicate/stale
  questions, navigation and account changes agree with saved state. Read-only
  recovery never replays a write; devices and private drafts/clips are cleared.
- AC3: Authorized employer HTTP reads expose only consent-permitted versioned
  summaries, without transcripts/turns/raw media; revocation/restart/erasure and
  another candidate's access remain isolated. Mixed text/audio data survives a
  real child-app restart exactly, and erased rows disappear.
- AC4: Review the combined sprint application/test/journey diff separately from
  implementation; run focused/full project pytest, actual Chrome, migrated
  SQLite/PostgreSQL HTTP and controlled PG lifecycle/erasure locks, relevant
  migration regressions, Node handlers/bindings/syntax and whitespace checks.

Reuse existing fake providers, synthetic media, capture login and owned scratch
stores/processes. No live ASR/codec compatibility, independent review, population
accuracy, video/appearance/emotion scoring, deployment or user-data cleanup is
claimed. Preserve prior uncommitted files, working DB and running demo. Missing
required evidence leaves Q awaiting validation. Exact evidence and findings below.

### <a id="r3-s3-q--evidence-and-review"></a>Evidence and review

Before work, captured 897 prior files/status/HEAD in the ignored
`.pytest_cache/r3-s3-q-before/` snapshot. Safe runner:
`.resume/Scripts/python.exe .pytest_cache/run_r3_s3_q.py <tag> <Python arguments>`;
omitted arguments run project `-m pytest -q --tb=short`. It clears inherited DEE
configuration and disables live providers. New browser journey is
`scripts/check_ui_interview_integration_browser.py`, reusing T3's real microphone
checks through an optional callback and owned-app restart. Existing
`scripts/smoke_r3_s3_t3.py --combined` now accepts SQLite / `--postgres`, adds typed
continuation/repetition and verifies actual erased rows. No application change.

Separate same-agent specification/correctness review covers the combined sprint
application boundaries: candidate ownership/CSRF, candidate-first locks and live
question/expiry rechecks, atomic final turn/assessment/audit, current consent and
transcript-free employer projection, deterministic rubric eligibility/version
compatibility/capped model fallback, audio validation/redacted provider errors,
private capture cleanup/deadlines and actor/view/action guards. Compared T1's
initial hashes to current sources and Q's initial snapshot to this session:
`.pytest_cache/review_r3_s3_q.py` records combined/session diffs and 31 source/test/
journey hashes in `r3-s3-q-reviewed.json`; 10 application files unchanged in Q.
No new unresolved acceptance-blocking application finding. This is self-review,
not independent review. Known bounded English heuristics, per-clip limits,
delayed browser timers and duplicate provider work remain explicit limitations.

First browser fixture run (`browser-initial`, exit 1) incorrectly required zero
aggregate confidence despite valid audio evidence, compared a full assessment
to a summary projection, and lost its own device instrumentation after reload.
Corrected eligibility/projection assertions and reinstalled instrumentation;
rerun passed. These were test-harness findings, not application regressions or
claimed defect reproductions. Native combined SQLite HTTP passed 23/23 (43.04s).
Low evidence-helper finding: T1 hashed all files but copied only its touched
subset. The first helper treated absent copies as additions and its stricter
verifier then refused the missing frontend copy. Regenerated the combined diff
from available earlier snapshots only where SHA256 matches T1's original hash;
`r3-s3-q-baseline-origins.json` records each verified source or explicit addition.
The final baseline/preservation verification passed; all 31 executable hashes
remained identical, so this artifact correction changes no tested code.
Low documentation finding: the previous archive count included its README.
Corrected the index to **49 detailed records** after the four leaf moves;
the final checker compares the actual inventory to the pre-session files.
All required test gates passed. Chrome uses the existing CDN runtime and requires
internet; external assessment/transcription/delivery providers remain fake.

Focused arguments: `-m pytest -q --tb=short tests/test_interview_scoring.py
tests/test_interview_scoring_llm.py tests/test_interview_service.py
tests/test_interview_api.py tests/test_interview_store.py tests/test_interview_org.py
tests/test_interview_org_api.py tests/test_interview_erasure.py
tests/test_interview_erasure_concurrency.py tests/test_interview_lifecycle_concurrency.py
tests/test_speech_seam.py tests/test_ui_interview.py tests/test_ui_interview_audio.py
tests/test_migrations.py`.

| Layer | Actual command/result | Artifact |
|---|---|---|
| Focused | Safe runner `focused` with arguments above: **175 passed, 16 skipped, 16 warnings, 166.74s**, exit 0 | `.pytest_cache/r3-s3-q-focused.txt` |
| Combined Chrome/SQLite/restart | Safe runner `browser scripts/check_ui_interview_integration_browser.py`: **40/40**, exit 0, 140.40s; includes 29 inherited microphone checks and 11 combined text/audio/employer/restart checks; no console exceptions | `.pytest_cache/r3-s3-q-browser.txt` |
| Text Chrome/history/errors | Safe runner `text-browser scripts/check_ui_interview_browser.py`: **36/36**, exit 0, 59.81s; historical/mixed/limited/relevance fixtures, chosen domain, read-only errors, CSRF and actor loss | `.pytest_cache/r3-s3-q-text-browser.txt` |
| Combined SQLite HTTP | Safe runner `http scripts/smoke_r3_s3_t3.py --combined`: **23/23**, exit 0, 43.04s | `.pytest_cache/r3-s3-q-http.txt` |
| SQLite rubric/history HTTP | Safe runner `rubric-http scripts/smoke_r3_s3_t1.py`: **28/28**, exit 0, 35.07s; positive substantive/concise examples, complete repetition refusal, v1/mixed persistence, consent/restart/erasure | `.pytest_cache/r3-s3-q-rubric-http.txt` |
| PostgreSQL locks/migrations | Project Python `.pytest_cache/run_r3_s3_q_postgres.py`: interview store/service/API/org/erasure/lifecycle plus candidate-login and curation migration regressions: **142 passed, 4 skipped, 21 warnings, 376.58s**, exit 0; PG 18.6 / READ COMMITTED / Asia/Calcutta; actual competing locks/erasure, constraints and existing up/down/up | `.pytest_cache/r3-s3-q-pg-focused.txt` |
| Combined PostgreSQL HTTP | Same owned runner invokes `scripts/smoke_r3_s3_t3.py --combined --postgres`: **23/23**, exit 0, 42.74s | `.pytest_cache/r3-s3-q-pg-http.txt` |
| PostgreSQL rubric/history HTTP | Same owned runner invokes `scripts/smoke_r3_s3_t1.py --postgres`: **28/28**, exit 0, 36.97s; owned PG stop exit 0 (41.26s) | `.pytest_cache/r3-s3-q-pg-rubric-http.txt`, `r3-s3-q-pg-runtime.json` |
| Original audio HTTP compatibility | Safe runner `audio-default scripts/smoke_r3_s3_t3.py`: **20/20**, exit 0, 39.21s | `.pytest_cache/r3-s3-q-audio-default.txt` |
| Cookie/CSRF contracts | Safe runner `contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 56.81s | `.pytest_cache/r3-s3-q-contract.txt` |
| Offline handlers | `node --test scripts/test_ui_interview_audio.js`: **64/64**, exit 0, 753.12ms (23 microphone plus 41 inherited text/client/evaluation cases) | Executed shipped handlers; separate from Chrome |
| Full pytest | Safe runner `full`, project `-m pytest -q --tb=short`: **3458 passed, 505 skipped, 127 warnings, 1558.60s**, exit 0, on the final reviewed source | `.pytest_cache/r3-s3-q-full.txt` |
| Static | `node scripts/check_ui_bindings.js`: **589 bindings / 18 states**; `node --check frontend/api.js`, `frontend/support.js`; project `-m compileall -q scripts/check_ui_interview_audio_browser.py scripts/check_ui_interview_integration_browser.py scripts/smoke_r3_s3_t3.py`; `git -c core.safecrlf=false diff --check`: passed | Separate from browser execution |

### <a id="r3-s3-q--handoff"></a>Handoff

AC1-4, required gates and separate combined self-review passed. Q, R3-S3 and PI-R3
are done within their bounded scope. Detailed T1/T2A/T2B/T3 records are archived;
T2's group summary remains in `tasks/`. No application/SQL/schema/dependency or
working migration change in Q. Warnings are existing Starlette/httpx and SQLite
expression-index warnings; conditional skips do not prove omitted environments.
Chrome uses synthetic microphone input and fake ASR; employer checks use the
actual HTTP summary API, not an employer interview UI or live-provider proof.
No independent review, measured quality, appearance/emotion scoring or deployment.

Unpaged history, snapshot delivery, ambiguous writes, duplicate provider work,
per-clip rather than aggregate limits, delayed browser timers, uncancelable media
permission requests and bounded English heuristics remain. The preserved demo's
older backend still needs its separately controlled restart. F10's broader
browser regression remains R5-S2-T1; F11 video and quality remain PI-R5.
Final project Python `.pytest_cache/verify_r3_s3_q.py --closed`: **855 unrelated
prior files**, working DB/HEAD/unrelated status and **31 reviewed hashes**
preserved; verified pre-sprint baseline hashes, demo health 200, owned PG stopped.
**13 documents / 315 local links**, added-line whitespace, task/next-pointer and
49-record archive inventory passed. Archived leaf contents differ only in repaired
links. Final `git -c core.safecrlf=false diff --check` and changed executable-line
whitespace checks passed. Owned app/Chrome/PG stopped; synthetic evidence retained.
No working migration, user-data cleanup or deployment occurred.

Exact next task: **R4-S1-T1 — Share database and service resources**, not started.
Stop after Q; do not begin the next task in this session.

## <a id="r3-s3-t1"></a>R3-S3-T1 — Repair and version the interview rubric

Status: done (2026-10-15). PI/sprint: R3/S3. Audit: F11.
Prerequisite: [R3-S2-Q](#r3-s2-q), done.

### <a id="r3-s3-t1--contract"></a>Contract

Replace token/pronoun counts and profile-word corroboration with a bounded,
deterministic content rubric over distinct substantive clauses. Repetition,
copied prompts, isolated expected terms and unrelated fluent prose cannot earn
a strong band or increase confidence merely by adding words. Recognize a small
explicit set of reasoning paraphrases; unrecognized relevance is uncertainty,
not evidence of poor ability. Keep missing yardsticks/profile evidence neutral.
Accept concise substantive answers and collaborative accounts. Freeze synthetic
development examples with observable expectations; these are not held-out
quality data or proof of real-world scoring accuracy.

Stamp new turn/assessment versions and evidence confidence. Preserve completed
historical JSON scores; retain legacy aggregation for wholly legacy sessions
and refuse a confident mixed-version assessment. Keep capped optional model
adjustments, whole-reply validation and deterministic fallbacks. No appearance,
emotion, stylistic fabrication inference or resume-score fusion. No UI lifecycle,
microphone, working migration/data/demo change, deployment or live provider.

| ID | Observable criterion | Required evidence | Result |
|---|---|---|---|
| AC1 | Known repeated-keyword exploit, copied prompts, padding and fluent unrelated prose cannot earn strong scores/confidence | Intended red; frozen examples; aggregation/LLM regressions | Passed |
| AC2 | Distinct action/reason/outcome evidence, concise paraphrases and non-software examples remain usable; missing relevance/profile stays neutral | Frozen rubric fixtures; focused pytest | Passed |
| AC3 | New versions/confidence persist; completed historical values survive reload/restart; mixed versions do not silently blend; model failures preserve baseline | Store/service/API tests; actual migrated HTTP/restart with fakes/two actors | Passed |
| AC4 | Advisory/consent/ownership/transcript boundaries and existing flows/data remain; final diff reviewed separately | Focused/full pytest; HTTP/contract/static; self-review/preservation | Passed |

Use existing JSON score storage; no SQL/transaction/migration change planned,
so no new PostgreSQL lock/migration gate. Browser gate applies if a visible
screen/handler changes; T2 owns the still-prototype interview UI. Run bindings
and existing API contracts separately. Record actual commands/counts below.

### <a id="r3-s3-t1--evidence-and-review"></a>Evidence and review

Intended red: safe runner `red -m pytest -q --tb=short
tests/test_interview_scoring.py::test_keyword_repetition_never_earns_a_strong_band`:
**1 failed, 3.55s**, old `s73.1` produced `deep` / overall 1.0 for the exact
repeated phrase (`.pytest_cache/r3-s3-t1-red.txt`). No import/fixture failure is
claimed as reproduction. Five old assertions intentionally encoding token,
pronoun/profile-name rewards or unversioned-current aggregation were revised
to the new contract; missing passive-action recognition was fixed, not relabeled.

New `s73.2` reports distinct action/object clauses, reasoning stages and bounded
paraphrase anchors. Factual consistency stays neutral; collaborative or passive
ownership stays unknown, with no pronoun-frequency reward. Repeated/copied clauses
and word padding add no credit; concise substantive clauses remain usable.
Unknown relevance caps evidence and cannot alone earn a band even with a zero
confidence threshold. Models preserve unknown axes/version/confidence and retain
strict whole-reply fallback. Existing JSON scores carry new turn metadata; new
summary version is additive. Completed legacy JSON stays unchanged; wholly
legacy aggregation stays v1, mixed/unsupported versions refuse a confident blend.
No schema/SQL/migration change. English lexical heuristics may miss valid phrasing
or over-credit plausible prose; no general semantic/factual accuracy claim.

Separate same-agent specification/correctness self-review of HEAD `5480498` plus
11 file hashes and bounded session diff in `.pytest_cache/r3-s3-t1-reviewed.json`
/ `r3-s3-t1-session.diff`, captured by project Python
`.pytest_cache/review_r3_s3_t1.py`. Specification maps AC1-4 to frozen examples,
content/uncertainty/model gates, saved versions/history and actual actor/consent/
erasure journeys. Correctness follows question context through service scoring,
provider member validation, immutable metadata, legacy/mixed aggregation, existing
16-character version storage, transcript-free summary projection, unchanged
store/CSRF/ownership boundaries and isolated scratch setup/owned teardown.

Medium finding, `scoring.py` clause segmentation: coordinated single-sentence
paraphrases received less credit than identical semicolon clauses. Regression
`review-red -m pytest -q --tb=short tests/test_interview_scoring.py::test_substantive_clause_credit_is_not_a_punctuation_preference`:
**1 failed, 2.41s**, specificity 0.3333 vs 1.0. Action-aware coordinated-clause
splitting fixes it and preserves decimal metrics. A proposed mixed-version label
also exceeded the existing 16-character store column; compact `mixed/unknown`,
length regression and real PG persistence validate the final representation.
No unresolved acceptance-blocking finding in this review; self-review, not
independent review. No appearance/emotion, proxy rubric, scoring fusion or UI
lifecycle change. Frozen examples are synthetic development data, not quality
evaluation. No new PostgreSQL lock/migration gate; real PG is compatibility evidence.

Medium finding, `score_turn` relevance branch: an empty expected-signal list
left fluent unrelated content at a solid band. Safe runner
`review-relevance-red -m pytest -q --tb=short tests/test_interview_scoring.py::test_unrelated_answer_is_not_rescued_by_a_missing_signal_yardstick`:
**1 failed, 2.63s**, `solid` / overall 0.7222. Relevance now uses question topic
anchors independently of the depth yardstick; generic template wording and
profile names are not required passwords. The new actual profile-template test
also caught trailing question punctuation leaking through the topic filter;
token normalization fixes it. Corrected scoring/LLM checks passed before final
runs restarted. The provisional full run was stopped at 18% for these fixes;
its partial log and earlier PG results are retained as
`.pytest_cache/r3-s3-t1-provisional-*`, not final passing evidence. Re-captured
10 rubric/journey hashes; re-ran focused and actual SQLite/PG HTTP on that state.

Full regression then exposed an existing test-clock defect outside interview
code: `tests/test_features_current_consent.py::seed` granted through 2026-10-15
but submitted seed ledger/coding records at wall time, while export assertions
used pinned NOW. On 15 October seed setup correctly refused expired write consent.
Safe runner `full-failure -m pytest -q --tb=short tests/test_features_current_consent.py::test_revoked_feature_csv_does_not_trust_cached_consent`:
**1 failed, 1 skipped, 6.36s**, `ConsentError` before assertions. Fixed only the
two seed submissions with explicit `now=NOW`; production consent logic is
unchanged. Preserved that file's original bytes for review and the failed full
log in `.pytest_cache/r3-s3-t1-full-fixture-failure.txt`. The affected fixture
suite and final full regression were restarted; final review has 11 hashes.

Medium finding, single-clause eligibility: repeating a short qualifying clause
crossed the raw word floor and raised evidence confidence from 0 to 0.55.
`review-floor-red -m pytest -q --tb=short tests/test_interview_scoring.py::test_repetition_or_filler_cannot_cross_a_single_clause_word_floor`:
**1 failed, 3.64s**. Single-clause turns now supply zero assessment evidence at
any length. Unrelated/limited turns are excluded from current dimension means
and confidence; sum evidence/planned avoids rounding-induced increases when
unsupported turns merely change progress. Legacy math remains exact. The new
partial-versus-padded full-session regression and actual HTTP scenario validate
both score and confidence invariance. **338 focused tests passed**; prior clean
partial full log is retained in `r3-s3-t1-full-before-evidence-review.txt` and
earlier PG artifacts in `r3-s3-t1-pre-eligibility-pg-*`. Re-captured final 11
hashes and restarted required full/current HTTP/PG checks after the fix.

Medium finding, generic profile-template relevance: "compared" alone anchored
an unrelated garden story after profile-name exclusion. `review-profile-red -m
pytest -q --tb=short tests/test_interview_scoring.py::test_profile_template_does_not_accept_a_generic_investigation_cue_as_relevance`:
**1 failed, 2.77s**, `deep` / overall 0.8889. Generic templates now require a
specific contextual signal or two distinct procedural cues; the nameless
substantive paraphrase still passes. Real unmodified profile/domain questions
are additionally exercised through HTTP. Final **339 focused tests passed**;
prior partial full/PG artifacts are retained as `full-before-template-review`
and `pre-template-pg-*` under the task prefix. Final 11 hashes were re-captured
and full/HTTP/PG checks restarted. No broader semantic-accuracy claim is made.

Safe runner: `.resume/Scripts/python.exe .pytest_cache/run_r3_s3_t1.py <tag>
<Python arguments>` removes inherited DEE configuration and disables providers;
no arguments after tag runs project `-m pytest -q --tb=short`. Normal HTTP journeys
use migrated 0029 scratch app composition, fake models and explicit synthetic
question/history fixtures (not a question-planner quality claim). Node bindings,
API contracts and existing evaluate/contact Chrome are separate compatibility
checks; the still-prototype interview UI is T2, not a browser-scoring claim.

Focused arguments: `-m pytest -q --tb=short tests/test_interview_scoring.py
tests/test_interview_scoring_llm.py tests/test_interview_schema.py
tests/test_interview_service.py tests/test_interview_store.py tests/test_interview_api.py
tests/test_interview_org.py tests/test_interview_review.py tests/test_interview_questions.py
tests/test_interview_proxy.py tests/test_config_interview.py tests/test_model_output_boundaries.py`.

| Layer | Actual command/result | Artifact |
|---|---|---|
| Focused | Safe runner `final-focused` with arguments above: **339 passed, 1 warning, 49.38s**, exit 0 | `.pytest_cache/r3-s3-t1-final-focused.txt` |
| Migrated SQLite HTTP/restart | Safe runner `http-reviewed scripts/smoke_r3_s3_t1.py`: **20/20**, exit 0, 54.31s; exploit/concise/empty-yardstick/partial evidence/native question plan, version/history/mixed, two-candidate isolation, org consent/projection/revocation and erasure | `.pytest_cache/r3-s3-t1-http-reviewed.txt` |
| PostgreSQL compatibility | Project Python `.pytest_cache/run_r3_s3_t1_postgres.py`: **58 passed, 1 warning, 8988.46s reported elapsed**, exit 0; actual HTTP/restart `--postgres` **20/20**, exit 0, 29.02s; PG 18.6 / READ COMMITTED / Asia/Calcutta; owned stop exit 0, 14.50s | `.pytest_cache/r3-s3-t1-pg-focused.txt`, `r3-s3-t1-pg-http.txt`, `r3-s3-t1-pg-runtime.json`; elapsed time is not a performance claim |
| Existing common UI/contract compatibility | Safe runner `evaluate-browser scripts/check_ui_evaluate_browser.py`: **31/31**, exit 0, 47.18s; `contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 33.68s | Corresponding `.pytest_cache/r3-s3-t1-<tag>.txt`; Chrome requires CDN internet, no interview UI execution claim |
| Consent fixture regression | Safe runner `consent-fixture -m pytest -q --tb=short tests/test_features_current_consent.py`: **41 passed, 93 skipped, 147.14s**, exit 0; PostgreSQL/optional-format skips are not environment proof | `.pytest_cache/r3-s3-t1-consent-fixture.txt` |
| Full | Safe runner `full`, project `-m pytest -q --tb=short`: **3430 passed, 496 skipped, 127 warnings, 10117.54s reported elapsed**, exit 0 on final reviewed source | `.pytest_cache/r3-s3-t1-full.txt`; elapsed is not a performance benchmark |
| Static | Bindings **559 / 17 states**, API/support JS syntax, project compileall on interview/new journey/changed tests and `git -c core.safecrlf=false diff --check` passed | Actual browser is separate |

### <a id="r3-s3-t1--handoff"></a>Handoff

AC1-4, required checks and separate self-review passed; T1 is done. No independent,
live-provider, general semantic/factual-accuracy or empirical-quality claim.
Warnings are existing Starlette/httpx and SQLite expression-index warnings;
conditional skips do not prove omitted environments. The English action/object
heuristic can miss valid phrasing or over-credit plausible prose; the later
effectiveness gate remains required. Models cannot validate factual consistency
or change evidence/version metadata. Single-clause/unrelated turns supply no
assessment evidence; raw progress counts remain separate. Completed historical
values stay unchanged, legacy-only aggregation remains v1 and mixed/unsupported
versions remain insufficient. No SQL/store/migration or UI lifecycle change;
the two fixture-clock arguments are a test-only correction. Existing demo uses
its older reload-disabled backend and still needs a separately controlled restart.

Final project Python `.pytest_cache/verify_r3_s3_t1.py`: **867 prior files**,
working DB/HEAD/unrelated status and **11 reviewed hashes** preserved; demo
health 200 and owned PG stopped. Project Python
`.pytest_cache/check_r3_s3_t1_docs.py --closed`: **7 records / 195 local links**,
done T1/open sprint/PI/F11/next-task consistency passed. Final
`git -c core.safecrlf=false diff --check` passed. No application changes followed
the final reviewed regression run.
Owned validation app/Chrome/PG stopped; synthetic artifacts retained. No working
migration, user-data cleanup or deployment. PI-R3/F11 remain open; exact next:
**R3-S3-T2 — Wire interview lifecycle and text answers**, not started. Stop after T1.

## <a id="r3-s3-t2"></a>R3-S3-T2 — Interview lifecycle and text answers

Status: done (2026-10-15). Parent: [PI-R3](PI-R3.md), F11.
Prerequisite: [T1](#r3-s3-t1), done.

Split before implementation because the API checked start/question/status before
asynchronous provider work without rechecking writes under a lock. Concurrent
starts/answers and finish-versus-answer could corrupt saved progress. T2A repaired
that prerequisite before T2B connected the browser.

- [T2A](#r3-s3-t2a) (done): atomic saved lifecycle, conflicts, expiry, recovery
  and actor boundaries. The leaf owns controlled SQLite/PostgreSQL, migrated
  HTTP/restart, full regression, self-review and preservation evidence.
- [T2B](#r3-s3-t2b) (done): real candidate start/list/resume/text/finish,
  saved version/evidence explanations and read-only recovery without replay.
  The leaf owns actual Chrome/API/restart, full regression, self-review and
  preservation evidence; microphone remains T3.

Parent acceptance remains the PI card: reload resumes the correct question;
duplicate/stale/expired actions explain conflicts; completion shows the saved
assessment. Both children passed; T2 and T3 are done. Combined sprint acceptance
passed [R3-S3-Q](#r3-s3-q), closing R3-S3/PI-R3 within scope. F11 retains
PI-R5 video/quality gates. No microphone implementation in T2.

## <a id="r3-s3-t2a"></a>R3-S3-T2A — Atomic saved interview lifecycle

Status: done (2026-10-15). Parent: [T2](#r3-s3-t2).

### <a id="r3-s3-t2a--contract"></a>Contract

Serialize writes using the existing candidate row, including erasure. Recheck
live status and the current question after provider work and lock acquisition.
Conflicting starts/duplicate answers/finishes commit once; reject stale work
with 409. An answer committed before an early finish contributes to its result.
Compute completion from locked saved turns. Commit the last answer, assessment
and completion audit together so a failure cannot leave partial completion.
Do not hold database locks across provider calls. Terminal responses offer no
next question. Reads resume saved state; preserve historical completed values,
tenant/consent/transcript boundaries and advisory scoring.

| ID | Acceptance | Evidence required | Result |
|---|---|---|---|
| AC1 | Competing starts and duplicate answers commit once; stale/wrong questions refuse | Intended red; controlled SQLite/PG competing connections | Passed |
| AC2 | Answer/finish order agrees with stored assessment; final-answer failure rolls back; expiry during provider/lock wait refuses | Service/API regressions, controlled PG locks, rollback assertions | Passed |
| AC3 | Reload/restart returns saved question/outcome; terminal next question null; other actors denied, org summaries transcript-free under consent | Migrated scratch HTTP/restart; API/erasure tests | Passed |
| AC4 | Historical scoring/data/prior edits remain; reviewed final code passes regression | Full pytest; separate diff self-review; preservation/static checks | Passed |

No SQL schema migration, working DB/demo restart, UI handler, microphone or live
provider change. PostgreSQL transaction gates apply; migrations up/down/up only
if schema changes become necessary. T2B owns actual interview browser execution;
source bindings/common browser checks are not that evidence.

### <a id="r3-s3-t2a--evidence-and-review"></a>Evidence and review

Intended red: project Python safe runner `red -m pytest -q --tb=short
tests/test_interview_api.py::test_finish_during_scoring_refuses_late_answer_without_changing_outcome`:
**1 failed, 1 warning, 11.68s**. The API returned 200 after scoring finished the
session first, appending a turn absent from the saved assessment. Not a fixture
or import failure (`.pytest_cache/r3-s3-t2a-red.txt`).

Store writes now lock the existing candidate row (SQLite write-first no-op
preserves its timestamp; PostgreSQL row lock), then reread live state/current
question. Provider/turn scoring stays outside the transaction. Completion uses
a synchronous pure assessment callback over locked saved turns; final turn,
outcome and audit commit together. No new table, SQL migration or retry protocol.
The internal store signature changes; all production callers were updated.
Existing `SessionConflictError` import path and public HTTP shapes remain.
Terminal responses now return null `next_question`. Prior erasure tests pause
before lock acquisition or after commit; new competing-erasure tests prove that
erasure queues behind a locked write, then removes all owned content/audits.

Separate same-agent specification/correctness **self-review**, HEAD `5480498`
plus seven source/test/journey files, hashes and bounded session diff in
`.pytest_cache/r3-s3-t2a-reviewed.json` / `r3-s3-t2a-session.diff`, generated by
project Python `.pytest_cache/review_r3_s3_t2a.py`. Reviewed all changed functions
and the original red addition (its unchanged API baseline was verified against
HEAD because that regression was added during the initial snapshot copy),
callers, question/status/expiry checks after provider work and lock wait,
candidate-first lock order, completion rollback, frozen historical JSON,
transcript-free org projection, actor/consent/erasure refusals and owned scratch
setup/teardown. AC1-3 map to controlled competing connections, API delayed-provider
tests and migrated HTTP/restart; AC4 maps to final regression and preservation.
No unresolved acceptance-blocking finding. Removed one trailing blank line found
by diff check; this changed no executable behavior. No independent review claim.

Safe runner `.resume/Scripts/python.exe .pytest_cache/run_r3_s3_t2a.py <tag>
<Python arguments>` removes inherited `DEE_*`, disables live credentials, points
GitHub to loopback refusal and uses null/capture providers and isolated stores.
Actual final commands/results:

- `focused-final -m pytest -q --tb=short tests/test_interview_store.py
  tests/test_interview_service.py tests/test_interview_api.py
  tests/test_interview_org.py tests/test_interview_erasure.py
  tests/test_interview_erasure_concurrency.py
  tests/test_interview_lifecycle_concurrency.py`: **88 passed, 16 skipped,
  1 warning, 70.50s**. Skips require disposable PostgreSQL. Earlier focused
  82/13 was before the last test additions and is not final evidence.
- `http scripts/smoke_r3_s3_t1.py`: **28/28**, exit 0, 51.94s. Extended existing
  migrated scratch journey: duplicate/future/stale/expired requests, restart
  resume/early finish, saved historical/mixed versions, actor denials, current
  org consent/revocation, transcript/log boundaries and erasure. Fake providers.
- `contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 26.94s;
  actual HTTP cookie/CSRF contract, not browser execution.
- `.resume/Scripts/python.exe .pytest_cache/run_r3_s3_t2a_postgres.py`:
  focused selection above **104 passed, 1 warning, 217.81s**. PostgreSQL 18.6,
  Asia/Calcutta, READ COMMITTED; isolated schemas/owned disposable cluster.
  Controlled competing connections observe `pg_blocking_pids` before release
  for starts, duplicate answers, both finish/answer orders, repeated finishes,
  expiry during lock wait and erasure behind a locked write. The selection
  includes the shared SQLite cases as well as PostgreSQL cases. Actual migrated
  PostgreSQL HTTP/restart: **28/28**, exit 0, 36.56s; owned cluster stop exit 0,
  33.90s, PID file absent. No migration change, so no new down/up gate.
- `node scripts/check_ui_bindings.js`: **559 bindings, 17 states**; syntax checks
  `node --check frontend/api.js` and `node --check frontend/support.js` passed.
  Scoped `git diff --check` passed after the whitespace correction.

Project Python `.pytest_cache/verify_r3_s3_t2a.py` passed after owned PG teardown:
**874 prior files**, working DB hash, HEAD/unrelated git status and seven reviewed
source hashes unchanged; demo health 200. Seven task/feature/handoff documents,
202 local links checked after closing; final status check
`.pytest_cache/check_r3_s3_t2a_docs.py` confirms T2A's four criteria, open
parent/sprint/PI/F11 and pending next T2B. An early invocation preceded PG teardown
metadata and was rerun after stop; it is not counted as a passing run.
Final safe runner `full` executes `.resume/Scripts/python.exe -m pytest -q
--tb=short`: **3443 passed, 505 skipped, 127 warnings, 1656.67s** (wrapper exit 0,
1675.44s), `.pytest_cache/r3-s3-t2a-full.txt`. Checks cover the reviewed executable
state; the sole later code-file edit removed a blank EOF line and diff check
was rerun. No application/test logic changed during final validation.
No UI handler change or interview-browser validation; T2B owns that gate.
Concurrent requests may still incur provider work before one loses the saved
state check. A lost HTTP response requires a read before deciding to resubmit;
there is no idempotency-token replay. Historical active duplicates are preserved,
not cleaned. No live-provider, measured-quality or working-data change claim.

T2A done. Parent T2, R3-S3, PI-R3/F11 remain open. Exact next: **R3-S3-T2B —
Browser lifecycle and text answers**, not started. Preserve data/demo and stop
after T2A; do not begin microphone T3.

## <a id="r3-s3-t2b"></a>R3-S3-T2B — Browser lifecycle and text answers

Status: done (2026-10-15). Parent: [T2](#r3-s3-t2).
Prerequisites: [T1](#r3-s3-t1), [T2A](#r3-s3-t2a), done.

### <a id="r3-s3-t2b--contract"></a>Contract

Replace the simulated interview with candidate-only start/list/resume/answer/
finish requests. Select a saved active session on entry, or the latest saved
outcome; allow explicit selection of history. Reload resumes the server's next
question. Bind typed text and submit its question ID once. Clear drafts when
changing questions/sessions, navigating away, signing out or unmounting. Display
saved candidate transcripts and assessments, version and advisory limitations.
Missing/limited evidence and unconfirmed relevance do not imply poor ability;
historical v1 and mixed/unknown versions must be explained without comparison.
Describe derived abandoned status as expired. Use deadlines, visible errors and
read-only recovery after conflicts or uncertain writes; never replay an answer.

| ID | Acceptance | Required validation | Result |
|---|---|---|---|
| AC1 | Real start/list/resume/text/finish; saved question/outcome survives reload | Intended red, offline handlers, migrated scratch HTTP and actual Chrome | Passed |
| AC2 | Duplicate clicks submit once; stale/expired/refused/uncertain writes settle; refresh reads before another write | Offline failure/delay/malformed cases and actual Chrome recovery | Passed |
| AC3 | Actor/view/session cleanup ignores late replies; candidate-only transcripts; org projection remains consent-gated | Offline races, two-actor API tests/journey and Chrome session loss | Passed |
| AC4 | Saved versions, history, insufficient/limited/relevance and mixed evidence are honest | Rendered Chrome fixtures, offline assertions, assessment API regressions | Passed |
| AC5 | Reviewed final code passes regression and preserves prior data/work/demo | Full pytest, bindings/syntax, separate self-review, preservation | Passed |

Scope: frontend lifecycle plus bounded regression/journey scripts. Reuse existing
API client and backend contracts. No schema/store/scorer change, microphone
implementation, live provider, working migration, cleanup or deployment. No new
PostgreSQL transaction gate unless backend semantics change. T3 owns microphone;
only typed answers are offered here. Microphone and sprint integration retain separate gates.

### <a id="r3-s3-t2b--evidence-and-review"></a>Evidence and review

Intended red: safe runner `red -m pytest -q --tb=short tests/test_ui_interview.py`
failed **1 test, 2.19s** because entry never requested `/portal/interviews`.
The shipped handler regression reached the missing behavior, not a fixture error.
Removed simulated questions, recording timers, fake progress and word-floor
claims. Browser requests reuse the credential/CSRF client with deadlines. Drafts
are memory-only and clear on refresh/navigation/actor loss; unmount invalidates
callbacks. An uncertain draft remains read-only until a successful saved read,
then clears; there is no automatic replay or new idempotency mechanism.

Separate same-agent specification/correctness **self-review**, HEAD `5480498`
plus five executable files captured by project Python
`.pytest_cache/review_r3_s3_t2b.py`; exact hashes and bounded diff are
`.pytest_cache/r3-s3-t2b-reviewed.json` / `r3-s3-t2b-session.diff`.
Reviewed template/handlers, callers, candidate/CSRF boundaries, stale responses,
draft and transcript cleanup, partial reads, terminal/malformed responses,
version/coverage copy, scratch isolation and owned-process teardown. AC1-4 map
to offline handlers, actual Chrome and migrated HTTP; AC5 maps to final full regression, static and preservation checks. No unresolved acceptance-blocking finding.
No independent review. Findings resolved:

- Medium, `frontend/Veritas.dc.html`, assessment rendering: an unknown saved
  version with a confident historical band could still show that band/index.
  Now unknown/mixed versions offer no ability conclusion or comparable index.
  `review-red` failed **1 test, 2.26s** on that trigger; final Node/pytest pass.
- Medium, interview start template: candidate navigation hid the existing
  domain controls, despite copy promising the selected domain. Reused both
  registered domain buttons; final Chrome checks the actual saved GenAI domain.
  An early full run was stopped before this final template change; its partial
  log is provisional and is not completion evidence.

Safe runner: `.resume/Scripts/python.exe .pytest_cache/run_r3_s3_t2b.py <tag>
<Python arguments>` clears inherited `DEE_*`, disables live credentials and
points GitHub at loopback refusal. Actual results:

- `focused-final -m pytest -q --tb=short tests/test_ui_interview.py
  tests/test_ui_evaluate.py tests/test_ui_verification.py tests/test_interview_api.py
  tests/test_interview_org_api.py tests/test_interview_erasure.py
  tests/test_interview_service.py tests/test_interview_scoring.py
  tests/test_interview_scoring_llm.py`: **100 passed, 1 warning, 37.24s**.
- `node --test scripts/test_ui_interview.js`: **41 passed**, including 19
  interview cases and 22 reused client/evaluation/feedback cases. The pytest
  wrapper is the offline gate, separate from Chrome.
- `browser-final scripts/check_ui_interview_browser.py`: **36/36**, exit 0,
  37.72s. Actual Chrome/native HTTP on migrated scratch SQLite: empty/list,
  chosen domain, duplicate clicks, typed answer/reload/early finish, stale
  second-client answer, expiry, CSRF, history, saved versions/evidence,
  navigation, late old-account acknowledgement and actual session loss.
  Synthetic 503/malformed/stall and lost committed acknowledgement exercise
  recovery without replay. Frozen historical/mixed/expiry records are explicit
  fixtures, not scoring-quality evidence. Console/uncaught errors absent;
  answer text absent from app logs. Screenshot inspected. Scratch:
  `C:/Users/REVANP~1/AppData/Local/Temp/r3-s3-t2b-browser-i63afdso`.
  First browser attempt refused a profile-less setup (422); corrected the
  synthetic resume fixture, not application behavior. Earlier browser runs
  were provisional; final run owns all listed criteria. Chrome needs CDN internet.
- `http scripts/smoke_r3_s3_t1.py`: **28/28**, exit 0, 30.76s. Migrated scratch
  SQLite/native HTTP/restart: saved next question/outcomes, duplicates/stale/
  expiry, historical/mixed versions, two candidates, current org consent and
  revocation, transcript-free org summaries and erasure. Fake providers only.
- `contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 19.34s;
  real HTTP cookie/CSRF contracts, separate from browser execution.
- `common-browser scripts/check_ui_evaluate_browser.py`: **31/31**, exit 0,
  35.75s. Actual Chrome evaluation/report/feedback/contact compatibility.
  The later interview-only domain controls do not change these paths.
- `node scripts/check_ui_bindings.js`: **575 bindings, 18 states**;
  `node --check frontend/api.js` and `node --check frontend/support.js` passed.
  Scoped tracked diff whitespace check passed.
- `full -m pytest -q --tb=short`: **3445 passed, 505 skipped, 127 warnings in 932.27s**;
  `.pytest_cache/r3-s3-t2b-full.txt`. This completed run uses the final reviewed
  code; the stopped earlier run is not counted.
- Project Python `.pytest_cache/verify_r3_s3_t2b.py`: **879 prior files**
  preserved; working DB, HEAD/unrelated status and five executable hashes
  unchanged; demo health 200. Eight documents and 221 local links checked after
  closure. Browser/HTTP scripts stopped their owned app/Chrome processes and
  retained synthetic evidence; no working server restart.
  `.pytest_cache/check_r3_s3_t2b_docs.py` verifies five passed criteria, done
  T2B/T2, pending T3 and open sprint/PI/F11. Its whitespace check was scoped to
  added lines after finding existing historical Roadmap whitespace; prior
  formatting is preserved.

No backend, SQL, schema, scorer or dependency change, so no new PostgreSQL/
migration gate applies; T2A owns its controlled concurrency evidence. All external
providers remain fake/capture; no live-provider or measured-quality claim.
Lists remain unpaged; saved reads are snapshots and an earlier uncertain request
may still finish later. Backend conflicts remain authoritative. Prior active
duplicates and historical values are preserved. Working DB/demo untouched.
T2B and parent T2 are done; R3-S3/PI-R3/F11 remain
open. Exact next: **R3-S3-T3 — Microphone answers and transcription**, not started.
Stop after T2B.

## <a id="r3-s3-t3"></a>R3-S3-T3 — Microphone answers and transcription

Status: done (2026-10-16). Prerequisite: [T2](#r3-s3-t2), done.
Parent: [PI-R3](PI-R3.md), F11.

### <a id="r3-s3-t3--contract"></a>Contract

Connect candidate microphone capture to the existing answer API. Permission is
requested only by an explicit recording action. Stop creates a local clip;
only explicit submission sends it for immediate transcription/scoring. Explain
that the saved transcript is shown afterwards, not editable before scoring.
Offer discard/re-record and typed fallback. Preserve a typed draft across local
recording failures. Capture only audio. Use supported MediaRecorder MIME types,
bounded chunks (5 MB), a two-minute recording deadline and permission/stop
deadlines. Timer delivery can be delayed in background tabs; byte validation
still precedes upload. Raw media stays in memory and is discarded after use.

Stop tracks and discard callbacks/clips on mode/question/session changes,
refresh, navigation, sign-out, page exit and unmount. Ignore late permission,
recorder, encoding and HTTP results. No duplicate submissions or automatic
replay; uncertain writes still require saved-state refresh. Provider failures
save no turn. Validate MIME/base64/size before provider work; suppress provider
payloads/errors in HTTP/logs. Keep saved transcript/digest only, current actor/
CSRF/consent/erasure boundaries, versioned advisory content scoring and history.

| ID | Acceptance | Required evidence | Result |
|---|---|---|---|
| AC1 | Explicit audio-only record/stop/discard/submit; saved transcript, same server question and completion | Intended red, offline handlers, actual Chrome fake media and migrated HTTP | Passed |
| AC2 | Permission/device/unsupported format/empty/size/deadline/provider failures recover with text and unchanged saved progress | Offline events/timers; actual Chrome permission and fake-ASR API scenarios | Passed |
| AC3 | Cleanup and late-result guards on all exits; uncertain writes read before retry without replay | Offline races; actual Chrome navigation/reload/actor and lost-response recovery | Passed |
| AC4 | Invalid audio refuses before ASR; raw audio/provider details do not persist or leak | API/service/speech regressions; migrated HTTP/restart/two actors and logs | Passed |
| AC5 | Final reviewed code passes regression; prior data/work/demo preserved | Full pytest, bindings/syntax, separate self-review and preservation | Passed |

Scope: browser capture and bounded audio-path validation/disclosure fixes. No
SQL/schema/migration/scorer change, waveform/appearance/emotion scoring,
transcript editing endpoint, file uploader, TTS, live-provider or quality claim.
Chrome uses synthetic device audio and a fake ASR; this does not validate codec
support or transcription accuracy at a live provider. Existing provider MIME
mapping is reused. No new PostgreSQL transaction gate unless SQL behavior changes.
R3-S3-Q remains a separate combined acceptance task. Complete only T3, then stop.

### <a id="r3-s3-t3--evidence-and-review"></a>Evidence and review

Safe runner `.resume/Scripts/python.exe .pytest_cache/run_r3_s3_t3.py <tag>
<Python arguments>` clears inherited `DEE_*`, disables live credentials and uses
isolated stores/capture/fake providers. Intended reds:

- `red -m pytest -q --tb=short tests/test_ui_interview_audio.py`: **1 failed,
  4.91s**. The candidate action requested no microphone stream; no fixture error.
- `api-red -m pytest -q --tb=short
  tests/test_interview_api.py::test_invalid_audio_refuses_before_asr_and_preserves_the_question
  tests/test_interview_api.py::test_asr_failure_detail_is_safe_and_an_empty_transcript_does_not_consume_a_turn`:
  **4 failed, 1 warning, 16.61s**. Unsupported MIME/ambiguous channels were accepted,
  bad base64 reached ASR, and a private exception appeared in the HTTP response.

Permission/encoding deadlines are 20s; stop finalization is 5s. Raw clips live
outside component state, tied to the actor/session/question, and clear on use
or exit; no automatic submit on stop. The existing answer endpoint still saves
and scores immediately. Invalid MIME/base64/exclusive-channel input now refuses
before ASR; empty output saves no turn. SDK parsing errors are safe refusals,
and ASR logs keep exception type rather than its payload. Existing format mapping
and saved scorer/transaction behavior remain; no database or migration change.

Separate same-agent specification/correctness **self-review**, HEAD `5480498`
plus ten executable files: bounded diff and hashes captured with project Python
`.pytest_cache/review_r3_s3_t3.py` in `r3-s3-t3-session.diff` /
`r3-s3-t3-reviewed.json`. Reviewed all changed handlers/callers, input/provider
boundaries, callback/timer/track/reader cleanup, actor/CSRF/consent/erasure,
terminal/stale/ambiguous outcomes, version/history preservation and owned scratch
lifecycle. AC1-4 map to the offline events and actual Chrome/API evidence below;
AC5 maps to final full regression and preservation checks. Review fixed one low-severity introduction still
advertising text-only answers, and clarified that finish discards unsent media.
No unresolved acceptance-blocking finding; no independent review claim.

Final checks on the reviewed executable state:

- `focused-final -m pytest -q --tb=short tests/test_ui_interview_audio.py
  tests/test_ui_interview.py tests/test_interview_api.py tests/test_interview_service.py
  tests/test_interview_org_api.py tests/test_interview_models.py
  tests/test_interview_erasure.py tests/test_speech_seam.py`: **82 passed,
  1 warning, 82.52s**. Earlier focused **64 passed** was provisional.
- `node --test scripts/test_ui_interview_audio.js`: **64 passed**, including
  23 audio cases and 41 reused text/client/evaluation cases. Offline callbacks,
  permission/stop/encoding/duration deadlines, byte/empty limits, device failures,
  actor/navigation/page-exit/unmount cleanup and no replay; not browser evidence.
- `browser-final scripts/check_ui_interview_audio_browser.py`: **29/29**, exit 0,
  69.86s. Actual Chrome synthetic microphone and MediaRecorder: denied/granted
  permission, audio-only tracks, stop/discard/type, synthetic unsupported/oversize
  cases, native fake-ASR failures/empty/delay, lost committed acknowledgement,
  duplicate/stale clips, encoded-byte digest agreement, truncated transcript,
  final-answer completion, late permission/navigation/reload/signout/other actor.
  Console/uncaught errors absent; app logs omit transcript/private error. Screenshots
  retained under `C:/Users/REVANP~1/AppData/Local/Temp/r3-s3-t3-browser-ljzu5y6z`;
  recording display inspected. Requires Chrome/CDN internet. Earlier 29/29 was
  before final copy/test changes; final run owns the current result.
- `http-final scripts/smoke_r3_s3_t3.py`: **18/18**, exit 0, 66.62s. Migrated
  scratch SQLite/native HTTP: invalid input before ASR, no-turn refusals, saved
  transcript/digest/truncation/assessment, duplicate/foreign refusals, exact restart
  recovery, current/revoked org consent without transcript/turns, erasure and
  surviving actor. Logs omit raw audio/transcript/private provider text. Earlier
  15/15 preceded explicit audio-summary consent checks and is provisional.
- `text-browser scripts/check_ui_interview_browser.py`: **36/36**, exit 0, 62.66s;
  current real text lifecycle/history/version/CSRF/expiry/error/actor compatibility.
- `contract scripts/check_ui_screening_contract.py`: **32/32**, exit 0, 49.46s;
  native HTTP cookie/CSRF contracts, separate from browser execution.
- `node scripts/check_ui_bindings.js`: **589 bindings, 18 states**;
  `node --check frontend/api.js`, `node --check frontend/support.js` and scoped
  tracked `git diff --check` passed.
- `full -m pytest -q --tb=short`: **3457 passed, 505 skipped, 127 warnings in 1944.85s**;
  `.pytest_cache/r3-s3-t3-full.txt`, final reviewed code. No stopped/provisional
  full run is counted. Closure on 2026-10-16 recovered this completed run and
  verified all ten reviewed executable hashes before finishing; no application
  edits were needed during the continuation.
- Project Python `.pytest_cache/verify_r3_s3_t3.py`: **880 prior files** preserved,
  working DB/HEAD/unrelated status and ten executable hashes unchanged; demo
  health 200. Seven documents and 226 local links checked after closure.
  Owned app/Chrome processes stopped; synthetic artifacts retained. Demo backend
  was not restarted and still needs its separately recorded controlled restart.
- Project Python `.pytest_cache/check_r3_s3_t3_docs.py`: five passed criteria,
  dated T3 completion, unstarted next Q, open sprint/PI/F11 and added-line
  whitespace across 17 files passed; prior formatting preserved.

References used for API event ordering and test permission control:
[MediaRecorder stop](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/stop_event),
[getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia),
[Chrome permissions](https://chromedevtools.github.io/devtools-protocol/tot/Browser/#method-setPermission).
No live-provider/codec-compatibility/transcription-quality or independent-review
claim. Pending permission cannot be canceled at the browser API; late streams
are stopped on resolution. Browser timers may be delayed; limits are per clip,
not aggregate browser/service resources. ASR can hallucinate; the saved transcript
is inspectable after scoring, not editable beforehand. Server limits may be
lower than the UI's 5 MB cap and refuse safely. No SQL/concurrency/migration change
requires a new PostgreSQL gate. Working DB/demo preserved. T3 done; R3-S3/PI-R3/F11 stay open.
Exact next: **R3-S3-Q — Sprint integration review**, not started. Stop after T3.
