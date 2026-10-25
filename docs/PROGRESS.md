# Current handoff

Updated: 2026-10-25. Project: Veritas resume evaluation / talent platform.

## Start here

**R4-S2-T2 complete.** Its
[contract/evidence](delivery/EVIDENCE-R4.md#r4-s2-t2) owns the bounded scope,
regressions, harness corrections, exact checks and implementation self-review.
Unresolved contact lookups now lock/recheck before creating candidates; existing
candidate writes serialize caller-owned resume deduplication and unique versions.
Email ordering agrees with mailbox redemption; missing/ambiguous/incompatible
hints keep distinct-submission policy. Proof, tenant ownership, consent and
erasure remain. No migration/UI/working-store change; historical duplicates and
separate provider/report work remain possible.

Full pytest: **3659 passed, 623 skipped**; PostgreSQL-configured focused:
**551 passed, 12 skipped**; SQLite/PostgreSQL two-process HTTP/restart:
**41/41 + 31/31 each**. Bindings, Python compilation and whitespace pass.
The evidence owns initial harness corrections and clean final runs. Fakes prove
mechanics, not live providers or empirical quality.

**Exact next: R4-S2-T3 - Bound requests and move blocking work off-loop**;
read its [PI contract](delivery/PI-R4.md#r4-s2-t3--bound-requests-and-move-blocking-work-off-loop).
Do not start T3 in this session. F14/sprint/PI remain open for T3/T4/Q.
Earlier R4-S1 and R4-S2-T1 remain closed.

Implementation and distinct final staged self-reviews found no blocker.
Authorized scoped publication uses tracking branch `origin/main`; the final
response reports the verified remote SHA. Working DB and unrelated files match
baseline; 643 code hashes name the reviewed/tested state. Demo untouched; owned
PG, HTTP and pytest validation processes stopped.
[FEATURE_STATUS.md](../FEATURE_STATUS.md) owns the feature overview.

## Reusable validation setup

- Windows Python: `.resume/Scripts/python.exe`; full suite: `-m pytest -q
  --tb=short`. Use fake providers and isolated stores, never working storage.
  Latest sanitized runner: `.pytest_cache/run_r4_s2_t2.py <tag> <Python args>`;
  omitted args run full pytest. Clear inherited DEE config/keys and avoid .env.
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
  holds the candidate/SQLite writer lock with existing socket timeouts. PDF limits
  are per parse, not aggregate RSS/concurrency; unsupported runtimes/input can
  refuse safely. Aggregate bounds/cross-worker overlay/reproducibility remain R4.
