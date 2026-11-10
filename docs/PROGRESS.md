# Current handoff

Updated: 2026-11-10. Project: Veritas resume evaluation / talent platform.

## Start here

**R4-S2-T3C3D4A complete.** Published baseline D3 is `7c36a7f`.
[A contract/evidence](delivery/EVIDENCE-R4.md#r4-s2-t3c3d4a) owns acceptance,
red/green, review findings/resolutions, final checks and the staged review.
D4 was split before implementation; only A closes, with B/C/Q still open.

Four employer batch view GETs use complete owning-session reads on a separate
pool (four slots accommodate three parallel view reads plus discovery). Final
batch visibility refuses observed deletion/ownership loss without rewriting
cursors. Safe full/closed/pending responses retain accepted admission through
actual completion, without replay or assessment. Human GET recovery preserves
selection/reference and upload drafts; account/refresh/page guards reject stale
callbacks. Paging waits for its base read, a filtered empty page can continue,
and a partial summary retains its saved name/counts. Auth/CSRF, projections,
retention, success DTOs, advisory/scoring and write scheduling remain.

Final full pytest **4324 passed, 1114 skipped, 127 warnings**. Actual PG-enabled
selection **719 passed, 10 SQLite-only skips, 18 warnings**; both databases'
migrated two-actor HTTP/graceful restart **50/50**; actual worker Chrome **39/39**.
Offline UI **98** (including 68 shared evaluation cases), bindings **605/18**,
syntax and 10-module compilation pass. Earlier interrupted/failed attempts remain
in evidence. All **616** corrected code/config hashes match. Working DB/unrelated
files preserved, demo not restarted, owned PG confirmed stopped. Completion
records and distinct final staged self-review are recorded; scoped commit/push
follows. The final response reports the verified remote commit.

**Exact next: R4-S2-T3C3D4B - Bound batch registration**, in a separate session.
Stop after A publication; do not start B here. B/C/Q, D4, D5-D6/Q, C3D and broader
parents remain open. Use per-command `-c credential.username=RevanParimi` for
GCM account selection.

The [batch read budget](../OPERATING.md#batch-view-read-execution-budget) owns
defaults/limits. Counts, individual values and scope/delivery remain snapshots,
not erasure/update locks; summary still reads the whole batch. Direct/internal
callers own scheduling. Per-process waits do not bound global SQL/auth, whole
requests, drivers, drain or memory. Fakes prove mechanics, not live quality.

## Reusable validation setup

- D4A runner: `.pytest_cache/run_r4_s2_t3c3d4a.py <tag> <Python args>`; omitted
  args run full pytest. Owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t3c3d4a_postgres.py` / `r4-s2-t3c3d4a-pg-runtime.json`
  (stopped).
  Hash/preservation helper: `.pytest_cache/review_state_r4_s2_t3c3d4a.py check` /
  `preserve`. HTTP/restart: `scripts/smoke_r4_s1_t3d.py --batch-read-workers`;
  add `--postgres` only with an explicitly disposable URL. Actual Chrome:
  `scripts/check_ui_screening_extraction_browser.py --batch-read-workers`.
  A evidence owns the exact selections, commands, failed/incomplete attempts.
- D3 runner: `.pytest_cache/run_r4_s2_t3c3d3.py <tag> <Python args>`; omitted args
  run full pytest. Owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t3c3d3_postgres.py` / `r4-s2-t3c3d3-pg-runtime.json`
  (stopped).
  Hash/preservation helper: `.pytest_cache/review_state_r4_s2_t3c3d3.py check` /
  `preserve`. Migrated HTTP/restart: `scripts/smoke_r4_s1_t3c.py
  --evaluation-publication-workers`; add `--postgres` only with an explicitly
  disposable URL. Actual Chrome: `scripts/check_ui_evaluate_browser.py
  --evaluation-publication-workers`. D3 evidence owns exact commands/results.
- D2 runner: `.pytest_cache/run_r4_s2_t3c3d2.py <tag> <Python args>`; omitted args
  run full pytest. Owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t3c3d2_postgres.py` / `r4-s2-t3c3d2-pg-runtime.json`
  (stopped). Hash/preservation helper:
  `.pytest_cache/review_state_r4_s2_t3c3d2.py check` / `preserve`. Both-door
  outcome-worker HTTP/restart: `scripts/smoke_r4_s1_t3c.py --outcome-write-workers`;
  append `--postgres` only with an explicitly disposable URL. Actual outcome
  worker Chrome: `scripts/check_ui_evaluate_browser.py --outcome-write-workers`.
  D2 evidence above owns exact selections, red/green, failed test-policy/fixture
  attempts, static commands and results.
- D1 runner: `.pytest_cache/run_r4_s2_t3c3d1.py <tag> <Python args>`;
  omitted args run full pytest. Final full/PG orchestrator:
  `.pytest_cache/final_gates_r4_s2_t3c3d1.py`. Owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t3c3d1_postgres.py` /
  `r4-s2-t3c3d1-pg-runtime.json` (stopped). Hash/preservation helper:
  `.pytest_cache/review_state_r4_s2_t3c3d1.py check` / `preserve`.
  Report-worker HTTP/restart: `scripts/smoke_r4_s1_t3c.py --report-read-workers`;
  add `--postgres` only with an explicitly disposable URL. Actual saved-report
  Chrome: `scripts/check_ui_evaluate_browser.py`. D1 evidence above owns exact
  focused selection, compile/browser/static commands, failed attempts and results.
- CQ runner: `.pytest_cache/run_r4_s2_t3c3cq.py <tag> <Python args>`;
  omitted args run full pytest. Sequential orchestrator:
  `.pytest_cache/final_gates_r4_s2_t3c3cq.py`. Owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t3c3cq_postgres.py` /
  `r4-s2-t3c3cq-pg-runtime.json`; separate unchanged-family rerun:
  `.pytest_cache/rerun_r4_s2_t3c3cq_postgres.py` /
  `r4-s2-t3c3cq-rerun-pg-runtime.json` (both stopped). Hash/preservation helper:
  `.pytest_cache/review_state_r4_s2_t3c3cq.py check` / `preserve`.
  CQ evidence above owns exact commands/results for all seven record/intake/source
  modes on `scripts/smoke_r4_s1_t3c.py`, two-process races, affected Chrome and the
  retained initial PG failure. Only use PG with an explicitly disposable URL.
  Earlier C1/C2/C3 helpers/results remain in their linked evidence records.
- B2's sanitized runner: `.pytest_cache/run_r4_s2_t3c3b2.py <tag> <Python args>`;
  omitted args run full pytest. Owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t3c3b2_postgres.py` /
  `r4-s2-t3c3b2-pg-runtime.json` (stopped). Review/preservation helper:
  `.pytest_cache/review_state_r4_s2_t3c3b2.py check` / `preserve`.
  Three-plane session SQL/admission/late-write/manual recovery/restart:
  `scripts/smoke_r4_s1_t3a.py --auth-session-workers`; real Chrome:
  `scripts/check_ui_screening_extraction_browser.py --auth-session-workers`.
  Add HTTP `--postgres` only with an explicitly disposable `DEE_TEST_DB_URL`.
- B1's sanitized runner: `.pytest_cache/run_r4_s2_t3c3b1.py <tag> <Python args>`;
  omitted args run full pytest. Owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t3c3b1_postgres.py` /
  `r4-s2-t3c3b1-pg-runtime.json` (stopped). Review/preservation helper:
  `.pytest_cache/review_state_r4_s2_t3c3b1.py check` / `preserve`.
  Redemption SQL/query/late-commit/admission/recovery/restart:
  `scripts/smoke_r4_s1_t3a.py --auth-redemption-workers`; real Chrome:
  `scripts/check_ui_screening_extraction_browser.py --auth-redemption-workers`.
  Add HTTP `--postgres` only with an explicitly disposable `DEE_TEST_DB_URL`.
- Windows Python: `.resume/Scripts/python.exe`; full suite: `-m pytest -q
  --tb=short`. Use fake providers and isolated stores, never working storage.
  C3A's runner: `.pytest_cache/run_r4_s2_t3c3a.py <tag> <Python args>`;
  omitted args run full pytest. Clear inherited DEE config/keys and avoid .env.
- Principal resolution SQL/touch admission/uncertainty/graceful restart:
  `scripts/smoke_r4_s1_t3a.py --auth-resolution-workers`; real Chrome:
  `scripts/check_ui_screening_extraction_browser.py --auth-resolution-workers`.
  Add HTTP `--postgres` only with an explicitly disposable `DEE_TEST_DB_URL`.
  Owned PG runner/runtime: `.pytest_cache/run_r4_s2_t3c3a_postgres.py` /
  `r4-s2-t3c3a-pg-runtime.json`, stopped. Reviewed-state/preservation helper:
  `.pytest_cache/review_state_r4_s2_t3c3a.py check` / `preserve`.
- Contact code admission/SQL/mail stalls/late completion/recovery/graceful restart:
  `scripts/smoke_r3_s1_t2.py --contact-code-workers`; actual Chrome:
  `scripts/check_ui_verification_browser.py --contact-code-workers`.
  Append HTTP `--postgres` only with an explicitly disposable `DEE_TEST_DB_URL`.
  C2's owned PG runner/runtime: `.pytest_cache/run_r4_s2_t3c2_postgres.py` /
  `r4-s2-t3c2-pg-runtime.json`, stopped.
- Auth code worker admission/SQL/mail stalls/late success/graceful restart:
  `scripts/smoke_r4_s1_t3a.py --auth-code-workers`; actual Chrome:
  `scripts/check_ui_screening_extraction_browser.py --auth-code-workers`.
  Append HTTP `--postgres` only with an explicitly disposable `DEE_TEST_DB_URL`.
  C1's owned PG runner/runtime: `.pytest_cache/run_r4_s2_t3c1_postgres.py` /
  `r4-s2-t3c1-pg-runtime.json`, stopped. Resend/contact/portal Chrome:
  `scripts/check_ui_evaluate_browser.py`.
- Aggregate request bodies / partial-upload latency / graceful HTTP restart:
  `scripts/smoke_r4_s1_t3d.py --body-limit`. Actual screening Chrome including
  ingress refusal, Clear/fresh-file recovery and reload:
  `scripts/check_ui_screening_extraction_browser.py --body-limit`.
- PDF child stalls/shared admission/timeout/recovery/graceful HTTP restart:
  `scripts/smoke_r4_s1_t3d.py --pdf-execution`. Actual PDF 503/fresh-file
  recovery/reload Chrome: `scripts/check_ui_screening_extraction_browser.py
  --pdf-execution`.
- Two-process batch scheduling/terminal outcomes/retry/graceful restart:
  `scripts/smoke_r4_s1_t3d.py --persistence` (or `--expiry` / `--outcomes` /
  scheduling `--leases`);
  append `--postgres` only with an
  explicitly disposable DEE_TEST_DB_URL. Latest owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t1b2b2b_postgres.py` / `r4-s2-t1b2b2b-pg-runtime.json`;
  stopped.
- Candidate/resume creation contention across two app processes and restart:
  `scripts/smoke_r4_s1_t3d.py --ingest-races`; add `--postgres` only with an
  explicitly disposable `DEE_TEST_DB_URL`. T2's owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t2_postgres.py` / `r4-s2-t2-pg-runtime.json`, stopped.
  It covers this journey and the focused group named in T2 evidence.
- Combined R4-S1 production composition/API/UI/graceful restart:
  `scripts/smoke_r4_s1_t1b.py --integration`; append `--postgres` only with an
  explicitly disposable DEE_TEST_DB_URL. Q's owned PG runner/runtime:
  `.pytest_cache/run_r4_s1_q_postgres.py` / `r4-s1-q-pg-runtime.json`; stopped.
- Screening/UI HTTP contract/graceful restart: `scripts/smoke_r4_s1_t3d.py`.
  Actual screening Chrome: `scripts/check_ui_screening_extraction_browser.py`.
  Candidate/source/ownership/graceful restart: `scripts/smoke_r4_s1_t3c.py`.
  Evaluation/report/outcome/restart journey: `scripts/smoke_r3_s1_q.py`
  (Windows stop is forced). Auth/ledger/employer/features/portal/graceful SQL journey: `scripts/smoke_r4_s1_t3a.py`.
  Contract fixture: `tests/fixtures/api_contract_r4_s1_t3.json`; pure extractions
  retain it. Provenance journey: `scripts/smoke_r4_s1_t2.py` (blocked Chroma imports,
  default/legacy settings, migrated HTTP and graceful restart). Provider lifecycle
  journey: `scripts/smoke_r4_s1_t1b.py`, or
  `--postgres` with an explicitly disposable DEE_TEST_DB_URL. Prior owned PG
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
  Working DB remains at 0023; only scratch stores were migrated to 0030.
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
  holds the candidate/SQLite writer lock with existing socket timeouts. PDF
  admission is per service, with per-parse limits; global RSS and HTTP body
  concurrency remain separate. Unsupported runtimes/input can refuse safely.
  Remaining SQL/SMTP work, cross-worker overlay and reproducibility remain R4.
