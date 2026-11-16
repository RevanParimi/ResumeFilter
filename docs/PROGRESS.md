# Current handoff

Updated: 2026-11-16. Project: Veritas resume evaluation / talent platform.

## Start here

**R4-S2-T3C3E3C complete**, baseline `4e8b26d`.
[C contract/evidence](delivery/EVIDENCE-R4.md#r4-s2-t3c3e3c) owns pre-code scope,
red/green, findings/fixes, exact validation, completion and separate self-reviews.
Complete operator decisions use existing `portal_writes`, shared with four
candidate writes. New decisions commit request, allowed full-name/pin correction
and audit together. OPEN targets and observed final erasure refuse; human review,
actor/CSRF and policy remain. No new pool/config/schema or historical repair.

Pending/cancelled/failed replies may follow a whole decision commit. Admission
lasts until settlement; recover with deliberate request/identity/audit GETs,
never automatic decision replay. Submission quota/request/audit remain separate
commits. Final guards are snapshots; process/global/driver/drain limits remain.

Full pytest **4599 passed / 1347 skipped**. Focused **568 passed / 180 skips**,
affected baseline-guard selection **15 passed / 15 PG skips**; fresh PG selection
**728 passed**, no skips. Actual Chrome **29/29 + 33/33**. Both DBs' six HTTP/
restart modes pass (decision **54/54**). Bindings **638/19**, JS/Python compilation
and diff checks pass. Initial browser-readiness and PG baseline-setup failures
were fixed/reviewed and affected checks rerun; evidence owns details. Latest
**616** reviewed code/config hashes match after full. Both owned PG attempts
stopped; latest stop **0**, independent status **3**. No gate is still running.
Distinct final staged self-review is complete, with no blocking finding; scoped
publication follows. Final response reports the verified tracking SHA. Working
DB/demo remain preserved.

**Exact next: R4-S2-T3C3E3Q - Review combined reviewed-rights acceptance**,
pending, separate chat. Re-inventory combined reads/submissions/decisions and
budgets before its fresh integration gates. Only C closes; E3/Q and broader
parents remain open. Stop after scoped final review/publication, without E4.

## Reusable validation setup

- Completed sequential gate: `.pytest_cache/gates_r4_s2_t3c3e3c.py`. Sanitized
  runner: `.pytest_cache/run_r4_s2_t3c3e3c.py <tag> <Python args>`; omitted args
  run full. Owned PG runner/runtime: `run_r4_s2_t3c3e3c_postgres.py` /
  `r4-s2-t3c3e3c-pg-runtime.json` under `.pytest_cache/`.
  State/preservation helper: `review_state_r4_s2_t3c3e3c.py check` / `preserve`.
- Windows Python: `.resume/Scripts/python.exe`; full: `-m pytest -q --tb=short`.
  Clear inherited DEE config/keys and avoid working `.env`. Fake providers and
  isolated stores only. Add `--postgres` only for explicitly disposable storage.
  Portable PG distribution: `.pytest_cache/r1-s1-t3a-v1-pg-runtime.json`.
  Ignored local helpers are not portable setup guarantees.
- Git per-command `-c credential.username=RevanParimi -c http.version=HTTP/1.1`
  works with configured `origin/main`; never print credentials.
- UI bindings/source checks are not browser execution. Chrome compatibility
  uses existing CDN internet with fake/capture providers. Optional skips do not
  prove omitted cases; fakes prove mechanics, not live-provider delivery/quality.
  Same-agent self-review is not independent review. Historical exact commands
  and results belong to [PI evidence](delivery/EVIDENCE-R4.md).

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
