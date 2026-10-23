# Current handoff

Updated: 2026-10-23. Project: Veritas resume evaluation / talent platform.

## Start here

**R4-S1-T4I complete and published; T4 frontend extraction closed.**
Shared display directly composes the eight screen areas. Proven unused helper,
overwritten account/org/search defaults, obsolete design prop and unreachable
sample notice/text metadata are removed. Live identities/values/callbacks,
module precedence and shared state/lifecycle/navigation/API behavior remain.
Before/after Node (38), full render comparison (18 states), focused pytest
(111 passed), full pytest (3540 passed, 505 skipped), bindings/syntax, actual
Chrome (48 shared shell; 30 employer; 40 interview, with host checks) and migrated
HTTP/graceful restart (91/91) pass. [I evidence](delivery/EVIDENCE-R4.md#r4-s1-t4i) owns exact
commands/counts/limits and separate final review/publication. Distinct final
completion self-review found no blocking issues. Scoped task commit `e7d7bc1`
is pushed to `origin/main`; remote
`e7d7bc11c31cb8e7cf65f1d974ef3543a128dc9c` was verified. This documentation-only
confirmation records publication; the final response reports the verified remote
SHA after this confirmation.
Only I completed, closing [T4](delivery/EVIDENCE-R4.md#r4-s1-t4); F13/sprint/PI
remain open. Working storage preserved; demo not restarted.

**Exact next task: R4-S1-Q - Sprint integration review**, not started.
Read its [PI-R4 section](delivery/PI-R4.md#r4-s1-q--sprint-integration-review),
[WORKFLOW](delivery/WORKFLOW.md) and T1-T4 evidence. Run the combined production
composition journey on migrated scratch storage in its own session. No Q work
or deployment started during I/T4 publication.

## Latest work

No duplicate mock/live sources remain for completed screens. Useful shared
formatters/styles and actual lifecycle/loading/navigation/file-reader/row-cache
callers remain in the HTML. Live account identity and org draft override design
props even with missing/failed data; all planes retain theme/domain callbacks,
navigation, search/advisory placement and neutral errors. Chrome separately
proves document reload and synthetic media/cleanup; HTTP proves graceful
restart and exact saved state. Fakes prove mechanics, not provider or measured
quality. Working DB and 715 unrelated tracked files match baseline. The completed
T4 task record is folded under its stable PI evidence anchor; A-I links remain.
Ignored-artifact removal stays outside scope;
[FEATURE_STATUS.md](../FEATURE_STATUS.md) owns the feature overview.

## Reusable validation setup

- Windows Python: `.resume/Scripts/python.exe`; full suite: `-m pytest -q
  --tb=short`. Use fake providers and isolated stores, never working storage.
  Latest sanitized runner: `.pytest_cache/run_r4_s1_t4i.py <tag> <Python args>`;
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
- Curation migrated HTTP/graceful restart: `scripts/smoke_curation_activation.py`;
  add `--browser` for real Chrome, including process restart and auth recovery.
- Operator accounts/retention/metrics/signal-quality migrated HTTP/graceful restart:
  `scripts/smoke_r3_s2_q.py`; add `--browser` for real account/curation Chrome.
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
  reload-disabled backend still needs a separately controlled restart for the
  extracted UI asset allowlist and earlier backend/PDF/rubric/lifecycle changes.
  Scratch validation does not update it.
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
