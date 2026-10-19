# PI-R1 — Identity, erasure and consent

Status: done (2026-10-09; bounded current-system acceptance, [Q scope/limits](EVIDENCE-R1.md#r1-s2-q)). Deleting or revoking access to a candidate's data must remain effective across reports, derived stores and concurrent requests.

2026-09-26 documentation organization: [feature summary](../../FEATURE_STATUS.md)
and [closed-group evidence archive](README.md) added. Task and sprint
statuses are unchanged; detailed archived child records remain linked below.

Load only the current task section plus [WORKFLOW.md](WORKFLOW.md), not this entire PI by default.
Source entry points (paths relative to repository root): src/app/services/flywheel.py; src/app/graph/nodes/report.py; src/app/portal/service.py; src/app/ledger/store.py; src/app/features/; src/app/auth/; src/app/verification/
Task test lists are starting points verified during planning; select/add regression cases from actual callers at implementation time.
Every task inherits [WORKFLOW.md](WORKFLOW.md). Reuse inline active task sections; completed records use PI evidence anchors.

## R1-S1 — Complete erasure

Sprint status: done (2026-10-06; [Q acceptance and limits](EVIDENCE-R1.md#r1-s1-q)).

Sprint acceptance journey: Create two candidates, evaluate both, erase one, restart the app and inspect every retained sink. Repeat with erasure between evaluation and persistence. The other candidate remains intact; the erased candidate's content cannot return.

### R1-S1-T1 — Make new flywheel records erasable

Status: done (2026-09-09). Audit mapping: F05. Prerequisites: None; F01–F04 complete.
Evidence: [task record](EVIDENCE-R1.md#r1-s1-t1). Full pytest 2163 passed;
production HTTP checks 16/16 and employer-outcome checks 21/21 passed.
Production retains no duplicate JSONL stream; legacy files remain for T2.

**Development:** Implement one explicit retention/ownership contract for new evaluation and outcome records. Prefer minimizing retained free text; if text is needed, use candidate-linked deletable storage. Cover standalone evaluations without inventing identity.

**Acceptance:** New reports and outcomes cannot write unmanaged candidate text. Portal/admin erasure reaches the selected sink. Failure is observable; never report complete erasure when a required sink failed. Preserve other candidates.

**Tests and journey:** Extend tests/test_flywheel_io.py, tests/test_report.py, tests/test_portal_service.py and tests/test_portal_api.py. Reproduce retained text first; then test two candidates, repeated deletion, outcome records and write/delete failure. Isolated HTTP evaluation → erase → inspect persistence.

**Review focus:** Trace every flywheel.log caller, all free-text fields including probes, and production builder wiring. Legacy files and in-flight races remain explicit T2/T3 gaps.

### R1-S1-T2 — Handle existing flywheel files safely

Status: done (2026-09-09). Audit mapping: F05. Prerequisites: R1-S1-T1.
Evidence: [task record](EVIDENCE-R1.md#r1-s1-t2). Explicit-file offline utility and
whole-file retention policy implemented; focused 31 passed, CLI smoke 10/10,
full pytest 2186 passed. Existing user files remain untouched; no production
cleanup or whole-system erasure completion is claimed.

**Development:** Add an explicit legacy-file policy and an inspectable migration/cleanup utility. Dry-run reports counts and unresolvable ownership without printing personal text. Preserve source files by default.

**Acceptance:** Synthetic legacy records with known, deleted, missing and ambiguous owners have documented outcomes. Cleanup is idempotent, crash-safe and bounded to an explicit file. No blanket claim that removal of IDs anonymizes text.

**Tests and journey:** Temporary-file tests for dry-run no-write, malformed lines, ownership ambiguity, retry and interrupted replacement. CLI subprocess smoke on synthetic copies; never run apply on user data as part of this task.

**Review focus:** Review path containment, backup/retention implications and handling of records whose candidate has already been deleted. Existing-data application is a separate operation, not silently authorized here.

### R1-S1-T3 — Prevent writes after candidate erasure

Status: done (2026-10-06; bounded development acceptance complete). Audit mapping: F05. Prerequisites: R1-S1-T1, R1-S1-T2.
The [T3 parent](EVIDENCE-R1.md#r1-s1-t3) owns the child map and acceptance scope.
[T3a](EVIDENCE-R1.md#r1-s1-t3a) (reports/outcomes) and [T3b](EVIDENCE-R1.md#r1-s1-t3b)
(interview/derived stores) are done. Their child and combined evidence satisfy
the bounded development acceptance; [D3d](EVIDENCE-R1.md#r1-s1-t3b-d3d) records response
and lifecycle limits. The actual empty named-database inventory below settles
the last curation row-retention gap. [Q](EVIDENCE-R1.md#r1-s1-q) records the bounded
current-system F05/sprint gate closure; future media remains R5-S1-T4.

Login scope [D3d2c](EVIDENCE-R1.md#r1-s1-t3b-d3d2c) is complete: atomic cleanup,
issuance and redemption have combined validation in
[c3](EVIDENCE-R1.md#r1-s1-t3b-d3d2c3). [D3d2d](EVIDENCE-R1.md#r1-s1-t3b-d3d2d) is split:
[aggregate refusal](EVIDENCE-R1.md#r1-s1-t3b-d3d2d1),
[curation policy](EVIDENCE-R1.md#r1-s1-t3b-d3d2d2) engineering and
[combined validation](EVIDENCE-R1.md#r1-s1-t3b-d3d2d3) are done. The user approved option A:
candidate/source-linked observations with a fixed 30-day review lifetime.
D2 implementation/validation is done: input/log boundaries (D2a), owned review
lifecycle (D2b) and legacy disposition tooling/policy validation (D2c). D2b completed
[storage foundation](EVIDENCE-R1.md#r1-s1-t3b-d3d2d2b1) (done) and
[runtime/reviewer switch](EVIDENCE-R1.md#r1-s1-t3b-d3d2d2b2) (done). The latter
is split into [owned store](EVIDENCE-R1.md#r1-s1-t3b-d3d2d2b2a) (done) and
[coupled activation](EVIDENCE-R1.md#r1-s1-t3b-d3d2d2b2b) (done). Owned capture,
reviewer API/UI and startup/daily maintenance are active. Counts-only inventory
and explicit selected disposition are validated on synthetic stores;
[D2c evidence](EVIDENCE-R1.md#r1-s1-t3b-d3d2d2c) owns final integrated policy checks.
[Combined evidence](EVIDENCE-R1.md#r1-s1-t3b-d3d2d3) owns final ordering/ancestor mapping.
[Working-data inventory/disposition decision](EVIDENCE-R1.md#r1-s1-t3b-d3d2d4) is done:
the actual named-database inventory is empty, so no cleanup selection or approval
was needed. T3 and its development ancestors close within that verified scope.
Historical aliases remain a compatibility exception in nonempty legacy stores;
backups/history and physical reclamation were not inventoried. Response checks
remain snapshots, not locks across delivery or a whole-ingest guarantee.
The separate [Q sprint integration review](EVIDENCE-R1.md#r1-s1-q) has passed.

Exact next task: [PROGRESS.md](../PROGRESS.md). Detailed test counts, commands,
review findings and limitations belong in the corresponding task evidence section, rather than
being copied through every ancestor. Q owns the sprint/F05 scope and limits. Historical
feature timestamp repair requires an explicit policy, separate from UTC binding.

**Development:** Make persistence reject stale evaluation/report/outcome work after erasure; cover the transaction boundary rather than only checking existence before work.

**Acceptance:** Controlled concurrent interleavings cannot recreate candidate-linked text, reports or derived rows after deletion. No arbitrary sleep-based race tests. Client receives a defined failure or cancellation response.

**Tests and journey:** Extend tests/test_report_cascade.py, tests/test_portal_service.py and tests/test_interview_erasure.py where applicable. Barrier-controlled write/delete tests on isolated SQLite and PostgreSQL; real HTTP sequence and restart inspection.

**Review focus:** Review time-of-check/time-of-use gaps and cross-store ordering. Treat unavailable PostgreSQL evidence as awaiting validation, not a passed concurrency gate.

### R1-S1-Q — Sprint integration review

Status: done (2026-10-06; bounded sprint acceptance complete). Prerequisites: all tasks in R1-S1.
Evidence/acceptance contract: [R1-S1-Q](EVIDENCE-R1.md#r1-s1-q).

Run the [sprint closure gate](WORKFLOW.md#sprint-closure) against the acceptance journey above; record results in the existing sprint section.

## R1-S2 — Enforce current authorization

Sprint status: done (2026-10-09; [Q acceptance/limits](EVIDENCE-R1.md#r1-s2-q)).

Sprint acceptance journey: Materialize while consent is active; revoke/expire it; then search, match, export and train at an earlier as_of. Historical timestamps must not restore current access. Verify candidate and organization isolation.

### R1-S2-T1 — Apply current consent to serving

Status: done (2026-10-06; current serving authorization validated).
Audit mapping: F06. Prerequisites: R1-S1-Q.
Acceptance/evidence: [R1-S2-T1](EVIDENCE-R1.md#r1-s2-t1).

**Development:** Keep historical feature values separate from present authorization. Enforce current purpose/org-scoped consent at search and job matching boundaries.

**Acceptance:** Revoked/expired grants mask or exclude gated values from scores, returned contributions and filters. Ungated values remain usable. A historical as_of cannot bypass current consent.

**Tests and journey:** Extend tests/test_talent_search_api.py, tests/test_job_store_match.py and tests/test_features_materialize.py. Active → materialize → revoke → search/match tests with two candidates/orgs; valid and expired grants.

**Review focus:** Review direct store callers, per-org scope and ranking explanations, not only response field removal.

### R1-S2-T2 — Apply current consent to exports and training

Status: done (2026-10-08; current export/training authorization validated).
Audit mapping: F06. Prerequisites: R1-S2-T1.
Acceptance/evidence: [R1-S2-T2](EVIDENCE-R1.md#r1-s2-t2).

**Development:** Reuse the explicit authorization policy for CSV/Parquet export and training-label/outcome joins; define invalidation/re-materialization behavior.

**Acceptance:** Cached consent.allowed cannot authorize a revoked use. No gated data survives through labels or optional export formats. Historical snapshot semantics remain testable.

**Tests and journey:** Extend tests/test_features_export.py, tests/test_features_build_training_set.py and tests/test_features_training_export.py. API → materialize → revoke → export/train smoke, including optional-format behavior and missing grants.

**Review focus:** Inspect streaming/iterator timing, purpose differences and alternate direct-call entry points; avoid one copied consent rule per consumer.

### R1-S2-T3 — Close contact-verification attempt races

Status: done (2026-10-08). Audit mapping: F09; F04 residual. Prerequisites: R1-S2-T2.
Acceptance/evidence: [R1-S2-T3](EVIDENCE-R1.md#r1-s2-t3).

**Development:** Make VerificationStore challenge attempts and consumption atomic without changing the already-fixed login OTP contract.

**Acceptance:** Concurrent failures do not lose increments; exhausted/expired/superseded challenges cannot succeed. Exactly defined repeated-success semantics; no fake phone delivery.

**Tests and journey:** Extend tests/test_verification_store.py, tests/test_verification_service.py and tests/test_verification_api.py. Controlled competing transactions on PostgreSQL plus offline service regressions.

**Review focus:** Review exact challenge identity, lock/update predicates and transaction isolation. SQLite sequential tests alone cannot close this concurrency task.

### R1-S2-T4 — Separate asserted contacts from identity changes

Status: done (2026-10-08; bounded development acceptance); T4A/T4B done. Audit mapping: F01 residual. Prerequisites: R1-S2-T3.
Scope/status: [R1-S2-T4](EVIDENCE-R1.md#r1-s2-t4); completed evidence: [T4A](EVIDENCE-R1.md#r1-s2-t4a), [T4B](EVIDENCE-R1.md#r1-s2-t4b). Integrated sprint gate: [Q](EVIDENCE-R1.md#r1-s2-q), done.

**Development:** Document and enforce proof required to bind/change login identity or merge profiles. Inspect current email/phone hints without automatically repairing existing records.

**Acceptance:** An upload cannot change a verified principal's ownership. Legitimate verified changes have a defined path or explicit refusal. Existing F01 cases remain green; persisted anomalies are inventoried only.

**Tests and journey:** Extend tests/test_candidate_store.py, tests/test_portal_identity.py and tests/test_auth_service.py. Two principals, conflicting contacts, verified change and unverified upload attempts through public APIs.

**Review focus:** Review account-claim assumptions and tenant disclosure. Split schema migration from workflow into a child task if both cannot fit one session.

### R1-S2-Q — Sprint integration review

Status: done (2026-10-09; bounded sprint acceptance). Prerequisites: all tasks in R1-S2.
Acceptance/evidence: [R1-S2-Q](EVIDENCE-R1.md#r1-s2-q).

Run the [sprint closure gate](WORKFLOW.md#sprint-closure) against the acceptance journey above; record results in the existing sprint section.
