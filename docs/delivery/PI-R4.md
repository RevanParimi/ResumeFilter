# PI-R4 — Simpler services and reliable execution

Status: planned. Reduce unnecessary machinery while proving ownership, concurrency, resource lifecycle and operating behavior remain correct.

Load only the current task section plus [WORKFLOW.md](WORKFLOW.md), not this entire PI by default.
Source entry points (paths relative to repository root): src/app/services/; src/app/core/; src/app/api/; src/app/screening/; src/app/candidates/; src/app/curation/; src/app/metrics/; frontend/; .github/workflows/ci.yml
Task test lists are starting points verified during planning; select/add regression cases from actual callers at implementation time.
Every task inherits the workflow's full pytest, review and relevant journey gates. Task evidence lives in `tasks/<task-id>.md`.

## R4-S1 — Simplify construction and boundaries

Sprint acceptance journey: Boot the production service composition against a migrated scratch database, run evaluation/search/portal flows, shut down and restart. Shared resources have a single lifecycle and routes preserve contracts.

### R4-S1-T1 — Share database and service resources

Status: pending. Audit mapping: F12. Prerequisites: R3-S3-Q.

**Development:** Construct one engine/session factory per configured database and reuse service instances. Dispose resources on shutdown; preserve distinct database URLs when intentional.

**Acceptance:** Production builders and test containers use equivalent topology; repeated startup/shutdown does not leak engines or clients. No nested builder recreates shared stores.

**Tests and journey:** Extend tests/test_services_features.py plus startup/service-wiring tests. Spy resource construction/disposal; actual uvicorn smoke on scratch DB.

**Review focus:** Review injected factories, ownership of cleanup and hidden global settings; avoid a new dependency-injection framework.

### R4-S1-T2 — Remove unused provenance infrastructure

Status: pending. Audit mapping: F13; F02 cleanup. Prerequisites: R4-S1-T1.

**Development:** Search callers before removing unused vector-store startup/config/dependencies; migrate supported settings with clear compatibility behavior. Evaluate linear graph simplification only if it has no required capability.

**Acceptance:** Core evaluation runs without Chroma initialization when no feature needs it; no unused embedding path remains solely for old provenance. Retained graph choice has a short rationale.

**Tests and journey:** Production-boot/evaluation smoke, config compatibility tests and dependency/import checks; existing domain and pipeline contracts stay green.

**Review focus:** Show removed call paths and measured startup/resource effect. Do not rewrite orchestration merely to reduce file count.

### R4-S1-T3 — Split routes by product area

Status: pending. Audit mapping: F13. Prerequisites: R4-S1-T2.

**Development:** Extract one cohesive router per subtask while retaining central authentication, response contracts and OpenAPI behavior. Partition further before starting if one router exceeds a session.

**Acceptance:** Every moved route retains method/path, status codes, auth plane and CSRF enforcement. No accidental unguarded registration.

**Tests and journey:** Route contract and auth pytest plus affected API smoke; compare OpenAPI and ownership denial behavior before/after.

**Review focus:** Review dependency execution order and circular imports; label child subtasks and keep parent pending until all selected routers are moved.

### R4-S1-T4 — Extract frontend components and remove dead handlers

Status: pending. Audit mapping: F13. Prerequisites: R4-S1-T3.

**Development:** Extract one cohesive screen/module per child task and remove only proven unused code. Keep runtime compatibility and working user journeys.

**Acceptance:** Bindings resolve and browser actions persist real data after extraction. No duplicate mock/live sources remain for completed screens.

**Tests and journey:** Binding/JS checks plus browser regression of each affected screen and auth navigation; preserve console-error checks.

**Review focus:** Review event binding, stale state, unnecessary abstraction and documented versus actual dependencies.

### R4-S1-Q — Sprint integration review

Status: pending. Prerequisites: all tasks in R4-S1.

Run the sprint acceptance journey above through the actual app composition on a migrated scratch database. Use HTTP/subprocess checks for backend sprints and a real browser for UI sprints; fake external providers. Run full pytest and the required PostgreSQL/browser gates from the task records. Review the final combined diff for broken ownership, data lifecycle, fallback and compatibility boundaries. Record command results and unresolved findings in `tasks/R4-S1-Q.md`. Fix acceptance-blocking regressions within this closure task; unrelated improvements return to the backlog. Missing required evidence means awaiting validation, not done. Stop after this task and name the next sprint task.

## R4-S2 — Concurrency and bounded work

Sprint acceptance journey: Two workers process competing uploads and batches with slow/failing providers. Counts reflect committed results, stale leases cannot overwrite, and an unrelated request remains responsive.

### R4-S2-T1 — Make batch leases and counts truthful

Status: pending. Audit mapping: F14. Prerequisites: R4-S1-Q.

**Development:** Claim work just in time or renew leases; honor complete/fail return values and idempotent persistence.

**Acceptance:** Expired/stolen lease results cannot count as committed successes or overwrite newer results. Retries are bounded and cancellation is defined.

**Tests and journey:** Extend tests/test_screening_store.py, tests/test_screening_service.py and tests/test_screening_retry.py. Controlled slow fake provider with two workers; HTTP process/retry count assertions.

**Review focus:** Review duplicate provider calls versus duplicate persisted results separately; define remaining cost risk.

### R4-S2-T2 — Resolve candidate and resume ingest races

Status: pending. Audit mapping: F14. Prerequisites: R4-S2-T1.

**Development:** Handle lookup/create and resume-version allocation conflicts transactionally while respecting verified identity policy. Inspect existing duplicates before proposing constraints.

**Acceptance:** Concurrent identical uploads have defined deduplication; versions remain unique; valid concurrent uploads do not fail due to unhandled integrity errors.

**Tests and journey:** Extend tests/test_candidate_store.py and screening ingest tests. Competing PostgreSQL transactions and API uploads; migration tests on synthetic duplicate records if schema changes.

**Review focus:** Review uniqueness scope, retries and existing data. Never auto-merge real identities as a schema-cleanup shortcut.

### R4-S2-T3 — Bound requests and move blocking work off-loop

Status: pending. Audit mapping: F14. Prerequisites: R4-S2-T2.

**Development:** Add aggregate body limits before expensive parsing; move measured blocking SQL/SMTP/PDF boundaries to bounded workers without unsafe shared sessions.

**Acceptance:** Oversized batches refuse before full expensive processing; slow provider/PDF does not block an unrelated endpoint. Cancellation, timeout and worker saturation have defined behavior.

**Tests and journey:** HTTP size-bound tests and controlled blocking fakes; concurrent health/read request latency with a documented budget measured on the test host.

**Review focus:** Review sessions across threads, memory bounds and exception sanitization. Split individual boundaries into child tasks when needed.

### R4-S2-T4 — Provide durable batch continuation

Status: pending. Audit mapping: F14. Prerequisites: R4-S2-T3.

**Development:** Use the existing durable queue with a minimal managed worker so browser closure does not halt accepted work. Define restart, lease renewal and graceful shutdown.

**Acceptance:** Accepted batch progresses after browser closure and worker restart; two workers do not commit duplicate results; UI reads server progress.

**Tests and journey:** Subprocess worker + API smoke with fake providers and scratch DB; stop/restart during an item and observe recovery. PostgreSQL competing-worker coverage.

**Review focus:** Review product necessity and operational ownership; avoid a new broker unless measured requirements justify it.

### R4-S2-Q — Sprint integration review

Status: pending. Prerequisites: all tasks in R4-S2.

Run the sprint acceptance journey above through the actual app composition on a migrated scratch database. Use HTTP/subprocess checks for backend sprints and a real browser for UI sprints; fake external providers. Run full pytest and the required PostgreSQL/browser gates from the task records. Review the final combined diff for broken ownership, data lifecycle, fallback and compatibility boundaries. Record command results and unresolved findings in `tasks/R4-S2-Q.md`. Fix acceptance-blocking regressions within this closure task; unrelated improvements return to the backlog. Missing required evidence means awaiting validation, not done. Stop after this task and name the next sprint task.

## R4-S3 — Cross-worker state and reproducibility

Sprint acceptance journey: Run multiple app workers against one scratch database; curation changes become visible consistently, readiness detects storage failure, and a clean install runs the tests without workspace secrets.

### R4-S3-T1 — Synchronize curation and define metrics scope

Status: pending. Audit mapping: F15. Prerequisites: R4-S2-Q.

**Development:** Refresh/version taxonomy across workers; choose explicit per-worker or aggregated metrics semantics and expose provider latency/usage with bounded labels.

**Acceptance:** Editing on worker A changes normalization on B within a stated bound; metrics do not falsely represent one worker as the whole app.

**Tests and journey:** Extend tests/test_curation_overlay.py and tests/test_metrics.py; two-process refresh smoke and metric cardinality/privacy checks.

**Review focus:** Review cache invalidation, stale reads, label cardinality and persistence overhead.

### R4-S3-T2 — Add readiness and safe diagnostics

Status: pending. Audit mapping: F15. Prerequisites: R4-S3-T1.

**Development:** Keep liveness lightweight; implement storage-aware readiness and allowlisted provider/SMTP error logging.

**Acceptance:** Unreachable/unmigrated storage makes readiness fail; ordinary liveness has documented behavior. Errors contain no resume text, credentials or recipient addresses.

**Tests and journey:** Boot/health and logging tests with failing DB/provider fakes; real scratch-server readiness failure/recovery smoke.

**Review focus:** Review raw exception serialization and whether probes themselves consume expensive provider calls.

### R4-S3-T3 — Lock dependencies and remove runtime-data assumptions

Status: pending. Audit mapping: F15. Prerequisites: R4-S3-T2.

**Development:** Create a reproducible transitive lock/install path; align CI interpreter coverage with the chosen supported versions. Replace dependence on tracked working DB with fixtures without deleting user data.

**Acceptance:** A clean isolated install builds/migrates/tests; generated fixtures are deterministic; runtime DB is no longer required by tests/build. Browser test dependencies are documented.

**Tests and journey:** Install/build/migration CI checks; existing requirements/image tests and full pytest. Inspect git changes to ensure actual DB contents were not modified.

**Review focus:** Review lock provenance/platform support and safe untracking plan. Do not rewrite repository history or discard the existing local database.

### R4-S3-Q — Sprint integration review

Status: pending. Prerequisites: all tasks in R4-S3.

Run the sprint acceptance journey above through the actual app composition on a migrated scratch database. Use HTTP/subprocess checks for backend sprints and a real browser for UI sprints; fake external providers. Run full pytest and the required PostgreSQL/browser gates from the task records. Review the final combined diff for broken ownership, data lifecycle, fallback and compatibility boundaries. Record command results and unresolved findings in `tasks/R4-S3-Q.md`. Fix acceptance-blocking regressions within this closure task; unrelated improvements return to the backlog. Missing required evidence means awaiting validation, not done. Stop after this task and name the next sprint task.

