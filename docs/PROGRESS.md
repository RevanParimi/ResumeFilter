# Current handoff

Updated: 2026-09-18. Project: Veritas resume evaluation / talent platform.

## Start here

**Next task: R1-S1-T3a validation — disposable PostgreSQL concurrency gate.**
T3 was split into T3a (reports/outcomes) and T3b (interview/derived-store writes).
T3a is implemented and **awaiting validation**, not done. Read
`docs/delivery/WORKFLOW.md`, the T3 section of `docs/delivery/PI-R1.md` and
`docs/delivery/tasks/R1-S1-T3a.md` for commands/evidence. DEE_TEST_DB_URL is now
present in `.env`, but PostgreSQL rejects authentication. User was asked to
correct it locally; never print its credentials. The fixtures read the process
environment, so load only that setting explicitly after correction. Confirm
disposable storage before running the concurrency/focused tests and full suite.
The suite cleanup drops all schemas matching `s_%` (literal underscore). Do not
repeat the audit or count SQLite as PostgreSQL evidence. If unavailable,
keep the validation gate open rather than starting another task.
After T3a passes, next development task is **R1-S1-T3b** in a separate chat;
its entry points/scope are in `docs/delivery/tasks/R1-S1-T3.md`. Do not begin
T3b, R1-S1-Q or F06 in this chat. Legacy-file cleanup remains unauthorized.

One development or sprint-review task per chat: reproduce/specify, implement,
run required pytest and journey checks, review/fix, record evidence, then stop.
If a task is too large, split into named children and finish only the next one.
Missing required evidence means awaiting validation, not done. Full process:
`docs/delivery/WORKFLOW.md`.

## Standing user direction

- "Continue" means resume the task above without asking again to perform the
  authorized local audit fixes, feature completion and simplification.
- Preserve accuracy through focused source reads, explicit acceptance tests,
  failure-path coverage and review; no assumed 5–10% failure rate or zero-bug claim.
- Keep AI-polished truthful writing separate from factual fabrication risk.
- Conversational video with content-only scoring is the working recommendation;
  user has not confirmed the optional format preference. Repair rubric first.
- No publishing, deployment, external messages or destructive user-data cleanup.
- Preserve the existing modified `data/veritas.db`, other uncommitted work and
  secrets. Use isolated test storage/fake providers and project `.resume` Python.

## Latest session

Portability check (2026-09-18): confirmed AGENTS.md, this handoff and delivery
plans/task records are Git-tracked. A clone carries their committed/pushed
versions; .env and .resume are ignored and require local setup. Observed an
uncommitted tests/conftest.py change; preserved it. No task advanced, application
behavior changed or tests run. Next remains R1-S1-T3a PostgreSQL validation;
the recorded connection blocker was not rechecked in this informational session.

T3a validation retry (2026-09-11): the read-only connection probe still fails
with PostgreSQL password authentication rejected. No database SQL or mutations
ran; disposable storage cannot yet be verified. No task completed and no
application code changed. Pytest/HTTP checks were not repeated: existing SQLite
evidence cannot satisfy the missing PostgreSQL gate. Report-store SHA256 still
matches the implementation review. Self-review, documentation checks and
working-database preservation recorded in the task evidence. Next remains
**R1-S1-T3a validation** after the local test connection is corrected.

T3a validation follow-up (2026-09-10): read-only connection probes resolved DNS
but failed with password authentication rejected; no remote schema/data changes
were made. PostgreSQL remains unvalidated. Local focused rerun: **55 passed,
6 skipped, 2 warnings**, 41.32s; real scratch HTTP/restart rerun **19/19 passed**.
Recovered the prior full-suite log: **2195 passed, 6 skipped, 42 warnings**,
423.01s (SQLite evidence, not a new full run). No application code changed.
Report-store hash matches the implementation review; self-review and diff checks
recorded in the task evidence. Next remains T3a validation after connection repair.

R1-S1-T3a: report updates racing erasure now translate stale-row errors into
SubjectErasedError after rollback and a fresh candidate lookup. Report/outcome
race logs no longer retain SQL exception parameters containing claims/notes.
Existing insert/cascade constraints, null-report evaluation cancellation and
outcome 404 responses remain authoritative. No schema/API/UI change.

Three intended regressions failed before the fix. Final focused verification:
**55 passed, 6 PostgreSQL skips**, 2 warnings, 50.19s; HTTP/restart smoke
**19/19 passed**, with event-controlled evaluator pauses through portal/admin
erasure and SQL inspection preserving only B. Full result recovered above.
Self-review and diff checks complete. Evidence/commands:
`docs/delivery/tasks/R1-S1-T3a.md`. No independent review, PostgreSQL success,
browser execution or live-provider validation claimed. No user-data cleanup.

Prior completed task: T2, legacy CLI/policy, full suite 2186 passed;
details in `docs/delivery/tasks/R1-S1-T2.md` and `docs/LEGACY_FLYWHEEL.md`.
Existing logs, legacy files, cloud backups and physical media are not cleaned
by T3a. Interview/derived-store and ingest races remain the pending T3b child.

## Implementation state and evidence

F01–F04 are completed local fixes, with qualifications in
`docs/delivery/BASELINE.md`. R1-S1-T1/T2 are done; F05–F16 remain open. Task status lives in
the matching PI card; evidence lives in `delivery/tasks/<id>.md`. T3a awaits
PostgreSQL validation; T3b remains pending; the parent is incomplete.

Prior baseline: F04 2155 passed; foundations 2148 passed; UI bindings 402 across
nine states with JS syntax passing. Latest code result is above; it does not
establish production or representative model quality.

Known residuals: no persisted identity repair; contact-verification attempts
still have a separate race; no PostgreSQL concurrency evidence; shared vector
startup remains; current consent and erasure gaps remain. Full qualifications
and baseline command evidence: `docs/delivery/BASELINE.md`.

## Read only when relevant

- `docs/delivery/README.md`: PI/sprint order, original finding mapping.
- `docs/delivery/TASK_TEMPLATE.md`: per-task evidence/review record.
- `docs/CODEBASE_REVIEW_2026-09-07.md`: original detailed audit.
- `docs/FEATURE_LOGIC.md`: feature formulas and present limitations.
- `docs/ROADMAP.md` and old `.superpowers` artifacts: historical context;
  never load all of them for a new task.
