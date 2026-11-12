# Current handoff

Updated: 2026-11-12. Project: Veritas resume evaluation / talent platform.

## Start here

**R4-S2-T3C3D5Q complete; D5 closed.** Published A/B baseline is `160a991`.
The [PI status](delivery/PI-R4.md#r4-s2-t3c3d5q) and
[Q evidence](delivery/EVIDENCE-R4.md#r4-s2-t3c3d5q) own combined acceptance,
source/SQL inventory, aggregate budget, checks and both self-reviews.

The shared two-slot/20s pool covers limiter/ownership/claims and complete saved
input/report recovery. New combined coverage occupies both claim/recovery slots
plus all eight management slots; management and standalone intake remain
independent. Composed A/B HTTP/Chrome journeys prove saved-state/manual recovery
without late provider continuation. Only stale rate-limit comments changed;
no runtime behavior change was needed. Ordinary failure writes (including known
recovery refusal before intake), post-intake completion and final counts remain
synchronous D6 work. D5 closure does not mean every process SQL path is bounded.

Fresh SQLite selection: **33 passed / 33 PG environment skips**. PG-enabled
25-module selection: **901 passed / 10 skips / 18 warnings**. Combined
HTTP/restart **95/95** and persistence **71/71** on each DB; final actual Chrome
**74/74**, Python UI **20**, offline UI **138**, static checks pass. Full pytest:
**4405 passed, 1170 skipped, 127 warnings**. All 616 code/config hashes match.
Owned PG is confirmed stopped; working DB/unrelated files and demo are untouched.
Evidence owns completion and the distinct final staged self-review. Scoped
publication follows; final response reports the verified remote commit.

**Exact next: R4-S2-T3C3D6 - Bound batch terminal SQL**, in a separate session.
Stop after Q publication; do not start D6 here. D6/Q, C3D and broader parents
remain open. Durable continuation remains T4.
Use per-command `-c credential.username=RevanParimi` for GCM account selection.

## Reusable validation setup

- Windows Python: `.resume/Scripts/python.exe`; full suite: `-m pytest -q
  --tb=short`. Use fake providers/isolated stores, sanitize inherited DEE
  configuration/keys and avoid the working `.env`.
- Q runner: `.pytest_cache/run_r4_s2_t3c3d5q.py <tag> <Python args>`; omitted
  args run full pytest. Owned PG runner/runtime:
  `.pytest_cache/run_r4_s2_t3c3d5q_postgres.py` /
  `r4-s2-t3c3d5q-pg-runtime.json` (stopped). Hash/preservation helper:
  `.pytest_cache/review_state_r4_s2_t3c3d5q.py check` / `preserve`.
  Portable PG distribution metadata: `.pytest_cache/r1-s1-t3a-v1-pg-runtime.json`.
  These ignored local artifacts are not portable setup guarantees.
- Combined HTTP/restart: `scripts/smoke_r4_s1_t3d.py
  --batch-processing`; actual Chrome: `scripts/check_ui_screening_extraction_browser.py
  --batch-processing`. Add HTTP `--postgres` only with an explicitly disposable
  `DEE_TEST_DB_URL`. Q evidence owns commands and results;
  historical admission/management setup stays in its linked PI evidence, not this handoff.
- Next processing work can reuse `scripts/smoke_r4_s1_t3d.py --persistence`
  (or `--expiry`, `--outcomes`, `--leases`, `--ingest-races`) for two-process
  leases/input/report/terminal and restart journeys. Existing controlled SQL/
  HTTP/browser harnesses should be extended rather than copied.
- UI: `node scripts/check_ui_bindings.js`; `node --check frontend/api.js`,
  `frontend/support.js`, `frontend/screening.js`. Actual Chrome needs existing
  CDN internet; bindings/source checks are not browser execution.
- CPython 3.13.11/current dependencies remain in use. Optional/environment skips
  do not prove omitted cases. Synthetic providers/media prove mechanics, not live
  ASR/codec compatibility, factual accuracy or measured quality. Same-agent
  self-review is not independent review. Historical detailed commands and counts
  belong to [PI evidence](delivery/EVIDENCE-R4.md).

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
