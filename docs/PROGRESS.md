# Current handoff

Updated: 2026-10-19. Project: Veritas resume evaluation / talent platform.

## Start here

**R4-M2 publication follow-up: all completed local work reviewed and validated.**
The existing application changes and R4-M1 test/delivery consolidation are now
included in the explicit 342-path publication scope, alongside 58 pending tracked
deletions. Full offline pytest, actual scratch Chrome/HTTP restart journeys,
static checks, record/link preservation and staged diff self-review passed.
[The existing audit](CODEBASE_REVIEW_2026-09-07.md#publication-follow-up-previously-completed-local-work)
owns exact commands, counts, limits and publication evidence. Publish to main
using revan.datta132@gmail.com; final commit verification follows publication.
Working data, secrets, local editor settings and the running demo are preserved.
Previously blocked ignored local-artifact deletion remains outside the push.

R4-M1 test/delivery consolidation and R4-M2 versioned-file retirement are done.
The earlier cleanup-only publication is `57a68ec`; this follow-up includes the
previously uncommitted completed work. No new backlog development starts here.

**Exact next development task: R4-S1-T3E - Extract ledger organizations, consent,
records, coding and reputation routes (not started).** Read [PI-R4](delivery/PI-R4.md),
[WORKFLOW.md](delivery/WORKFLOW.md), [T3](delivery/tasks/R4-S1-T3.md) and
[D evidence](delivery/EVIDENCE-R4.md#r4-s1-t3d). Write E's contract/evidence inline
in T3; reuse `tests/test_api_route_extraction.py`. Trace admin/org planes,
shared schemas/helpers and DTOs; retain the full OpenAPI/ordered dependency,
auth/CSRF, ownership and error contracts. Complete only E next session; no T4.

## Latest work

R4-M2 removed 93 superseded implementation/prototype/design files and updated
historical references. The static allowlist refuses restored retired assets;
focused/full offline regression, actual Chrome, binding/syntax, history/link,
AST and preservation checks passed for both the workspace and published candidate.
Automatic approval review blocked recursive deletion of ignored local tooling/
Windows-cache directories; they remain excluded from Git/build context. The
owned validation checkout was unregistered, but Windows denied removing its
residual ignored scratch directory.


R4-M1 consolidated 47 test modules into 15 (314 -> 282 overall), and 86 completed
delivery records into four PI evidence files (97 -> 14 delivery Markdown files).
Task IDs, original evidence/statuses and all 4,015 collected cases are retained.
The workflow now reuses inline child records and existing product-area tests;
there is no standalone cleanup task document. Focused/full offline pytest, all
seven Node handler journeys, bindings, collection/AST/evidence/link preservation,
whitespace and self-review passed; the audit owns exact commands/results. Runtime
source/scripts/frontend, prior unrelated edits, working DB and demo were preserved.

T3A/B/C/D are done; [their PI-R4 evidence](delivery/EVIDENCE-R4.md) retains exact
checks and limitations. D moved 13 screening operations, three DTOs and two
helpers; `routes.py` is 1,626 lines. The full 102-operation contract, shared/legacy
aliases and auth/CSRF are unchanged. T3/F13, R4-S1 and PI-R4 stay open. T1/T2
retain shared resource ownership and unused vector infrastructure removal.
[FEATURE_STATUS.md](../FEATURE_STATUS.md) owns the feature overview; completed
PI-R1/R2/R3 records retain bounded validation and unresolved PI-R5 scope.

## Reusable validation setup

- Windows Python: `.resume/Scripts/python.exe`; full suite: `-m pytest -q
  --tb=short`. Use fake providers and isolated stores, never working storage.
  Latest sanitized runner: `.pytest_cache/run_r4_s1_t3d.py <tag> <Python args>`;
  omitted args run full pytest. Clear inherited DEE config/keys and avoid .env.
- Screening/UI HTTP contract/graceful restart: `scripts/smoke_r4_s1_t3d.py`.
  Actual screening Chrome: `scripts/check_ui_screening_extraction_browser.py`.
  Candidate/source/ownership/graceful restart: `scripts/smoke_r4_s1_t3c.py`.
  Evaluation/report/outcome/restart journey: `scripts/smoke_r3_s1_q.py`
  (Windows stop is forced). Auth/graceful SQL journey: `scripts/smoke_r4_s1_t3a.py`.
  Contract fixture: `tests/fixtures/api_contract_r4_s1_t3.json`; pure extractions
  retain it. Provenance journey: `scripts/smoke_r4_s1_t2.py` (blocked Chroma imports,
  default/legacy settings, migrated HTTP and graceful restart). Provider lifecycle
  journey: `scripts/smoke_r4_s1_t1b.py`, or
  `--postgres` with an explicitly disposable DEE_TEST_DB_URL. Latest owned PG
  runner/runtime: `.pytest_cache/run_r4_s1_t1b_postgres.py` /
  `r4-s1-t1b-pg-runtime.json`; server stopped. Portable PG distribution metadata:
  `.pytest_cache/r1-s1-t3a-v1-pg-runtime.json`. These local artifacts are not
  portable setup guarantees. PG HTTP proves PG behavior; SQLite fixtures and
  skipped lock cases do not. T1A owns the actual controlled lock/migration gate.
- Actual Chrome: `scripts/check_ui_evaluate_browser.py` and
  `scripts/check_ui_interview_integration_browser.py`; screening contracts:
  `scripts/check_ui_screening_contract.py`. Chrome needs existing CDN internet.
  Bindings: `node scripts/check_ui_bindings.js`; JS syntax: `node --check
  frontend/api.js` and `frontend/support.js`. Bindings/source checks are not Chrome.
- CPython 3.13.11/current dependencies remain in use; optional Parquet and
  environment skips do not prove omitted cases. Synthetic providers/media prove
  mechanics, not live ASR/codec compatibility, factual accuracy or measured quality.
  Same-agent diff self-review is not independent review.

## Standing constraints and risks

- Exactly one task per chat. Standing Option A fixes are authorized; publishing,
  deployment, external messages and working-data/legacy cleanup are not implied.
  Prior commit/push authorization was recorded on 27 September; no such action
  was taken in D. Preserve all prior changes and modified `data/veritas.db`.
- Do not restart the running `http://127.0.0.1:8000/ui/` demo. Its older,
  reload-disabled backend still needs a separately controlled restart for earlier
  backend/PDF/rubric/lifecycle changes. Scratch validation does not update it.
  Working DB remains at 0023; only scratch stores were migrated to 0029.
- Preserve advisory/human review, domain independence, deterministic fallbacks,
  tenant isolation and present consent/erasure. Polished/AI-assisted truthful
  writing is not fabrication. Video scoring judges content, not appearance or
  inferred emotion. Heuristic scores and synthetic fixtures are not fraud proof.
- `s73.2` English content coverage is bounded/uncalibrated; historical v1 stays
  labeled and mixed/unknown versions refuse confident comparison. Microphone
  answers score immediately; saved transcripts appear afterwards. Limits are per
  clip, timers may be delayed, and pending permission requests cannot be canceled;
  late streams stop when resolved. Uncertain writes require saved-state reads
  without automatic replay; duplicate provider work remains possible.
- Final read/export/search/delivery guards are snapshots, not locks across later
  delivery. Failed HTTP after a commit does not imply rollback; concurrent fresh
  capture may reappear and matching audit rank gaps remain. Older unresolved
  screening input pauses across tenants on erasure with its TTL; fresh intake is
  allowed. Future-media erasure extensions remain R5-S1-T4.
- Curation retention can exceed 30 days if maintenance/startup is delayed;
  schedule/monitor `scripts/purge_curation.py` (no scheduler installed). Overlay
  refresh is process-local. Approval is human judgment, not anonymization; the
  named legacy inventory was one empty snapshot, not proof for other stores.
- Historical feature timestamps and the named working DB's one historical-login
  subject with unknown mailbox proof need explicit review/policy. Do not infer
  login ownership from hints, merge identities or auto-repair old history. Missing
  session/audit history is unrecoverable; downgrade discards new proof metadata.
- Phone verification remains unavailable. Mail/DB commits are not atomic; SMTP
  holds the candidate/SQLite writer lock with existing socket timeouts. PDF limits
  are per parse, not aggregate RSS/concurrency; unsupported runtimes/input can
  refuse safely. Aggregate bounds/cross-worker overlay/reproducibility remain R4.
