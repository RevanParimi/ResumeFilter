# R1-S1-T3b-D3d2c3 - Redemption across erasure and login closure

Status: pending. Parent: [D3d2c](R1-S1-T3b-D3d2c.md). Prerequisite: D3d2c2.

Trace verify_code's committed consume, principal establishment and session creation
against erasure, including stale verification that recreates an erased candidate.
Define bounded acceptance before implementation; preserve legitimate fresh signup,
single use, generic refusal, all-plane cleanup and unrelated principals. Compose
with c1 atomic cleanup and c2 issuance ordering. Contact-verification attempt races
remain R1-S2-T3; do not silently broaden into that independent flow.

Require meaningful red/green tests, controlled SQLite/PostgreSQL connections,
both erasure doors, migrated HTTP/interruption/restart, applicable migration gates,
focused/full pytest and diff self-review. Record combined login-state evidence
before closing D3d2c. D3d2d still owns wider ordering/aggregate/curation review.
