# R1-S1-T3b-D2 - Ingest and fingerprint erasure races

Status: done, 2026-09-22. Parent: [D](R1-S1-T3b-D.md).

Trace: ingest resolves an existing candidate, updates its identity timestamp,
flushes, writes/reuses a resume and commits an extraction in one transaction.
The identity UPDATE holds the write lock until commit. Erasure before that
UPDATE raises StaleDataError; erasure after it waits, then cascades all rows.
Fingerprint persistence runs in a separate transaction after ingest returns.

Bounded children, one per chat:
- [D2a](../archive/R1-S1-T3b-D2a.md): resolved-candidate ingest through commit; done.
  Focused SQLite 64 passed; PostgreSQL runner 71 passed (2 SQLite-only skips);
  full SQLite 2234 passed, 32 skipped; HTTP/restart 12/12 per backend.
  Migration up/down/up and self-review recorded in the child evidence.
- [D2b](../archive/R1-S1-T3b-D2b.md): post-ingest fingerprint persistence; done.
  Missing candidates/resumes safely refuse; concurrent duplicates are idempotent.
  Focused SQLite 79 passed; PG runner 97 passed, four SQLite-only skips; full
  SQLite 2250 passed, 45 skipped; HTTP/restart 18/18 per backend. Migration
  up/down/up and self-review recorded in the child evidence.

No tombstone or new permanent ban on uploading an erased identity is introduced.
A new upload resolving after erasure cannot identify the erased row; that is
distinct from replaying work that already resolved that row. D2 is complete;
D stays open. Next: D3 screening completion, audits and cross-store ordering.
Erasure after a successful fingerprint commit can still race later response/
screening work; this is not a whole-ingest erasure guarantee.
