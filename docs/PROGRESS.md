# Current handoff

Updated: 2026-10-30. Project: Veritas resume evaluation / talent platform.

## Start here

**R4-S2-T3C3C2B complete.** Baseline `813bde3` is published. This session
completes only fingerprint/comparison work; A is complete, C/Q and all broader
parents remain open. [B evidence](delivery/EVIDENCE-R4.md#r4-s2-t3c3c2b) owns the
contract, regressions, checks and reviews.

Admin/employer uploads and batches reuse the initial-ingest pool (two slots /
20-second caller wait) for complete fingerprint computation/save/comparison/
advisory assessment, with separate admission between phases. SQL sessions stay
on workers; async providers stay on the caller. Safe full/closed/pending 503/
Retry-After returns no IDs. A later refusal can follow a committed resume.
Timeout/cancel retains admission; late work never resumes evaluation or replays.
Batch uncertainty preserves its lease/checkpoint for deliberate recovery after
expiry. See the [intake budget](../OPERATING.md#candidate-intake-persistence-budget).

Red responsiveness reproduced at all three phases/doors. Focused **524 passed /
233 skipped**; uncertainty/ownership and actual SQLite lock/erasure regressions
pass; migrated SQLite HTTP/restart and two-process races **41/41 each**, final
actual Chrome **29/29**, offline UI **62/62**, bindings/syntax/five-module
compilation pass. Actual PG **748 passed / 9 skipped**; PG migrated HTTP/restart
and two-process races **41/41 each**. Full pytest: **3939 passed, 789 skipped,
127 warnings**. All **616 reviewed code/config hashes** match. Owned PG is
confirmed stopped; working DB preserved and port-8000 demo untouched. Fakes
establish mechanics, not live quality. Completion records and distinct final
staged self-review are complete; the linked evidence records that self-review.
Authorized commit/push follows; the final response reports the verified remote.

**Exact next: R4-S2-T3C3C2C - Bound intake report and subject SQL**, under its
[contract](delivery/PI-R4.md#r4-s2-t3c3c2c). Do not implement C in this session.
C2 closes only after C/Q. Use per-command `-c credential.username=RevanParimi`
for GCM account selection.

Report/subject and batch claim/failure/terminal SQL still run synchronously;
competing SQLite writers can block those paths. Limits are per service/process;
timeout cannot kill threads or promise rollback, and driver waits/drain have no
new hard deadline. Direct low-level callers own scheduling unless they supply
the executor. Single uploads without stable identity hints can create another
subject on deliberate fresh upload; no new idempotency key. Present guards remain
snapshots across later erasure/delivery.

## Reusable validation setup

- C3C2B runner: `.pytest_cache/run_r4_s2_t3c3c2b.py <tag> <Python args>`;
  omitted args run full pytest. Owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t3c3c2b_postgres.py` /
  `r4-s2-t3c3c2b-pg-runtime.json` (stopped). Review/preservation helper:
  `.pytest_cache/review_state_r4_s2_t3c3c2b.py check` / `preserve`.
  Complete fingerprint/admission/late-write/manual recovery/restart:
  `scripts/smoke_r4_s1_t3c.py --candidate-fingerprint-workers`; two-process races:
  `scripts/smoke_r4_s1_t3d.py --ingest-races`; add `--postgres` only with an
  explicitly disposable `DEE_TEST_DB_URL`. Actual screening Chrome:
  `scripts/check_ui_screening_extraction_browser.py --candidate-fingerprint-workers`.
- C3C2A runner: `.pytest_cache/run_r4_s2_t3c3c2a.py <tag> <Python args>`;
  omitted args run full pytest. Owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t3c3c2a_postgres.py` /
  `r4-s2-t3c3c2a-pg-runtime.json` (stopped). Review/preservation helper:
  `.pytest_cache/review_state_r4_s2_t3c3c2a.py check` / `preserve`.
  Initial ingest SQL/admission/late-write/manual recovery/restart:
  `scripts/smoke_r4_s1_t3c.py --candidate-ingest-workers`; two-process races:
  `scripts/smoke_r4_s1_t3d.py --ingest-races`; add `--postgres` only with an
  explicitly disposable `DEE_TEST_DB_URL`. Actual screening Chrome:
  `scripts/check_ui_screening_extraction_browser.py --candidate-ingest-workers`.
- C3C1 runner: `.pytest_cache/run_r4_s2_t3c3c1.py <tag> <Python args>`;
  omitted args run full pytest. Owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t3c3c1_postgres.py` /
  `r4-s2-t3c3c1-pg-runtime.json` (stopped). Review/preservation helper:
  `.pytest_cache/review_state_r4_s2_t3c3c1.py check` / `preserve`.
  Operator candidate reads/key SQL/admission/late-rotation/recovery/restart:
  `scripts/smoke_r4_s1_t3c.py --candidate-record-workers`; add `--postgres`
  only with an explicitly disposable `DEE_TEST_DB_URL`. Existing portal Chrome
  compatibility: `scripts/check_ui_evaluate_browser.py`.
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
