# PI-R4 — Simpler services and reliable execution

Status: in progress. Reduce unnecessary machinery while proving ownership, concurrency, resource lifecycle and operating behavior remain correct.

2026-09-26 targeted review reconfirmed repeated engine/store construction (T1),
unused vector-store startup after scoped provenance replaced retrieval (T2),
large live route/frontend modules (T3/T4) and tracked runtime DB (R4-S3-T3).
See the [audit follow-up](../CODEBASE_REVIEW_2026-09-07.md#follow-up-2026-09-26--repository-clutter-review).
These are source findings, not completed runtime fixes or measured speedups.

R4-M2 maintenance (2026-10-19): obsolete-file retirement done; the follow-up
publication includes the previously completed remediation and R4-M1 consolidation.
Final regression/journey/review gates passed. Local ignored-artifact removal
remains blocked; feature task statuses and next T3E are unchanged.
[Contract/evidence](../CODEBASE_REVIEW_2026-09-07.md#follow-up-2026-10-19--retire-obsolete-repository-material).

R4-M1 maintenance (2026-10-18): test/delivery consolidation done;
[contract and evidence](../CODEBASE_REVIEW_2026-09-07.md#follow-up-2026-10-18--test-and-delivery-consolidation).
R4-S1-T3E remains next; no feature task starts during this cleanup.

Load only the current task section plus [WORKFLOW.md](WORKFLOW.md), not this entire PI by default.
Source entry points (paths relative to repository root): src/app/services/; src/app/core/; src/app/api/; src/app/screening/; src/app/candidates/; src/app/curation/; src/app/metrics/; frontend/; .github/workflows/ci.yml
Task test lists are starting points verified during planning; select/add regression cases from actual callers at implementation time.
Every task inherits [WORKFLOW.md](WORKFLOW.md). Reuse inline active task sections; completed records use PI evidence anchors.

## R4-S1 — Simplify construction and boundaries

Status: done (2026-10-23); [Q integration evidence](EVIDENCE-R4.md#r4-s1-q).

Sprint acceptance journey: Boot the production service composition against a migrated scratch database, run evaluation/search/portal flows, shut down and restart. Shared resources have a single lifecycle and routes preserve contracts.

### R4-S1-T1 — Share database and service resources

Status: done (2026-10-16). Audit mapping: F12; bounded closure at [R4-S1-Q](EVIDENCE-R4.md#r4-s1-q). Prerequisites: R3-S3-Q.

Split before implementation: [T1 parent](EVIDENCE-R4.md#r4-s1-t1).
[T1A](EVIDENCE-R4.md#r4-s1-t1a) and [T1B](EVIDENCE-R4.md#r4-s1-t1b) are done for shared SQL
topology/engine ownership and lazy owned-provider cleanup. Their PI evidence sections
own final evidence. T2 removes the unused Chroma construction path; no blanket
leak-free or live-provider claim. Q completes the bounded F12 integration gate.

**Development:** Construct one engine/session factory per configured database and reuse service instances. Dispose resources on shutdown; preserve distinct database URLs when intentional.

**Acceptance:** Production builders and test containers use equivalent topology; repeated startup/shutdown does not leak engines or clients. No nested builder recreates shared stores.

**Tests and journey:** Extend tests/test_services_features.py plus startup/service-wiring tests. Spy resource construction/disposal; actual uvicorn smoke on scratch DB.

**Review focus:** Review injected factories, ownership of cleanup and hidden global settings; avoid a new dependency-injection framework.

### R4-S1-T2 — Remove unused provenance infrastructure

Status: done (2026-10-16). Audit mapping: F13; F02 cleanup. Prerequisites: R4-S1-T1.

[T2 contract/evidence](EVIDENCE-R4.md#r4-s1-t2): unused vector service, hashing path
and Chroma dependency removed; retired settings are accepted and ignored.
Final focused/full pytest, migrated HTTP/restart, packaging, static checks,
self-review and preservation passed. Graph retained with a bounded rationale;
Q completes the bounded F13 integration gate. PI-R4 remains open for S2/S3.

**Development:** Search callers before removing unused vector-store startup/config/dependencies; migrate supported settings with clear compatibility behavior. Evaluate linear graph simplification only if it has no required capability.

**Acceptance:** Core evaluation runs without Chroma initialization when no feature needs it; no unused embedding path remains solely for old provenance. Retained graph choice has a short rationale.

**Tests and journey:** Production-boot/evaluation smoke, config compatibility tests and dependency/import checks; existing domain and pipeline contracts stay green.

**Review focus:** Show removed call paths and measured startup/resource effect. Do not rewrite orchestration merely to reduce file count.

### R4-S1-T3 — Split routes by product area

Status: done (2026-10-22). Audit mapping: F13. Prerequisites: R4-S1-T2.

[T3 parent](EVIDENCE-R4.md#r4-s1-t3) links all A-M contracts/evidence.
[T3M](EVIDENCE-R4.md#r4-s1-t3m) completes the four remaining operations,
three DTOs and final ordered composition. The full 102-operation API/auth
contract remains unchanged; aggregate `routes.py` contains only assembly.
Focused/full pytest, migrated HTTP/graceful restart, actual Chrome,
static/preservation and implementation self-review pass. M owns the distinct
final completion review/publication record. T4 and the separate Q integration
gate are now also done; Q closes the bounded F13/sprint scope.

**Development:** Extract one cohesive router per subtask while retaining central authentication, response contracts and OpenAPI behavior. Record child contracts/evidence inline in T3; reuse its consolidated route tests.

**Acceptance:** Every moved route retains method/path, status codes, auth plane and CSRF enforcement. No accidental unguarded registration.

**Tests and journey:** Route contract and auth pytest plus affected API smoke; compare OpenAPI and ownership denial behavior before/after.

**Review focus:** Review dependency execution order and circular imports; label child subtasks and keep parent pending until all selected routers are moved.

### R4-S1-T4 — Extract frontend components and remove dead handlers

Status: done (2026-10-23). Audit mapping: F13. Prerequisites: R4-S1-T3.

[T4 parent](EVIDENCE-R4.md#r4-s1-t4) links the completed A-I contracts/evidence.
[T4I](EVIDENCE-R4.md#r4-s1-t4i) finishes shared display composition and retires
only proven dead sample/default/helper paths. A-H own the eight plain-script
screen modules; actual state/loading/lifecycle/navigation/file-reader/row-cache
callers and useful shared formatters/styles remain in the HTML intentionally.
Before/after behavior and live-value comparisons, focused/full pytest, actual
multi-plane/employer/interview Chrome, migrated HTTP/graceful restart, static/
packaging/preservation and implementation self-review pass. I owns the separate
final completion review/publication. Q now completes the combined integration
gate, closing the bounded F13/sprint scope. PI-R4 remains open for S2/S3.

**Development:** Extract one cohesive screen/module per child task and remove only proven unused code. Keep runtime compatibility and working user journeys.

**Acceptance:** Bindings resolve and browser actions persist real data after extraction. No duplicate mock/live sources remain for completed screens.

**Tests and journey:** Binding/JS checks plus browser regression of each affected screen and auth navigation; preserve console-error checks.

**Review focus:** Review event binding, stale state, unnecessary abstraction and documented versus actual dependencies.

### R4-S1-Q — Sprint integration review

Status: done (2026-10-23). Prerequisites: all tasks in R4-S1, done.

[Q contract/evidence](EVIDENCE-R4.md#r4-s1-q) owns the combined production
composition, SQLite/PostgreSQL graceful restart, full/focused pytest, actual
Chrome across eight extracted areas, static/preservation and separate reviews.
The existing smoke exposes repeatable `--integration` checks; no product fix was
required. The full API/auth fixture and advisory/ownership/consent/erasure
contracts remain. This closes R4-S1 and bounded F12/F13, not PI-R4 or measured
quality/live-provider validation. Exact next: R4-S2-T1, not started. Stop after Q.

## R4-S2 — Concurrency and bounded work

Sprint acceptance journey: Two workers process competing uploads and batches with slow/failing providers. Counts reflect committed results, stale leases cannot overwrite, and an unrelated request remains responsive.

### R4-S2-T1 — Make batch leases and counts truthful

Status: in progress (2026-10-23). Audit mapping: F14. Prerequisites: R4-S1-Q, done.

**Development:** Claim work just in time or renew leases; honor complete/fail return values and idempotent persistence.

**Acceptance:** Expired/stolen lease results cannot count as committed successes or overwrite newer results. Retries are bounded and cancellation is defined.

**Tests and journey:** Extend tests/test_screening_store.py, tests/test_screening_service.py and tests/test_screening_batches_api.py. Controlled slow fake provider with two workers; HTTP process/retry count assertions.

**Review focus:** Review duplicate provider calls versus duplicate persisted results separately; define remaining cost risk.

Split before implementation into bounded sections. A, B1 and B2a are done;
B2b is next. The parent, sprint and F14 stay open until all mapped work/gates
are complete.

#### R4-S2-T1A - Claim work when it starts and acknowledge failure writes

Status: done (2026-10-23). [A contract/evidence](EVIDENCE-R4.md#r4-s2-t1a)
owns the pre-implementation scope, red/green regressions, focused/full pytest,
SQLite/PostgreSQL two-process HTTP/graceful restart, actual screening Chrome,
static/preservation and separate reviews. Work is claimed immediately before
ingest; ingest/error failures require an acknowledged write; rejected terminal
writes stop this call. Task cancellation leaves only active work leased.
Only A closes here. B retains terminal completion outcomes, active expiry and
persistence/idempotence; no exactly-once provider or parent/F14 closure claim.

#### <a id="r4-s2-t1b"></a>R4-S2-T1B - Fence terminal outcomes and define expiry/idempotence

Status: in progress (2026-10-23). Prerequisite: A, done.

Complete the parent contract: distinguish committed completion/erasure failure
from a refused/stolen lease, define expiry eligibility at input/report/terminal
persistence boundaries, preserve retry/erasure behavior and document duplicate
provider work separately from committed results. Add red regressions for those
boundaries and real competing PostgreSQL/HTTP checks; refine its bounded contract
from A evidence before implementing. No B implementation in A's session.

Split before implementation on 2026-10-23: the acknowledgment defect can be
fixed without changing the input/report transaction protocol. Expiry and
idempotent report persistence need that separate protocol review. B1 is done;
B2 retains the remaining contract. B, T1, F14, sprint and PI remain open.

##### R4-S2-T1B1 - Distinguish acknowledged terminal outcomes

Status: done (2026-10-24). Prerequisite: A, done.
[B1 contract/evidence](EVIDENCE-R4.md#r4-s2-t1b1) owns the pre-implementation
scope, red/green regressions, validation, review findings and publication.
Completion distinguishes newly committed done/erasure-failed transitions from
refused writes; only acknowledged transitions count for this process call.
Refusal and committed erasure cleanup stop the call. Scrubbing/retry, lock order,
API/advisory/tenant/CSRF contracts remain. Only B1 closes; matching expired leases
and partial/duplicate input/report persistence remain B2. No parent/F14 closure
or exactly-once provider/report claim.

##### R4-S2-T1B2 - Fence expiry and make batch persistence idempotent

Status: in progress (2026-10-24). Prerequisite: B1, done.

Define and enforce expiry eligibility at input, report and terminal persistence
boundaries (including lock waits/rollback), and prevent an already-saved report
from creating duplicate persisted results on recovery. Refine the atomicity/
retry contract before implementation; preserve erasure lock ordering, private
input lifetime and current consent. Distinguish duplicate provider cost from
committed results. Own the remaining B/parent acceptance and PostgreSQL/HTTP
gates; B1's green tests do not close these requirements.

Split before implementation on 2026-10-24: terminal admission can be fenced
without changing the earlier ingest/report commit protocol. Input/report
fencing and report reuse require a separate persistence/erasure review. B2a is
done; B2b is next. B2/B/T1/F14/sprint/PI stay open.

###### R4-S2-T1B2a - Fence terminal transitions at lease expiry

Status: done (2026-10-24). Prerequisite: B1, done.
[B2a contract/evidence](EVIDENCE-R4.md#r4-s2-t1b2a) owns the pre-implementation
scope, red/green regressions, SQL/HTTP/browser/full validation and reviews.
Terminal done/fail and erasure cleanup check a fresh clock after locking and
after writes, before commit; expiry rolls back and counts neither outcome.
Timeout equality remains eligible. The last check admits a commit under the
held lock, not a physical commit/delivery deadline. Input/report fencing and
report reuse remain B2b; B2/B/T1/F14/sprint/PI stay open.

###### R4-S2-T1B2b - Fence input/report persistence and reuse saved reports

Status: pending. Prerequisite: B2a.

Refine input/report eligibility, lock-wait and commit atomicity/retry policy;
reuse a still-authorized saved report on recovery instead of creating duplicate
persisted results. Preserve erasure lock ordering, consent, private input and
its original TTL. Own B2's remaining parent acceptance and database/HTTP gates;
terminal-only fencing is not complete persistence idempotence.

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

Run the [sprint closure gate](WORKFLOW.md#sprint-closure) against the acceptance journey above; record results in the existing sprint section.

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

Run the [sprint closure gate](WORKFLOW.md#sprint-closure) against the acceptance journey above; record results in the existing sprint section.
