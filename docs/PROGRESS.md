# Current handoff

Updated: 2026-11-16. Project: Veritas resume evaluation / talent platform.

## Start here

**R4-S2-T3C3E3B complete**, started 15 November; baseline `015ff8e`.
[Contract/evidence](delivery/EVIDENCE-R4.md#r4-s2-t3c3e3b) owns pre-code scope,
red/green, exact validation, completion and separate self-reviews. Both rights
POSTs now own full limiter/validation/identity/create/audit/final-existence work
in existing `portal_writes`, shared with consent writes. No new pool/config/schema.
422/429/404 remain; observed erasure refuses success, and raw SQL/private notes
are excluded from application failure logs. Human review/identity/extractions remain.

Request/quota/audit commits remain separate. Pending/cancelled/failed replies may
follow a commit; retain admission until settlement, recover with deliberate own
GETs and never auto-replay. Early empty snapshots do not prove rollback; audit
failure can leave a saved request without its audit. Snapshots do not lock later
delivery. Global/driver/drain limits remain. Working DB/demo are preserved.

Full pytest **4572 passed / 1321 skipped**. Focused **465 passed / 122 PG skips**;
PG-enabled **567 passed**, no skips. Actual Chrome write/read compatibility
**29/29 + 33/33**. Both DBs' HTTP/restart: submissions **50/50**, rights reads
**49/49**, portal reads/reports **54/54**, consent writes **34/34**. Bindings
**638/19**, JS/Python compilation pass. Reviewed **616** code/config hashes
match; owned PG stop **0**, status **3**. All gates ended; no rerun needed.
Completion review/publication outcome and verified tracking SHA are reported
with this session. Stop after the scoped final review/publication sequence.

**Exact next: R4-S2-T3C3E3C - Bound reviewed-rights decisions**, not started.
Read/refine its existing decision/late-write contract before code. E3/C/Q and
broader parents remain open. Only B closes here. No new pool/config/schema/
scorer; partial commits, snapshot and per-process/global/driver/drain limits
remain explicit. Working DB/demo and unrelated work are preserved.

## Reusable validation setup

- Latest C3E3B sequential gate: `.pytest_cache/gates_r4_s2_t3c3e3b.py`; all
  required checks, including full, are complete.
  Sanitized runner: `.pytest_cache/run_r4_s2_t3c3e3b.py <tag> <Python args>`;
  omitted args run full pytest. Owned PG runner/runtime:
  `run_r4_s2_t3c3e3b_postgres.py` / `r4-s2-t3c3e3b-pg-runtime.json`
  under `.pytest_cache/`. Reviewed-state/preservation helper:
  `.pytest_cache/review_state_r4_s2_t3c3e3b.py check` / `preserve`.
- Git uses per-command `-c credential.username=RevanParimi`; HTTP/1.1 worked
  for the remote preflight after a transient empty HTTP response.
- Windows Python: `.resume/Scripts/python.exe`; full suite: `-m pytest -q
  --tb=short`. Use fake providers/isolated stores, sanitize inherited DEE
  configuration/keys and avoid the working `.env`.
- Portable PG distribution metadata: `.pytest_cache/r1-s1-t3a-v1-pg-runtime.json`.
  Local ignored helpers are not portable setup guarantees. Add `--postgres` only
  with an explicitly disposable `DEE_TEST_DB_URL`; prior owned E3A/E2 PGs are
  confirmed stopped. B's owned disposable local cluster is also stopped.
- The combined evidence owns exact HTTP/Chrome modes and commands. Extend the
  existing isolated worker, two-process and browser harnesses instead of copying
  them. Prior D5/D6 setup and results remain in their linked evidence records.
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
