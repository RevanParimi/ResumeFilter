# R1-S1-T3b-D3d2 - Cross-store cleanup ordering and combined validation

Status: in progress (split 2026-09-24). Parent: [D3d](R1-S1-T3b-D3d.md). Prerequisite: D3d1.

Initial trace found distinct remaining boundaries; one child per session:

1. [D3d2a](R1-S1-T3b-D3d2a.md): report-only erasure after save, before response
   on shared ingest and standalone evaluation. Done 2026-09-24: full SQLite
   2463 passed, 163 skipped; focused PG 172 passed, 1 skipped; migrated HTTP/
   restart 29/29 per backend. Migrations, snapshot limits and self-review in child.
2. [D3d2b](R1-S1-T3b-D3d2b.md): profile-source persistence/refusal and response review. Both source
   ingesters now refuse observed subject/source erasure with safe 404 responses.
   Done 2026-09-24: full SQLite 2488 passed, 170 skipped; PG broad 96 passed,
   1 skipped plus final-source 52 passed, 1 skipped; migrated HTTP/restart 29/29
   per backend. Curation policy preserved; raw-display-name limitation documented.
   Login-state follow-up is split below; exact next task: **R1-S1-T3b-D3d2c2**.
3. [D3d2c](R1-S1-T3b-D3d2c.md): login-state cross-store cleanup and in-flight issuance/redemption.
   Split into c1 atomic existing-state cleanup (done 2026-09-26), c2 issuance
   (next) and c3 redemption (pending). `PortalService.erase` counts reports;
   CandidateStore now commits challenge and candidate deletion together.
   C1: full SQLite 2497 passed, 178 skipped; focused PG 113 passed, 2 skipped;
   HTTP/process exit/restart 24/24 per backend, migrations and self-review.
   Challenge insertion has no FK;
   issuance sends before persisting, and redemption consumes before establishing
   a principal. Trace interruption and stale work before choosing a repair.
   Preserve existing all-plane cleanup and fresh-signup policy; do not infer
   permanent bans or silently change identity/retention semantics. Split this
   child before implementation if necessary.
4. D3d2d: combined ordering evidence and parent coverage review after the above.
   Candidate-linked stores cascade, but each caller's response/refusal and
   non-FK lifetime still need their evidence. No whole-ingest/delivery claim.
   Include source list/portal aggregate response windows and shared curation
   raw-display-name retention/input policy; absence of an identity FK is not
   proof of de-identification.

D3d2a/b and c1 are done; c remains in progress and d pending. Only c1 was
completed in the resumed session; c2/c3 remain required before c can close.

Required review and acceptance:
- Trace `PortalService.erase`, login challenge cleanup, candidate deletion,
  report/source lifetime and remaining report-only ingest response windows.
  Identify which writes share a transaction or FK cascade and which commit
  separately. Distinguish interruption safety from a final response snapshot.
- Reproduce any uncovered persistence/refusal defect with controlled ordering
  on isolated stores. Cover both erasure entry points, another subject/tenant,
  retries, cleanup failure/interruption and unrelated errors where relevant.
- Preserve consent/identity/retention policy, independent report lifetime after
  resume-only deletion, fresh upload permission and existing generation guards.
  No working-data cleanup, historical identity inference or new policy implied.
- For code changes: red/green regressions, focused and full pytest, relevant
  migrated HTTP/restart journeys and recorded diff self-review. SQL concurrency
  or transaction changes require isolated PostgreSQL controlled connections and
  migration checks. Browser evidence applies if visible UI/handler contracts change.
- Record combined coverage and remaining gaps for D3d/D3/D/T3b/T3; do not close
  parents from individual-store evidence or claim atomic HTTP delivery.

Read [D3](R1-S1-T3b-D3.md), [D3d1](R1-S1-T3b-D3d1.md) and the relevant D1/D2,
D3b/D3c child evidence. Existing trace is a starting point, not validation.
