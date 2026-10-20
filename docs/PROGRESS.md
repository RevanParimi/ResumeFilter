# Current handoff

Updated: 2026-10-20. Project: Veritas resume evaluation / talent platform.

## Start here

**R4-S1-T3F complete: employer routes extracted and Roles API bindings repaired.**
Eleven operations/four DTOs now live in `api/employer.py`; the aggregate is
1,163 lines. Full 102-operation OpenAPI/dependency contract unchanged. Roles
now renders the actual ranked candidates/nested skill coverage and successful
empty pools; errors remain separate. Focused/full offline pytest, migrated
HTTP/graceful restart, actual Chrome, static/preservation checks and self-review
passed. [F evidence](delivery/EVIDENCE-R4.md#r4-s1-t3f) owns commands, results,
bounded scope refinement and limits. Prior E work, working DB and demo preserved.

**Exact next development task: R4-S1-T3G - Extract feature materialization and
talent search routes, not started.** Read [PI-R4](delivery/PI-R4.md),
[WORKFLOW.md](delivery/WORKFLOW.md), [T3](delivery/tasks/R4-S1-T3.md) and
[F evidence](delivery/EVIDENCE-R4.md#r4-s1-t3f). Write G's contract/evidence inline
in T3; reuse `tests/test_api_route_extraction.py`. Trace feature/ranking schemas,
materialization helpers, admin dependencies and current-consent serving; preserve
the full OpenAPI/ordered auth, ownership, consent and error contracts.
Complete only G next session. T3/F13/sprint/PI remain open; T4 is not started.
E/F work and the new completion workflow are committed/pushed as `369ead1` on
`origin/main`, after a distinct final self-review; the remote SHA was verified.
[The audit](CODEBASE_REVIEW_2026-09-07.md#task-completion-publication-2026-10-20)
owns that later review/publication evidence. This documentation-only confirmation
records the verified push. No deployment/demo restart; G has not started.

## Latest work

F preserves job ownership, offer/card consent and advisory matching/compensation.
Actual Chrome exposed obsolete Roles response/status assumptions; the recorded
bounded fix aligns the UI with the unchanged API. A-F evidence is in
[PI-R4 evidence](delivery/EVIDENCE-R4.md). R4-M1/M2 maintenance and prior publication
are complete; [the existing audit](CODEBASE_REVIEW_2026-09-07.md#publication-follow-up-previously-completed-local-work)
owns that history. Ignored local-artifact removal remains outside this task.
[FEATURE_STATUS.md](../FEATURE_STATUS.md) owns the feature overview.

## Reusable validation setup

- Windows Python: `.resume/Scripts/python.exe`; full suite: `-m pytest -q
  --tb=short`. Use fake providers and isolated stores, never working storage.
  Latest sanitized runner: `.pytest_cache/run_r4_s1_t3f.py <tag> <Python args>`;
  omitted args run full pytest. Clear inherited DEE config/keys and avoid .env.
- Screening/UI HTTP contract/graceful restart: `scripts/smoke_r4_s1_t3d.py`.
  Actual screening Chrome: `scripts/check_ui_screening_extraction_browser.py`.
  Candidate/source/ownership/graceful restart: `scripts/smoke_r4_s1_t3c.py`.
  Evaluation/report/outcome/restart journey: `scripts/smoke_r3_s1_q.py`
  (Windows stop is forced). Auth/ledger/employer/graceful SQL journey: `scripts/smoke_r4_s1_t3a.py`.
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
- Employer Roles/compensation/report Chrome: `scripts/check_ui_review_context_browser.py`.
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

- Exactly one task per chat. After completion and required checks, perform a
  distinct final review, then commit/push scoped changes and verify the remote
  (user instruction 2026-10-20; recorded in AGENTS/workflow). No fresh routine
  permission request. Deployment, external messages and working-data/legacy
  cleanup remain outside scope. Preserve unrelated work and `data/veritas.db`.
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
