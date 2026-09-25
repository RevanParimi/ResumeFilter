# R1-S1-T3b-D3b2 - Durable screening input and interrupted cleanup

Status: done (2026-09-23; all children complete). Parent: [D3b](../tasks/R1-S1-T3b-D3b.md).

Two boundaries require separate evidence and one child per session:

1. [D3b2a](R1-S1-T3b-D3b2a.md): successful ingest atomically transfers batch
   retry input to an erasure-bound resume reference. Ordinary failures and
   interrupted processing may retry that exact surviving resume, without
   resolving it as a new identity. Candidate/resume erasure must remove the
   retry reference even when no completion/failure cleanup runs.
   Done 2026-09-23: final durable SQLite 23 passed; PG runner 253 passed;
   HTTP/worker termination/restart 18/18 per backend; full SQLite 2303 passed,
   93 skipped. Migration, retention and self-review evidence recorded in D3b2a.
2. [D3b2b](R1-S1-T3b-D3b2b.md): earlier identity-resolution/failed-first-ingest retention and
   interruptions before the first durable association. Also assess report-only
   erasure interrupted before D3a cleanup and legacy unlinked records. Create
   its acceptance record before implementing; do not infer ownership from raw
   text or silently delete existing ambiguous input. Split 2026-09-23 into
   D3b2b1 report-only interrupted cleanup and D3b2b2 unresolved/legacy input.

D3b2a binds successful-ingest input to an exact resume. D3b2b1 binds reports
atomically; D3b2b2 now guards earlier unresolved/historical input with the
user-authorized cross-tenant generation barrier. All children are done; evidence
is in their records. D3b2b2 full SQLite 2332 passed, PG focused 330 passed plus
25 final-file checks; HTTP/worker restart 17/17 per backend, SQLite browser 21/21.

Consent, anonymous completed counts/scalars, tenant isolation and the original
batch-input retention window remain intact. No permanent fresh-upload ban or
whole-ingest erasure guarantee. Exact next task: **R1-S1-T3b-D3c**.
