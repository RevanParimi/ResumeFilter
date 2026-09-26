# R1-S1-T3b-D3d2c - Login-state erasure ordering

Status: in progress (split 2026-09-24). Parent: [D3d2](R1-S1-T3b-D3d2.md). Prerequisite: D3d2b.

| Child | Scope | Status |
|---|---|---|
| [D3d2c1](R1-S1-T3b-D3d2c1.md) | Atomic candidate/existing-challenge erasure, rollback, interruption and retry. | Done |
| [D3d2c2](R1-S1-T3b-D3d2c2.md) | Competing code issuance across erasure. | Done |
| [D3d2c3](R1-S1-T3b-D3d2c3.md) | Competing redemption and combined login validation. | Pending; next |

Trace PortalService.erase, AuthService issue/verify/erase_login_state and AuthStore
transactions. C1 moved challenge cleanup into the candidate-delete transaction.
C2 orders reserved sends and activation against cleanup without locking delivery
or banning fresh signup. A consumed code whose principal/session is established
later remains c3; the parent stays open until combined validation.

Acceptance: preserve all-plane cleanup, anti-enumeration, unrelated principals,
send-failure retry and legitimate fresh signup. No permanent contact ban, inferred
identity or working-data cleanup. Use synthetic capture/null email only.

Each code child needs red/green regressions, both API doors with isolated actors,
controlled SQLite/PostgreSQL connections, applicable migrations, migrated HTTP/
interruption/restart, full pytest and diff self-review. Child records own counts
and commands. Parent closes only after c3 combines the evidence. D3d2d still owns
wider aggregate-response windows and shared curation retention policy.
