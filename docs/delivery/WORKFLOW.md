# One-task delivery workflow

User agreement: 2026-09-09. One development or sprint-review task per chat.
This workflow implements the user's request for detailed development, pytest,
review, end-to-end verification and accurate context between sessions.

## Context loading and task selection

1. Read `docs/PROGRESS.md`: current task, last evidence, next task and constraints.
2. Read this workflow and the current task section in its PI file. Read its
   `tasks/<id>.md` record if one exists. Use targeted sections, not the whole
   roadmap, every PI or old `.superpowers` review transcripts.
3. Inspect current git status/diff and relevant source/tests. Local state may
   have changed in another chat. Historical test results are not current proof.
4. Confirm dependencies against task evidence. Continue an unfinished current
   task first; otherwise start the named next eligible task. No new permission
   is needed for the already-authorized local work.
5. If the task cannot fit a focused session, create named child tasks before
   implementation. Give each its own acceptance criteria and tests. Complete
   only one child; the parent remains incomplete. Do not widen the task to
   unrelated improvements found during review.

PI files hold task status; the current handoff holds the next pointer. Per-task
records hold evidence and decisions. Update these together. Original F01–F16
IDs are traceability links, not a second competing execution order. PI-R IDs
are remediation increments and do not renumber the older product PI-1–PI-9.

## Development loop

1. **Specify the observable result.** Write the trigger, before/after behavior,
   exclusions, affected routes/stores, acceptance checks and required test layers
   in the task record. Record any design choice and why the simpler option works.
2. **Reproduce the defect.** Add a behavioral regression that fails for the
   intended reason and record that failure. For a new feature, test the missing
   behavior first. Do not count broken fixtures/import errors as reproduction.
3. **Implement the smallest complete change.** Include persistence, API behavior,
   UI behavior where in scope, error handling, compatibility and cleanup. Reuse
   current schemas, fake providers and smoke harnesses.
4. **Run focused tests.** Map each acceptance criterion to a meaningful assertion.
   Include failure paths, malformed provider data, ownership/consent boundaries,
   retries and missing-data behavior relevant to the change.
5. **Review the diff after implementation.** Perform the review described below,
   fix findings and rerun affected checks. Tests must assert user-visible or
   cross-boundary behavior, not merely mirror implementation/source shape.
6. **Run final regression and journey checks.** Full pytest for a code task;
   relevant API/browser/subprocess journey; database concurrency/migrations when
   required. Checks apply to the final reviewed code state. Changes after a
   check require the affected checks to be rerun.
7. **Record and stop.** Update the task record, PI status and short handoff.
   State completed behavior, evidence, open risks and the exact next task. Do
   not start that next task in the same chat.

No arbitrary number of review loops or assumed defect percentage proves
correctness. Stop when the acceptance gates pass, not after a token/time budget
or a predetermined number of failures. Do not promise zero bugs or measured
accuracy from test counts.

## Required validation layers

| Layer | Required when | What counts as evidence |
|---|---|---|
| Focused pytest | Every behavior change | Regression fails for the defect before the fix and passes after; new-feature acceptance tests; actual counts and command |
| Integration/API | A service, store, API or data boundary changes | Real request/store interactions with two actors where ownership matters, isolated persistence and fake external providers |
| Full regression | Every code task and sprint closure | `.resume/Scripts/python.exe -m pytest -q --tb=short` on the reviewed code; record failures, skips and warnings |
| Application journey | Every code task's affected workflow | Real app startup/HTTP/subprocess flow on migrated scratch storage; TestClient integration is useful but must not be mislabeled as browser/subprocess evidence |
| Browser | A visible screen, handler or UI contract changes | Real browser actions and rendered results, reload/error states, console exceptions; bindings alone are insufficient |
| PostgreSQL | SQL concurrency, constraints, transaction semantics or migrations change | Isolated DB tests, controlled competing connections and migration up/down/up when applicable; SQLite is not PostgreSQL evidence |
| Static/packaging | Relevant files change | JS syntax/bindings, import/build checks, `git diff --check`, install/lock/image checks appropriate to the task |
| Empirical quality | Claims about scoring/detection accuracy | Versioned held-out labeled data, provenance, sample sizes, false-positive/negative rates and uncertainty; synthetic unit fixtures prove mechanics only |
| Documentation | Docs-only task | Links, IDs, dependency graph, task coverage and status consistency; no full application test rerun merely for prose |

Full pytest command uses the project environment, not system Python. Choose
focused files from the task card and actual callers. Always record exact commands
used; a command listed in a plan is not evidence that it ran.

For frontend changes also run:

```powershell
node scripts/check_ui_bindings.js
node --check frontend/api.js
node --check frontend/support.js
```

Existing assets to reuse:

- `tests/conftest.py`: fake providers and isolated stores. `DEE_TEST_DB_URL`
  selects an explicitly configured disposable PostgreSQL test database.
- `scripts/_smoke.py`: existing scratch-server HTTP smoke harness. Inspect the
  selected script's setup before running; keep all DB/files in scratch storage,
  disable external providers explicitly, and do not inherit live `.env` secrets.
- `scripts/smoke_s*.py`: existing feature/sprint smokes. Extend only the relevant
  scenario or add a bounded one using the shared harness.
- `scripts/check_ui_screening_browser.py`: real Chrome/CDP screening journey.
  It currently requires Chrome and internet for CDN runtime assets. This is a
  known reproducibility gap; do not describe it as an offline browser runner.
- `.github/workflows/ci.yml`: existing Python 3.11/3.12 SQLite jobs, PostgreSQL
  job and image checks. A definition in this file does not mean a CI run passed.
  Local baseline used Python 3.13; runtime alignment is a planned task.

If a required browser/database/provider environment is unavailable, complete
all independent work, record the missing evidence and how to run it, and mark
the task **awaiting validation**. Do not claim the gate passed or close its
parent. External delivery, publishing and live-data cleanup are not implied by
this test workflow. Test with fakes/capture providers and synthetic data.

## Review protocol

Record a separate review pass after implementation, naming the reviewed code
state (commit if available plus relevant uncommitted diff/files). This workflow
does not authorize spawning sub-agents; label a same-agent review as self-review
and never claim an independent review that did not happen.

First check specification compliance: every acceptance criterion has a working
implementation and evidence, with no hidden scope changes. Then check correctness
and maintainability using the questions below. Record both parts; a green test
run alone is not the review.

Review these questions against the actual diff and callers:

- Does the original reproducer now fail safely, and can the same defect enter
  through another route, builder or background operation?
- Are authentication, CSRF, tenant/candidate ownership and present consent
  checked at the right boundary, including retries and historical snapshots?
- Can a crash, concurrent write, erasure, expiry or provider failure leave
  incorrect persisted state or misleading success?
- Are API/schema/scorer versions, migrations and old records handled explicitly?
- Are secrets, free text, transcripts, media and exception details exposed or
  retained unnecessarily?
- Does the UI reflect server state and recover from 4xx/5xx/timeouts/reloads?
- Is the test asserting the outcome rather than implementation wording? Are
  valid inputs and legitimate user behavior protected from false positives?
- Can the change be simpler without weakening these contracts? Have unused
  paths actually been checked before removing them?

Record each finding with severity, file/location, concrete trigger, consequence,
resolution and regression evidence. Fix acceptance-blocking findings before
completion. If no findings remain, write that plus the review scope and limits;
do not write "review passed" without identifying what was reviewed.

## Status and completion

`pending` → `in progress` → `review` → `done`.
Use `awaiting validation` for missing required test evidence and `blocked` for
a required dependency/information problem. These are task-document statuses,
not claims that unfinished work is complete. Reopen a task if a new regression
invalidates its acceptance result.

A task is done only when acceptance criteria, required checks and review fixes
are complete and recorded. A sprint closes only after its separate `-Q` task
proves the combined journey. A PI closes only after all its sprint gates. F05,
F06 etc. stay open until their mapped required tasks/gates close. Existing
F01–F04 completions remain historical fixes with explicitly scheduled residuals.

Keep durable evidence summaries in task Markdown files. Large logs/screenshots
may be local ignored artifacts, but important results must not exist only in
`.pytest_cache`. Never commit secrets, candidate data or a working database as
test evidence. Do not publish, push or deploy solely to obtain a green CI badge.
