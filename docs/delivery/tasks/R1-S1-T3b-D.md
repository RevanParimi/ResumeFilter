# R1-S1-T3b-D - Derived stores and ingest erasure races

Status: in progress (split 2026-09-21). Parent: [T3b](R1-S1-T3b.md).

Independent persistence boundaries require bounded children, one per chat:

1. [R1-S1-T3b-D1](R1-S1-T3b-D1.md): feature-vector insert/update erasure
   refusals and materialization API accounting. Done 2026-09-21: focused SQLite
   35 passed, PostgreSQL 45 passed; HTTP/restart 15/15 on each backend; full
   SQLite 2223 passed, 23 PostgreSQL skips. Review/migration evidence in D1.
2. [R1-S1-T3b-D2](R1-S1-T3b-D2.md): fingerprint and candidate-ingest races, including identity
   resolution through resume commit and the post-ingest fingerprint boundary.
   Done 2026-09-22: D2a resolved ingest and D2b post-ingest fingerprints complete.
   D2b: focused SQLite 79 passed, PG runner 97 passed, four SQLite-only skips;
   full SQLite 2250 passed, 45 skipped; HTTP/restart 18/18 per backend.
   Migration/review evidence in the children. This parent remains open.
3. [R1-S1-T3b-D3](R1-S1-T3b-D3.md): retained screening completion,
   matching/disclosure and materialization-consent audits; cross-store erasure
   ordering. Split 2026-09-22: D3a completion, D3b earlier retained input,
   D3c audits, D3d cross-store ordering. D3a done: full SQLite 2266 passed,
   61 skipped; PG focused 78 passed; HTTP/restart 19/19 per backend. D3b and
   descendants and D3c are done. D3d1 response checks are done; exact next child
   is **R1-S1-T3b-D3d2c2**, login-state erasure. D3d2a report-only response and
   D3d2b source ingestion checks are done; current evidence and snapshot/curation
   limits in [D3d2b](R1-S1-T3b-D3d2b.md).
   Login-state ordering and combined validation remain D3d2c/d.

Initial trace: feature-vector writes use candidate CASCADE but expose insert
integrity/update stale-row errors. Fingerprint save separately commits a row
after ingest. Matching commits candidate-linked disclosure audits after ranking
a previously loaded pool. Screening completes a separate batch item with retained
signals. LedgerStore separately commits feature.materialize and training.label
audits; include those in D3's persistence review without changing consent policy.
Detailed repair/validation of those latter paths remains D3.

Parent stays open until all children and required evidence are complete.

Resumed login-state update (2026-09-26): [D3d2c1](R1-S1-T3b-D3d2c1.md)
is done: existing challenge/candidate cleanup shares one transaction. Full SQLite
2497 passed, 178 skipped; focused PG 113 passed, 2 skipped; HTTP/interruption/
restart 24/24 per backend. Next is D3d2c2 issuance; c3 redemption and D3d2d combined
validation remain open. This parent is not closed by c1.
