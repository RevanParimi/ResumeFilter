# R1-S1-T3b-D3b - Screening input before completion

Status: done (2026-09-23; all children complete). Parent: [D3](R1-S1-T3b-D3.md).

Initial trace: registration stores raw_text/hash without a candidate ID. Claim leaves
them intact; extraction and CandidateStore.ingest resolve/store the identity;
fingerprinting and evaluation run before complete first writes the item links.
IngestRefused reaches fail; explicit erasure failures now scrub text (D3b1),
while earlier interrupted/unlinked input remains. Completed anonymous
counts/scalars and existing consent policy must remain unchanged.

Bounded children, one per session:

1. [D3b1](../archive/R1-S1-T3b-D3b1.md): atomically scrub recorded erasure refusals in fail;
   preserve leases, ordinary failure retries, tenant isolation and API accounting.
   Done 2026-09-22: focused SQLite 102 passed, PG runner 142 passed; HTTP/restart
   19/19 per backend; full SQLite 2279 passed, 70 skipped. Self-review recorded.
2. [D3b2](../archive/R1-S1-T3b-D3b2.md): durable association of pre-completion input with resolved identity,
   erasure during ordinary failure/retry and interrupted cleanup (including
   crashes before fail and D3a rollback-to-cleanup). Create acceptance record
   split into D3b2a successful-ingest retry references (done 2026-09-23) and
   D3b2b earlier unresolved input/report-only cleanup interruptions.

D3b1 and every D3b2 child are done. D3b2b2 closes unresolved/historical input
with the authorized cross-tenant pause, original TTL and fresh-upload behavior.
Final full SQLite 2332 passed; PG focused 330 passed plus 25 final-file checks;
HTTP/worker exit/restart 17/17 per backend, SQLite browser journey 21/21.
Detailed evidence and self-review are in the child records.
Exact next task: **R1-S1-T3b-D3c**. D3 and its ancestors remain open.
No permanent re-upload ban, registration-time identity inference, or whole-ingest
erasure guarantee is claimed.
