# Current handoff

Updated: 2026-11-14. Project: Veritas resume evaluation / talent platform.

## Start here

**R4-S2-T3C3E1 done; only this child closes.** Baseline `0402fa8`.
[Contract/evidence](delivery/EVIDENCE-R4.md#r4-s2-t3c3e1) owns the pre-code C3E
split, acceptance, reproducers/corrections, reviews and exact checks. The three
portal GETs now own complete composed SQL/DTO/final erasure checks in a separate
2-slot/20s pool. Stale read replies cannot overwrite newer account/refresh state;
safe pending/failure offers explicit GET reload. Unexpected read failures retain
correlated generic 500s while omitting private exception content from logs.

Final full: **4470 passed / 1227 skipped / 127 warnings**. Focused **363 passed /
28 PG skips**; PG-enabled 18 modules **371 passed**. Portal and report-compat HTTP/
restart each **54/54 on both DBs**; actual Chrome **33/33**, offline Node **130**,
bindings **635/19** pass. All **616** code/config hashes match. Owned PG stop **0**,
independent status **3**; working DB/unrelated files and demo are preserved.

**Exact next: R4-S2-T3C3E2 - Bound candidate consent writes**, in a separate
session. E2-E8/Q, C3E and broader parents stay open; read guards do not close
write callback/uncertainty work. Completion and distinct final staged self-review
are recorded; scoped commit/push and remote verification follow, then stop.
No schema, scorer or provider-policy change. Snapshots and per-process budgets retain their
documented global/driver/drain limits.

### Last completed

**C3DQ/C3D closed**, published at `0402fa8`, remote verified. Its
[combined evidence](delivery/EVIDENCE-R4.md#r4-s2-t3c3dq) owns exact prior results,
initial timing failure/unchanged reruns, scoped 16-slot subtotal and limitations.
Use per-command `-c credential.username=RevanParimi` for GCM account selection.

## Reusable validation setup

- Completed C3E1 gates: `.pytest_cache/gates_r4_s2_t3c3e1.py`; do not restart.
  Sanitized runner: `.pytest_cache/run_r4_s2_t3c3e1.py <tag> <Python args>`;
  omitted args run full pytest. Owned PG runner/runtime:
  `run_r4_s2_t3c3e1_postgres.py` / `r4-s2-t3c3e1-pg-runtime.json`
  under `.pytest_cache/`. Reviewed-state/preservation helper:
  `.pytest_cache/review_state_r4_s2_t3c3e1.py check` / `preserve`.
- Windows Python: `.resume/Scripts/python.exe`; full suite: `-m pytest -q
  --tb=short`. Use fake providers/isolated stores, sanitize inherited DEE
  configuration/keys and avoid the working `.env`.
- Portable PG distribution metadata: `.pytest_cache/r1-s1-t3a-v1-pg-runtime.json`.
  Local ignored helpers are not portable setup guarantees. Add `--postgres` only
  with an explicitly disposable `DEE_TEST_DB_URL`; owned C3E1 PG is stopped.
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
