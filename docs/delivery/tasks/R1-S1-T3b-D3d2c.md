# R1-S1-T3b-D3d2c - Login-state erasure ordering

Status: in progress (split 2026-09-24). Parent: [D3d2](R1-S1-T3b-D3d2.md). Prerequisite: D3d2b.

One child per session, in order:
1. [D3d2c1](R1-S1-T3b-D3d2c1.md): atomic candidate/existing-challenge erasure,
   rollback, interruption and retry. Done 2026-09-26: full SQLite 2497 passed,
   178 skipped; focused PG 113 passed, 2 skipped; migrated HTTP/process exit/
   restart 24/24 per backend, migration round trips and self-review recorded.
2. [D3d2c2](R1-S1-T3b-D3d2c2.md): competing code issuance across erasure. Next task.
3. [D3d2c3](R1-S1-T3b-D3d2c3.md): competing redemption and combined login validation.

Atomic cleanup alone cannot fence a send already in flight or a consumed code
whose principal/session is established later. No parent closure from c1 alone.

Start with `PortalService.erase`, `AuthService.erase_login_state`, challenge
issuance/redemption and `AuthStore` transactions. Before c1, erasure read the
report count, separately committed challenge deletion by email hash, then deleted
the candidate. C1 now commits existing challenge and candidate deletion together.
Candidate sessions cascade; login challenges have no FK. Issuance
sends before persistence; redemption consumes before establishing the principal.
Issuance/redemption remain trace findings requiring c2/c3 validation.

Before implementation, define bounded acceptance for interruption, competing
issuance/redemption and retry. Split into named children if this cannot fit one
focused session. Preserve all-plane challenge cleanup, candidate signup/login
semantics, fresh signup permission, anti-enumeration behavior and unrelated
principals. No permanent contact ban, inferred identity or working-data cleanup.

Required evidence for code changes: meaningful red/green regression, both admin
and portal erasure entry points with isolated actors/stores, controlled SQLite/
PostgreSQL connections, relevant migration round trips, migrated HTTP/restart
or interruption journey, full pytest and recorded diff self-review. Use synthetic
capture/null email only; no external messages or live credentials.

Combined validation remains D3d2d. Carry forward the explicit residuals: source
list/portal aggregate response windows and shared curation raw-display-name
retention policy. D3d2 and higher parents remain open.
