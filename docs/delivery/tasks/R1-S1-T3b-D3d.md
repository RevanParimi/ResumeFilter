# R1-S1-T3b-D3d - Cross-store ordering and response review

Status: in progress (split 2026-09-24). Parent: [D3](R1-S1-T3b-D3.md).

Two distinct contracts need separate focused sessions:

1. [D3d1](R1-S1-T3b-D3d1.md): shared ingest candidate/resume response snapshot
   after fingerprint comparison/evaluation. Refuse observed erasure on admin/org
   uploads and batches, including short inputs without fingerprints.
   Done 2026-09-24: full SQLite 2445 passed, 161 skipped; final focused PostgreSQL
   84 passed; migrated HTTP/restart 36/36 per backend, migrations and self-review.
2. [D3d2](R1-S1-T3b-D3d2.md): cross-store cleanup ordering and combined validation.
   In progress, split into D3d2a report-only response (done), D3d2b profile sources
   (done), D3d2c login state (c1 done, c2 next) and D3d2d combined validation.
   Trace portal/admin deletion, challenge issuance/redemption across erasure,
   report/source lifetimes and remaining report-only response windows. Define
   acceptance before implementation, split further if needed. No new retention
   or identity policy is implicit in this review.

Initial trace: both candidate-delete routes delegate to PortalService.erase;
it reads report count, separately deletes login challenges by email hash, then
deletes the candidate. Candidate-linked SQL rows use CASCADE; screening generation
and retry-reference safeguards live in the earlier D3b migrations. These facts
do not prove interruption-safe cleanup of non-FK rows or atomic response delivery.

D3c/D3d1/D3d2a/b snapshot limits remain explicit. D3d2b completed 2026-09-24:
full SQLite 2488 passed, 170 skipped;
PG broad 96 passed, 1 skipped plus final-source 52 passed, 1 skipped;
migrated HTTP/restart 29/29 per backend. Curation policy/read-window residuals
are recorded in D3d2b and carried into D3d2d.
D3d/D3/D/T3b/T3/F05/R1-S1-Q remain open until the remaining evidence is complete.

Resumed login-state update (2026-09-26): [D3d2c1](R1-S1-T3b-D3d2c1.md)
is done: existing challenge/candidate cleanup shares one transaction. Full SQLite
2497 passed, 178 skipped; focused PG 113 passed, 2 skipped; HTTP/interruption/
restart 24/24 per backend. Next is D3d2c2 issuance; c3 redemption and D3d2d combined
validation remain open. This parent is not closed by c1.
