# R1-S1-T3b-D3 - Screening, audits and cross-store ordering

Status: in progress (split 2026-09-22). Parent: [D](R1-S1-T3b-D.md).

Independent persistence boundaries require one bounded child per chat:

1. [D3a](R1-S1-T3b-D3a.md): screening completion after candidate/resume/report
   erasure; refusal, retained-input cleanup and accurate process accounting.
   Done 2026-09-22: focused SQLite 65 passed, PG runner 78 passed; HTTP/restart
   19/19 per backend; full SQLite 2266 passed, 61 skipped. Self-review and
   PostgreSQL migration/lock evidence recorded in D3a.
2. [D3b](R1-S1-T3b-D3b.md): screening input before completion, split into
   [D3b1](../archive/R1-S1-T3b-D3b1.md) recorded erasure-refusal cleanup and D3b2 durable
   identity association, ordinary failure/retry retention and interrupted cleanup.
   D3b1 done: focused SQLite 102 passed, PG runner 142 passed; HTTP/restart 19/19
   per backend; full SQLite 2279 passed, 70 skipped. Self-review recorded.
   D3b2 is split into successful-ingest retry references (D3b2a, done 2026-09-23)
   and earlier unresolved input/report-only cleanup (D3b2b).
   D3b and all descendants done 2026-09-23: D3b2b2's authorized generation
   barrier closes unresolved/historical input. Full SQLite 2332 passed; PG
   focused 330 passed plus 25 final-file checks; HTTP/restart 17/17 per backend,
   SQLite browser 21/21. Evidence/self-review in D3b2b2.
   Exact next child: **R1-S1-T3b-D3d2c2**.
3. [D3c](R1-S1-T3b-D3c.md): split into D3c1 materialization consent audit,
   D3c2 training-label audit/export, and D3c3 matching disclosure. Retain existing
   consent policy. D3c1 done: full SQLite 2353 passed, 123 skipped; PG 104 passed,
   1 skipped; HTTP/restart 19/19 per backend and self-review recorded.
   D3c2 done: training erasure refusal/final checks, full SQLite 2371 passed,
   PG focused 151 passed; HTTP/subprocess/restart recorded in its child.
   D3c3 done 2026-09-24: matching audit rollback/retry and final existence reads
   protect match/board snapshots. Full SQLite 2398 passed, 158 skipped; PG
   focused 167 passed, 3 skipped; HTTP/restart 21/21 per backend. D3c is done;
   snapshot delivery limits, migration evidence and self-review in child records.
4. [D3d](R1-S1-T3b-D3d.md): split into D3d1 shared-ingest response checks and
   D3d2 cross-store cleanup ordering/combined validation. D3d1 done 2026-09-24:
   full SQLite 2445 passed, 161 skipped; focused PostgreSQL 84 passed; migrated
   HTTP/restart 36/36 per backend, migrations and self-review. D3d2 is split;
   D3d2a report-only response done: full SQLite 2463 passed, 163 skipped; focused
   PG 172 passed, 1 skipped; HTTP/restart 29/29 per backend. D3d2b sources done:
   full SQLite 2488 passed, 170 skipped; PG broad 96 passed, 1 skipped plus final
   52 passed, 1 skipped; HTTP/restart 29/29 per backend. Login-state ordering is
   in progress (D3d2c1 done, c2 next); combined validation/read-window/curation
   residuals remain D3d2d.
   No whole-ingest guarantee follows from completion or individual-store fixes.

Initial trace: batch input is unlinked until ScreeningStore.complete; its
lease-checked UPDATE uses SET NULL foreign keys and currently exposes FK errors.
The service ignored complete's boolean (fixed D3a). Earlier ingest refusals call fail,
which retained input (explicit erasure refusals fixed D3b1; earlier association
and interrupted cleanup fixed D3b2). Matching writes disclosures after loading/ranking a pool.
LedgerStore materialization_consent audit erasure refusal is fixed in D3c1;
audit_training_label erasure refusal/final builder checks are fixed in D3c2;
matching disclosure audit/response snapshots are fixed in D3c3.

No changes to consent/scoring policy or to the existing anonymous completed
screening-count/scalar retention policy are authorized by this decomposition.
Parent remains open until all children and required evidence are complete.

Resumed login-state update (2026-09-26): [D3d2c1](R1-S1-T3b-D3d2c1.md)
is done: existing challenge/candidate cleanup shares one transaction. Full SQLite
2497 passed, 178 skipped; focused PG 113 passed, 2 skipped; HTTP/interruption/
restart 24/24 per backend. Next is D3d2c2 issuance; c3 redemption and D3d2d combined
validation remain open. This parent is not closed by c1.
