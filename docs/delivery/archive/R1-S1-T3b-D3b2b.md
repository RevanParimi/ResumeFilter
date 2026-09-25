# R1-S1-T3b-D3b2b - Earlier input and interrupted report cleanup

Status: done (2026-09-23; both children complete). Parent: [D3b2](R1-S1-T3b-D3b2.md).

Tracing shows two independent boundaries; complete one child per session:

1. [D3b2b1](R1-S1-T3b-D3b2b1.md): atomically associate saved reports with
   private retry input, so report-only erasure works after worker interruption
   and between failed completion rollback and cleanup. Implement first because
   its ownership is explicit and requires no legacy ownership inference.
   Done 2026-09-23: report save atomically binds retry to report erasure.
   Full SQLite 2317 passed; PostgreSQL focused 306 passed; migrated HTTP/worker
   exit/restart 19/19 per backend, migrations and self-review recorded.
2. [D3b2b2](R1-S1-T3b-D3b2b2.md): first extraction/identity resolution, failed-first-ingest
   interruptions before durable association, and historical unlinked input.
   Create its acceptance record before implementation. Current registration
   stores raw text without a known subject; ingest rollback leaves it intact.
   No safe ownership is established by similar text or by a missing identity.
   Preserve the existing TTL and do not silently delete ambiguous legacy input.
   Migration 0025 also leaves historical private references without inferred
   report links; document this boundary alongside historical unlinked raw input.
   Done 2026-09-23: user-authorized generation barrier pauses older unresolved
   input across tenants; migration 0026 quarantines historical input without
   deleting text or changing TTL. Full SQLite 2332 passed; PG focused 330 passed
   plus final-file supplement 25 passed; HTTP/worker exit/restart 17/17 each
   backend, SQLite browser journey 21/21. Self-review/migration evidence recorded.

No whole-ingest guarantee or permanent re-upload ban. Both children are done.
Exact next task: **R1-S1-T3b-D3c**; D3 and its ancestors remain open.
