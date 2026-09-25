# R1-S1-T3b-D3d2c2 - Challenge issuance across erasure

Status: pending. Parent: [D3d2c](R1-S1-T3b-D3d2c.md). Prerequisite: D3d2c1.

Trace issue_code's send-before-persist boundary against erasure. A send begun
before cleanup can insert a new non-FK challenge afterward. Define an ordering
contract and meaningful controlled regressions before repair. Preserve send-failure
retry, all-plane cleanup, unknown-address anti-enumeration and fresh signup after
erasure. No permanent contact ban or external messages. Consider how the contract
will compose with c3 redemption; split further only if needed before implementation.

Require SQLite/PostgreSQL competing connections, both erasure API doors, migrated
HTTP/restart, applicable migration gates, focused/full pytest and diff self-review.
Parent remains open until c3 and combined validation are complete.
