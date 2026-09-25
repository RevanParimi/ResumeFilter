# R1-S1-T3b - Interview and derived-store writes racing erasure

Status: in progress (split 2026-09-21). Parent: [T3](R1-S1-T3.md).

This scope crosses independent persistence boundaries; complete one child per chat.

1. [R1-S1-T3b-I](R1-S1-T3b-I.md): interview start, turn and completion writes;
   defined refusals, transactional audit rollback, response reload races.
   Done 2026-09-21: SQLite focused 76 passed, PostgreSQL focused 83 passed;
   full SQLite 2213 passed, 17 PostgreSQL skips; HTTP/restart 15/15. Self-review,
   migration checks and limitations recorded in the child evidence.
2. [R1-S1-T3b-D](R1-S1-T3b-D.md): fingerprints, feature vectors, matching/screening retained data,
   cross-store ordering, disclosure audits and remaining candidate-ingest races.
   In progress, split into D1 (feature-vector persistence), D2
   (fingerprints/ingest) and D3 (screening/disclosure audits/cross-store ordering).
   [D1](R1-S1-T3b-D1.md) done: focused SQLite 35 passed, PostgreSQL 45 passed;
   full SQLite 2223 passed, 23 PostgreSQL skips; HTTP/restart 15/15 each backend.
   D2 complete: D2a resolved ingest and D2b fingerprints done.
   [D2a](../archive/R1-S1-T3b-D2a.md): full SQLite 2234 passed, 32 skipped; focused PG
   runner 71 passed, 2 SQLite-only skips; HTTP/restart 12/12 per backend.
   [D2b](../archive/R1-S1-T3b-D2b.md): full SQLite 2250 passed, 45 skipped; focused PG
   runner 97 passed, four SQLite-only skips; HTTP/restart 18/18 per backend.
   [D3](R1-S1-T3b-D3.md) split into D3a completion (done), D3b earlier retained
   input (done), D3c audits (done) and D3d ordering. D3d1 shared-ingest response
   checks, D3d2a report-only checks and D3d2b source ingestion are done;
   **R1-S1-T3b-D3d2c2** is next, with current evidence in [D3d2c1](R1-S1-T3b-D3d2c1.md).
   D3a: full SQLite 2266 passed,
   61 skipped; PG focused 78 passed; HTTP/restart 19/19 per backend.
   D3 and this parent remain open.

Initial trace: interviews use candidate/session CASCADE foreign keys, but start
flush, turn commit and completion commit expose raw SQL failures on stale work.
Answer reload can return None after a committed turn is erased. Portal erasure
deletes login state then the candidate; SQL cascades cover interviews. Derived
stores have separate writes (fingerprint save, vector upsert, match disclosure
audit, screening completion); their detailed analysis remains child D.

Parent remains open until both children and their required evidence pass.

Resumed login-state update (2026-09-26): [D3d2c1](R1-S1-T3b-D3d2c1.md)
is done: existing challenge/candidate cleanup shares one transaction. Full SQLite
2497 passed, 178 skipped; focused PG 113 passed, 2 skipped; HTTP/interruption/
restart 24/24 per backend. Next is D3d2c2 issuance; c3 redemption and D3d2d combined
validation remain open. This parent is not closed by c1.
