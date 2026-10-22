# Current handoff

Updated: 2026-10-22. Project: Veritas resume evaluation / talent platform.

## Start here

**R4-S1-T3J complete and published: interviews/employer assessment extraction.**
Six operations, five DTOs and one helper now live in `api/interviews.py`;
aggregate `routes.py` is 387 lines. Full 102-operation ordered auth/OpenAPI,
subject/tenant ownership, cookie/CSRF, transcript privacy, current consent/audit,
ASR refusal/budget/fallback and versioned advisory content scoring remain unchanged.
Focused/full offline pytest, migrated mixed-channel HTTP/graceful restart,
actual interview Chrome and static/preservation/implementation self-review passed.
[J evidence](delivery/EVIDENCE-R4.md#r4-s1-t3j) owns commands, results and limits.
Distinct final completion self-review found no blocking issues. Scoped task commit
`7a2f7be` is pushed to `origin/main`; remote
`7a2f7be4b5869cf94d2e53d4faa490ee0471a623` was verified. This documentation-only
confirmation records publication; the final response reports its remote SHA.
No next task or deployment started during publication.

**Exact next development task: R4-S1-T3K - Extract curation routes, not started.**
Read [PI-R4](delivery/PI-R4.md), [WORKFLOW.md](delivery/WORKFLOW.md),
[T3](delivery/tasks/R4-S1-T3.md) and [J evidence](delivery/EVIDENCE-R4.md#r4-s1-t3j).
Write K's contract/evidence inline in T3; reuse consolidated route tests and
existing curation HTTP/Chrome journeys. Preserve operator auth/CSRF, queue
pagination/status/cursors, expected revisions, alias conflicts and overlay behavior.
Complete only K next session. T3/F13/sprint/PI remain open; T4 has not started.

## Latest work

Standalone interview/auth workflows preserve two-subject/two-employer ownership,
cookie/key precedence and CSRF, owned mixed-channel state, conflicts, safe ASR
refusal, pre-provider budget and typed recovery, versioned advisory assessments,
transcript-free employer summaries, exact-purpose current consent/audit,
revocation and erasure. Migrated HTTP survives graceful restart. Chrome performs
real recording, error recovery, reload/restart, completion and session isolation.
Working DB and unrelated tracked files match the baseline; no demo restart.
A-J evidence is in [PI-R4 evidence](delivery/EVIDENCE-R4.md). Publication uses
per-command GitHub account selection from G's evidence for the existing two-account
Credential Manager setup. Ignored artifact removal stays outside scope;
[FEATURE_STATUS.md](../FEATURE_STATUS.md) owns the feature overview.

## Reusable validation setup

- Windows Python: `.resume/Scripts/python.exe`; full suite: `-m pytest -q
  --tb=short`. Use fake providers and isolated stores, never working storage.
  Latest sanitized runner: `.pytest_cache/run_r4_s1_t3j.py <tag> <Python args>`;
  omitted args run full pytest. Clear inherited DEE config/keys and avoid .env.
- Screening/UI HTTP contract/graceful restart: `scripts/smoke_r4_s1_t3d.py`.
  Actual screening Chrome: `scripts/check_ui_screening_extraction_browser.py`.
  Candidate/source/ownership/graceful restart: `scripts/smoke_r4_s1_t3c.py`.
  Evaluation/report/outcome/restart journey: `scripts/smoke_r3_s1_q.py`
  (Windows stop is forced). Auth/ledger/employer/features/portal/graceful SQL journey: `scripts/smoke_r4_s1_t3a.py`.
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
- Interview mixed-channel/graceful restart: `scripts/smoke_r3_s3_t3.py --combined`.
- Candidate portal/consent/access/erasure Chrome: `scripts/check_ui_evaluate_browser.py`.
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
- Do not start/restart the `http://127.0.0.1:8000/ui/` demo. Its last recorded,
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
