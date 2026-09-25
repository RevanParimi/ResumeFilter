# PI-R1 — Identity, erasure and consent

Status: in progress. Deleting or revoking access to a candidate's data must remain effective across reports, derived stores and concurrent requests.

2026-09-26 documentation organization: [feature summary](../../FEATURE_STATUS.md)
and [closed-group evidence archive](archive/README.md) added. Task and sprint
statuses are unchanged; detailed archived child records remain linked below.

Load only the current task section plus [WORKFLOW.md](WORKFLOW.md), not this entire PI by default.
Source entry points (paths relative to repository root): src/app/services/flywheel.py; src/app/graph/nodes/report.py; src/app/portal/service.py; src/app/ledger/store.py; src/app/features/; src/app/auth/; src/app/verification/
Task test lists are starting points verified during planning; select/add regression cases from actual callers at implementation time.
Every task inherits the workflow's full pytest, review and relevant journey gates. Task evidence lives in `tasks/<task-id>.md`.

## R1-S1 — Complete erasure

Sprint acceptance journey: Create two candidates, evaluate both, erase one, restart the app and inspect every retained sink. Repeat with erasure between evaluation and persistence. The other candidate remains intact; the erased candidate's content cannot return.

### R1-S1-T1 — Make new flywheel records erasable

Status: done (2026-09-09). Audit mapping: F05. Prerequisites: None; F01–F04 complete.
Evidence: [task record](tasks/R1-S1-T1.md). Full pytest 2163 passed;
production HTTP checks 16/16 and employer-outcome checks 21/21 passed.
Production retains no duplicate JSONL stream; legacy files remain for T2.

**Development:** Implement one explicit retention/ownership contract for new evaluation and outcome records. Prefer minimizing retained free text; if text is needed, use candidate-linked deletable storage. Cover standalone evaluations without inventing identity.

**Acceptance:** New reports and outcomes cannot write unmanaged candidate text. Portal/admin erasure reaches the selected sink. Failure is observable; never report complete erasure when a required sink failed. Preserve other candidates.

**Tests and journey:** Extend tests/test_flywheel_io.py, tests/test_report.py, tests/test_portal_service.py and tests/test_portal_api.py. Reproduce retained text first; then test two candidates, repeated deletion, outcome records and write/delete failure. Isolated HTTP evaluation → erase → inspect persistence.

**Review focus:** Trace every flywheel.log caller, all free-text fields including probes, and production builder wiring. Legacy files and in-flight races remain explicit T2/T3 gaps.

### R1-S1-T2 — Handle existing flywheel files safely

Status: done (2026-09-09). Audit mapping: F05. Prerequisites: R1-S1-T1.
Evidence: [task record](tasks/R1-S1-T2.md). Explicit-file offline utility and
whole-file retention policy implemented; focused 31 passed, CLI smoke 10/10,
full pytest 2186 passed. Existing user files remain untouched; no production
cleanup or whole-system erasure completion is claimed.

**Development:** Add an explicit legacy-file policy and an inspectable migration/cleanup utility. Dry-run reports counts and unresolvable ownership without printing personal text. Preserve source files by default.

**Acceptance:** Synthetic legacy records with known, deleted, missing and ambiguous owners have documented outcomes. Cleanup is idempotent, crash-safe and bounded to an explicit file. No blanket claim that removal of IDs anonymizes text.

**Tests and journey:** Temporary-file tests for dry-run no-write, malformed lines, ownership ambiguity, retry and interrupted replacement. CLI subprocess smoke on synthetic copies; never run apply on user data as part of this task.

**Review focus:** Review path containment, backup/retention implications and handling of records whose candidate has already been deleted. Existing-data application is a separate operation, not silently authorized here.

### R1-S1-T3 — Prevent writes after candidate erasure

Status: in progress (split 2026-09-10). Audit mapping: F05. Prerequisites: R1-S1-T1, R1-S1-T2.
Children: R1-S1-T3a (reports/outcomes, done 2026-09-21), R1-S1-T3b
(interview/derived writes, in progress). [Parent record](tasks/R1-S1-T3.md).
T3b is split into [T3b-I](tasks/R1-S1-T3b-I.md) (interview mutations, done 2026-09-21)
and [T3b-D](tasks/R1-S1-T3b-D.md) (derived stores/cross-store ordering/ingest,
in progress, split into D1 vector persistence, D2 fingerprints/ingest and
D3 screening/disclosure audits/cross-store ordering).
T3b-I: focused SQLite 76 passed, PostgreSQL 83 passed; full SQLite 2213 passed,
17 PostgreSQL skips; real HTTP/restart 15/15. Self-review and migration checks
recorded. [T3b-D1](tasks/R1-S1-T3b-D1.md) done: erased feature writes return None
and the API counts them as skipped. Focused SQLite 35 passed; PostgreSQL 45
passed, zero skips; full SQLite 2223 passed, 23 PostgreSQL skips; migrated
HTTP/restart 15/15 per backend, migration up/down/up and self-review recorded.
[T3b-D2](tasks/R1-S1-T3b-D2.md) split 2026-09-22 into D2a resolved ingest
and D2b post-ingest fingerprints. [D2a](archive/R1-S1-T3b-D2a.md) done:
erasure after identity resolution returns candidate_erased (HTTP 422/failed
batch item). Focused SQLite 64 passed; PostgreSQL runner 71 passed, 2 SQLite-only
skips; HTTP/restart 12/12 per backend and migrations passed. Full SQLite pytest
2234 passed, 32 skipped; self-review recorded.
[D2b](archive/R1-S1-T3b-D2b.md) done: fingerprint erasure maps to candidate_erased/
resume_erased (HTTP 422/failed batch item); concurrent duplicates are idempotent.
Focused SQLite 79 passed; PG runner 97 passed, four SQLite-only skips;
HTTP/restart 18/18 per backend and migrations passed. Full SQLite 2250 passed,
45 skipped; self-review recorded. D2 complete.
[D3](tasks/R1-S1-T3b-D3.md) split into D3a completion, D3b earlier retained
input, D3c audits and D3d ordering. [D3a](tasks/R1-S1-T3b-D3a.md) done:
erased completion safely fails and scrubs input under its lease; process counts
refused completion as a failed attempt. Existing completed scalar/count retention
is unchanged. Focused SQLite 65 passed; PG runner 78 passed, three SQLite-only
skips; HTTP/restart 19/19 per backend; migrations and self-review recorded.
Full SQLite 2266 passed, 61 skipped, 42 warnings.
[D3b](tasks/R1-S1-T3b-D3b.md) split into [D3b1](archive/R1-S1-T3b-D3b1.md)
recorded erasure-refusal cleanup (done 2026-09-22) and D3b2 durable input
association, ordinary failure/retry erasure and interrupted cleanup.
D3b1: failed status and input/hash/link/signal scrub commit together under the
lease; ordinary failures remain retryable. Focused SQLite 102 passed; PG runner
142 passed, seven SQLite-only skips; HTTP/restart 19/19 per backend; migrations
and self-review recorded. Full SQLite 2279 passed, 70 skipped, 42 warnings.
[D3b2](archive/R1-S1-T3b-D3b2.md) split into
[D3b2a](archive/R1-S1-T3b-D3b2a.md) successful-ingest retry references (done
2026-09-23) and D3b2b earlier unresolved input/report-only cleanup interruption.
D3b2a: private CASCADE resume references replace unlinked batch input in the
ingest commit; ordinary retries pin the same resume and respect the batch TTL.
Migration 0024 preserves legacy data and restores surviving input on downgrade.
Final durable SQLite 23 passed; PG runner 253 passed, 11 SQLite-only skips;
HTTP/worker termination/restart 18/18 per backend; full SQLite 2303 passed,
93 skipped, 42 warnings. Migrations, lock evidence and self-review recorded.
[D3b2b](archive/R1-S1-T3b-D3b2b.md) split 2026-09-23 into report interruption
[D3b2b1](archive/R1-S1-T3b-D3b2b1.md) (done) and unresolved/historical input D3b2b2.
D3b2b1: migration 0025 binds private retry references to report erasure in the
report-save transaction. Worker exit before completion or after rollback cannot
retain retry capability for an erased report. Surviving resumes and completed
counts/scalars remain intact; historical links are not inferred. SQLite focused
95 passed; PG runner 306 passed, 12 SQLite-only skips; full SQLite 2317 passed,
105 skipped, 44 warnings; HTTP/worker exit/restart 19/19 per backend. Migration
round trips, observed PG deletion blocking and self-review recorded.
[D3b2b2](archive/R1-S1-T3b-D3b2b2.md) done 2026-09-23. User authorized the
conservative cross-tenant pause policy. Initial-ingest generation locking and
migration 0026 prevent older unresolved/historical input from automatic recovery
after erasure; retain original TTL and allow distinct fresh uploads/bound retries.
Queue/retry display a generic re-upload instruction. Full SQLite **2332 passed,
115 skipped**, 44 warnings; PG focused **330 passed, 13 skipped**, with final-file
supplement **25 passed, 1 skipped**. Migrated HTTP/worker exit/restart **17/17 per
backend**; SQLite real-browser journey **21/21**. Populated migration preservation/
refusal, lock observation, self-review and unchanged working DB recorded. Node
unavailable; no frontend assets changed. Two final compatibility tests added
after full-suite collection passed separately on SQLite/PG.
D3b2b/D3b2/D3b are done. [D3c](tasks/R1-S1-T3b-D3c.md) split 2026-09-23
into [D3c1](archive/R1-S1-T3b-D3c1.md) materialization consent audit (done),
[D3c2](archive/R1-S1-T3b-D3c2.md) training-label audit/export (done), and
[D3c3](archive/R1-S1-T3b-D3c3.md) matching disclosure (done). Each has a
separate caller/refusal contract; complete one child per session.
D3c1 returns a narrow missing-candidate refusal after audit rollback; materialization
counts the erased subject as skipped and continues surviving subjects. Consent
policy/fields remain unchanged. Full SQLite **2353 passed, 123 skipped**, 44 warnings;
PG focused **104 passed, 1 skipped**, 16 warnings; HTTP/restart **19/19 per backend**.
Observed FK blocking, migration up/down/up, clean shutdown and self-review recorded.
D3c2 done: audit erasure skips that subject; final per-subject existence checks
exclude stale examples with or without auditing, preserving stored consent and
survivor labels. Snapshot/file-delivery limits are explicit. Full SQLite **2371
passed, 142 skipped**, 44 warnings; PG focused **151 passed, 2 skipped**, 16 warnings;
HTTP/subprocess/restart **3/3 outer and 13/13 worker checks per backend**.
Observed FK blocking, migrations and self-review recorded; parquet dependency
guard checked (PyArrow absent). No working-data changes.
D3c3 done 2026-09-24: matching disclosure rollback/retry removes vanished
subjects without losing survivor audits; final existence reads filter match/board
results and counts. Scores/order, ownership, consent policy and API shapes stay
unchanged. Full SQLite **2398 passed, 158 skipped**, 44 warnings; PG focused
**167 passed, 3 skipped**, 16 warnings; HTTP/restart **21/21 per backend**.
Observed FK locking, migrations and self-review recorded. Response snapshot
limits remain explicit. D3c and its three children are done.
[D3d](tasks/R1-S1-T3b-D3d.md) split into D3d1 shared-ingest response checks and
D3d2 cross-store cleanup ordering/combined validation. [D3d1](tasks/R1-S1-T3b-D3d1.md)
done 2026-09-24: observed candidate/resume erasure after fingerprint/evaluation
returns 422 on both upload routes and scrubbed batch failure. Short input,
evaluate=False and report-save refusal are covered. Reads remain snapshots;
resume-only erasure preserves independent report lifetime. Full SQLite **2445
passed, 161 skipped**, 44 warnings; final focused PostgreSQL **84 passed**, zero
skips; migrated HTTP/restart **36/36 per backend**. Migrations, clean shutdown,
self-review, preserved working DB recorded. Node unavailable; no frontend change
or browser claim. D3d2 is split into D3d2a report-only response, D3d2b profile
sources, D3d2c login state and D3d2d combined validation.
[D3d2a](tasks/R1-S1-T3b-D3d2a.md) done 2026-09-24: final report lookups refuse
observed report-only erasure on admin/org uploads and standalone evaluation;
batches use existing cleanup/no-retry behavior. Candidate/resume records survive;
fresh requests remain permitted. Full SQLite **2463 passed, 163 skipped**, 44
warnings; focused PostgreSQL **172 passed, 1 skipped**, 17 warnings; migrated
HTTP/restart **29/29 per backend**, migration up/down/up, clean shutdown and
self-review recorded. Node unavailable; no frontend change or browser claim.
[D3d2b](tasks/R1-S1-T3b-D3d2b.md) done 2026-09-24: source FK erasure rolls back
and becomes a safe 404; fresh exact-row checks refuse vanished subjects/sources.
Both adapters and implicit GitHub handle lookup preserve unrelated errors,
unavailable-source behavior and shared taxonomy retention. Full SQLite **2488
passed, 170 skipped**, 44 warnings; PG broad **96 passed, 1 skipped**, 16 warnings,
plus final-source **52 passed, 1 skipped**, 1 warning. Migrated HTTP/restart
**29/29 per backend**, observed PG FK blocking, migration round trips, clean
shutdown and self-review recorded. Node unavailable; no frontend/browser claim.
Shared raw curation display names are not guaranteed de-identified; aggregate
read windows and this policy residual remain D3d2d.
[D3d2c](tasks/R1-S1-T3b-D3d2c.md) is split into c1 atomic existing login-state
cleanup, c2 issuance and c3 redemption. [D3d2c1](tasks/R1-S1-T3b-D3d2c1.md)
done 2026-09-26: existing challenge cleanup and candidate deletion now share a
transaction, preserving rollback/retry and unrelated principals. Full SQLite
**2497 passed, 178 skipped**, 44 warnings; focused PG **113 passed, 2 skipped**,
16 warnings; migrated HTTP/process exit/restart **24/24 per backend**. Observed
PG consume blocking, migration up/down/up, clean shutdown and diff self-review
recorded. Node bindings 402/402 passed; no frontend/browser or live-email claim.
Exact next child: **R1-S1-T3b-D3d2c2**. D3d2c/D3d2/D3d/D3/D/T3b/T3/F05/R1-S1-Q
remain open; snapshot reads do not lock across delivery.
No whole-ingest erasure guarantee.
Validation prerequisite [R1-S1-T3a-V1](archive/R1-S1-T3a-V1.md) is done:
aware UTC bindings fix the PostgreSQL feature timestamp failures. Final focused
PostgreSQL 93 passed; full PostgreSQL 2208 passed, zero skips; full SQLite
2198 passed, 10 PostgreSQL skips. Feature HTTP/restart 12/12 on each backend;
T3a erasure HTTP/restart 19/19 on SQLite; migration up/down/up and self-review
recorded. Historical timestamp repair requires a separate policy. Parent T3,
F05 and R1-S1-Q remain open.

**Development:** Make persistence reject stale evaluation/report/outcome work after erasure; cover the transaction boundary rather than only checking existence before work.

**Acceptance:** Controlled concurrent interleavings cannot recreate candidate-linked text, reports or derived rows after deletion. No arbitrary sleep-based race tests. Client receives a defined failure or cancellation response.

**Tests and journey:** Extend tests/test_report_cascade.py, tests/test_portal_service.py and tests/test_interview_erasure.py where applicable. Barrier-controlled write/delete tests on isolated SQLite and PostgreSQL; real HTTP sequence and restart inspection.

**Review focus:** Review time-of-check/time-of-use gaps and cross-store ordering. Treat unavailable PostgreSQL evidence as awaiting validation, not a passed concurrency gate.

### R1-S1-Q — Sprint integration review

Status: pending. Prerequisites: all tasks in R1-S1.

Run the sprint acceptance journey above through the actual app composition on a migrated scratch database. Use HTTP/subprocess checks for backend sprints and a real browser for UI sprints; fake external providers. Run full pytest and the required PostgreSQL/browser gates from the task records. Review the final combined diff for broken ownership, data lifecycle, fallback and compatibility boundaries. Record command results and unresolved findings in `tasks/R1-S1-Q.md`. Fix acceptance-blocking regressions within this closure task; unrelated improvements return to the backlog. Missing required evidence means awaiting validation, not done. Stop after this task and name the next sprint task.

## R1-S2 — Enforce current authorization

Sprint acceptance journey: Materialize while consent is active; revoke/expire it; then search, match, export and train at an earlier as_of. Historical timestamps must not restore current access. Verify candidate and organization isolation.

### R1-S2-T1 — Apply current consent to serving

Status: pending. Audit mapping: F06. Prerequisites: R1-S1-Q.

**Development:** Keep historical feature values separate from present authorization. Enforce current purpose/org-scoped consent at search and job matching boundaries.

**Acceptance:** Revoked/expired grants mask or exclude gated values from scores, returned contributions and filters. Ungated values remain usable. A historical as_of cannot bypass current consent.

**Tests and journey:** Extend tests/test_talent_search_api.py, tests/test_job_store_match.py and tests/test_features_materialize.py. Active → materialize → revoke → search/match tests with two candidates/orgs; valid and expired grants.

**Review focus:** Review direct store callers, per-org scope and ranking explanations, not only response field removal.

### R1-S2-T2 — Apply current consent to exports and training

Status: pending. Audit mapping: F06. Prerequisites: R1-S2-T1.

**Development:** Reuse the explicit authorization policy for CSV/Parquet export and training-label/outcome joins; define invalidation/re-materialization behavior.

**Acceptance:** Cached consent.allowed cannot authorize a revoked use. No gated data survives through labels or optional export formats. Historical snapshot semantics remain testable.

**Tests and journey:** Extend tests/test_features_export.py, tests/test_features_build_training_set.py and tests/test_features_training_export.py. API → materialize → revoke → export/train smoke, including optional-format behavior and missing grants.

**Review focus:** Inspect streaming/iterator timing, purpose differences and alternate direct-call entry points; avoid one copied consent rule per consumer.

### R1-S2-T3 — Close contact-verification attempt races

Status: pending. Audit mapping: F09; F04 residual. Prerequisites: R1-S2-T2.

**Development:** Make VerificationStore challenge attempts and consumption atomic without changing the already-fixed login OTP contract.

**Acceptance:** Concurrent failures do not lose increments; exhausted/expired/superseded challenges cannot succeed. Exactly defined repeated-success semantics; no fake phone delivery.

**Tests and journey:** Extend tests/test_verification_store.py, tests/test_verification_service.py and tests/test_verification_api.py. Controlled competing transactions on PostgreSQL plus offline service regressions.

**Review focus:** Review exact challenge identity, lock/update predicates and transaction isolation. SQLite sequential tests alone cannot close this concurrency task.

### R1-S2-T4 — Separate asserted contacts from identity changes

Status: pending. Audit mapping: F01 residual. Prerequisites: R1-S2-T3.

**Development:** Document and enforce proof required to bind/change login identity or merge profiles. Inspect current email/phone hints without automatically repairing existing records.

**Acceptance:** An upload cannot change a verified principal's ownership. Legitimate verified changes have a defined path or explicit refusal. Existing F01 cases remain green; persisted anomalies are inventoried only.

**Tests and journey:** Extend tests/test_candidate_store.py, tests/test_portal_identity.py and tests/test_auth_service.py. Two principals, conflicting contacts, verified change and unverified upload attempts through public APIs.

**Review focus:** Review account-claim assumptions and tenant disclosure. Split schema migration from workflow into a child task if both cannot fit one session.

### R1-S2-Q — Sprint integration review

Status: pending. Prerequisites: all tasks in R1-S2.

Run the sprint acceptance journey above through the actual app composition on a migrated scratch database. Use HTTP/subprocess checks for backend sprints and a real browser for UI sprints; fake external providers. Run full pytest and the required PostgreSQL/browser gates from the task records. Review the final combined diff for broken ownership, data lifecycle, fallback and compatibility boundaries. Record command results and unresolved findings in `tasks/R1-S2-Q.md`. Fix acceptance-blocking regressions within this closure task; unrelated improvements return to the backlog. Missing required evidence means awaiting validation, not done. Stop after this task and name the next sprint task.
