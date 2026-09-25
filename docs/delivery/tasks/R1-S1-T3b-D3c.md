# R1-S1-T3b-D3c - Candidate-linked audit races

Status: done (2026-09-24; split 2026-09-23). Parent: [D3](R1-S1-T3b-D3.md).

Three callers have different refusal and response contracts. One child per chat:

1. [D3c1](../archive/R1-S1-T3b-D3c1.md): feature.materialize consent-audit erasure race;
   safely skip the erased subject and continue materializing surviving subjects.
   Done 2026-09-23: full SQLite 2353 passed, 123 skipped; PG focused 104 passed,
   1 skipped; HTTP/restart 19/19 per backend, observed locking and self-review
   recorded in the child.
2. [D3c2](../archive/R1-S1-T3b-D3c2.md): training.label audit/export erasure races. Done
   2026-09-23: audit erasure cancels the subject; final existence reads exclude
   stale examples with or without auditing, preserving stored consent policy.
   Full SQLite 2371 passed, 142 skipped; PG focused 151 passed, 2 skipped;
   HTTP/subprocess/restart 3/3 outer and 13/13 worker checks per backend.
   Snapshot/file-delivery limits, migration chain and self-review recorded.
3. [D3c3](../archive/R1-S1-T3b-D3c3.md): match.surface disclosure audit/response race.
   Done 2026-09-24: rollback/retry omits vanished subjects, preserves survivor
   scores and audits, and final existence reads filter matches/counts on both
   match and board routes. Full SQLite 2398 passed, 158 skipped; PG focused
   167 passed, 3 skipped; migrated HTTP/restart 21/21 per backend. Observed FK
   blocking, migration chain, snapshot limits and self-review recorded.

Existing consent snapshots/current-consent policy changes remain separately
scheduled. No whole-ingest or response-time erasure guarantee is implied.
All three bounded caller contracts are complete. Exact next task:
**R1-S1-T3b-D3d**. D3/D/T3b/T3/F05/R1-S1-Q remain open.
