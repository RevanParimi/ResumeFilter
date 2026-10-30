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

Status: done (2026-10-24). Audit mapping: F14. Prerequisites: R4-S1-Q, done.

**Development:** Claim work just in time or renew leases; honor complete/fail return values and idempotent persistence.

**Acceptance:** Expired/stolen lease results cannot count as committed successes or overwrite newer results. Retries are bounded and cancellation is defined.

**Tests and journey:** Extend tests/test_screening_store.py, tests/test_screening_service.py and tests/test_screening_batches_api.py. Controlled slow fake provider with two workers; HTTP process/retry count assertions.

**Review focus:** Review duplicate provider calls versus duplicate persisted results separately; define remaining cost risk.

Split before implementation into A, B1, B2a, B2b1, B2b2a and B2b2b. All
implementation and required validation are complete;
[B2b2b evidence](EVIDENCE-R4.md#r4-s2-t1b2b2b)
owns the completed combined parent acceptance review and current validation.
B2b2/B2b/B2/B/T1 close; F14/sprint/PI retain their T2/T3/T4/Q work. Exact next
is R4-S2-T2; no next-task implementation is included here.

#### R4-S2-T1A - Claim work when it starts and acknowledge failure writes

Status: done (2026-10-23). [A contract/evidence](EVIDENCE-R4.md#r4-s2-t1a)
owns its bounded scope, regressions, validation and separate reviews. Work is
claimed immediately before ingest; ingest/error failures require an acknowledged
write; rejected terminal writes stop this call. Cancellation leaves only active
work leased. Later B children below complete terminal expiry and report recovery.

#### <a id="r4-s2-t1b"></a>R4-S2-T1B - Fence terminal outcomes and define expiry/idempotence

Status: done (2026-10-24). Prerequisite: A, done.

Distinguish committed completion/erasure failure from a refused/stolen lease;
define input/report/terminal expiry admission and authorized checkpoint recovery.
B1 and B2 were split before implementation to separate acknowledgment from the
persistence/erasure protocol. Child implementation and final gates are complete;
the combined parent review is in B2b2b evidence. Provider work before a committed
checkpoint remains separate from persisted report idempotence.

##### R4-S2-T1B1 - Distinguish acknowledged terminal outcomes

Status: done (2026-10-24). Prerequisite: A, done.
[B1 contract/evidence](EVIDENCE-R4.md#r4-s2-t1b1) owns its bounded scope,
red/green, validation and publication. Completion distinguishes newly committed
done/erasure-failed transitions from refused writes. Only acknowledged transitions
count; refusal/committed erasure cleanup stop this call. B2 completes expiry and
checkpoint recovery; advisory, tenant, CSRF and scrub/retry contracts remain.

##### R4-S2-T1B2 - Fence expiry and make batch persistence idempotent

Status: done (2026-10-24). Prerequisite: B1, done.

Fence input/report/terminal commit admission after lock waits and writes; prevent
an already-saved checkpoint from creating another persisted report on recovery.
B2a and B2b were split before implementation so terminal admission could close
separately from the input/report commit protocol. Both implementations and
required gates are complete; B2b2b evidence owns the combined B2/B/T1 closure review.
Earlier commits and provider cost before a checkpoint remain explicit.

###### R4-S2-T1B2a - Fence terminal transitions at lease expiry

Status: done (2026-10-24). Prerequisite: B1, done.
[B2a contract/evidence](EVIDENCE-R4.md#r4-s2-t1b2a) owns terminal done/fail
and erasure-cleanup checks after locking and writes, with rollback on expiry.
Equality remains eligible. These are commit-admission checks under locks, not a
physical commit/delivery deadline. B2b below completes input/report recovery.

###### R4-S2-T1B2b - Fence input/report persistence and reuse saved reports

Status: done (2026-10-24). Prerequisite: B2a, done.

Preserve input/report eligibility, erasure lock order, consent and original
private TTL; recover an authorized saved report. B2b1/B2b2 were split before
implementation to ship callback fencing separately from report reuse. Their
implementations and required gates are complete; B2b2b evidence owns parent
closure.

###### <a id="r4-s2-t1b2b1"></a>R4-S2-T1B2b1 - Fence input and report transaction admission

Status: done (2026-10-24). Prerequisite: B2a, done.
[B2b1 contract/evidence](EVIDENCE-R4.md#r4-s2-t1b2b1) owns callback eligibility,
red/green/full/SQL/HTTP/Chrome/static checks and separate self-reviews. Fresh
clocks after item locking/private-input operations fence each transaction;
refusal rolls back, preserves prior bindings/original TTL and stops with zero
counters when terminal expiry refuses. Earlier admitted commits remain separate.
B2b2 below completes saved-report reuse.

###### <a id="r4-s2-t1b2b2"></a>R4-S2-T1B2b2 - Reuse saved reports on authorized recovery

Status: done (2026-10-24). Prerequisite: B2b1, done.

Recover a still-authorized bound report without a duplicate persisted result,
preserving current tenant/consent/erasure/TTL boundaries and original flags.
Split before implementation into private original facts (B2b2a) and binding
protection with its recovery consumer (B2b2b), so retries kept working between
children. Implementation and required gates are complete; B2b2b evidence owns
combined parent closure, full/PG/HTTP checks, reviews and provider-cost limitations.

###### <a id="r4-s2-t1b2b2a"></a>R4-S2-T1B2b2a - Preserve original private ingest facts

Status: done (2026-10-24). Prerequisite: B2b1, done.
[B2b2a contract/evidence](EVIDENCE-R4.md#r4-s2-t1b2b2a) owns nullable version-1
original matching facts, first-ingest atomicity, private lifetime/TTL and
populated SQLite/PG 0030 migration roundtrips, regressions, validation and reviews.
Historical facts stay unknown and public responses exclude this metadata.
B2b2a itself left retries unchanged; B2b2b completes recovery/binding protection.
Working storage is untouched.

###### <a id="r4-s2-t1b2b2b"></a>R4-S2-T1B2b2b - Recover the authorized report checkpoint

Status: done (2026-10-24). Prerequisite: B2b2a, done.
[B2b2b contract/evidence](EVIDENCE-R4.md#r4-s2-t1b2b2b) owns the refined
pre-implementation scope, first-write binding, strict original-fact recovery,
authorization/erasure/TTL/expiry protocol, red/green regressions, validation and
parent T1 acceptance review. A saved report completes atomically without
extraction/evaluation or a new report. Invalid/unknown/swept/TTL-expired
checkpoints require a fresh upload; lease refusal rolls back/stops with zero
counters. Earlier commits/provider cost before a checkpoint remain explicit.
All required gates and the combined B2b2/B2b/B2/B/T1 acceptance review are
complete. No F14/sprint/PI closure or next-task work is included.

### R4-S2-T2 — Resolve candidate and resume ingest races

Status: done (2026-10-25). Audit mapping: F14. Prerequisites: R4-S2-T1, done.

**Development:** Handle lookup/create and resume-version allocation conflicts transactionally while respecting verified identity policy. Inspect existing duplicates before proposing constraints.

**Acceptance:** Concurrent identical uploads have defined deduplication; versions remain unique; valid concurrent uploads do not fail due to unhandled integrity errors.

**Tests and journey:** Extend tests/test_candidate_store.py and screening ingest tests. Competing PostgreSQL transactions and API uploads; migration tests on synthetic duplicate records if schema changes.

**Review focus:** Review uniqueness scope, retries and existing data. Never auto-merge real identities as a schema-cleanup shortcut.

[T2 contract/evidence](EVIDENCE-R4.md#r4-s2-t2) owns the pre-implementation scope,
safe unresolved-contact ordering/recheck, existing version-allocation proof,
synthetic duplicate inventory, regressions, full/focused/actual PostgreSQL and
two-process HTTP/restart validation, harness corrections and separate reviews.
Proof, tenant ownership, consent/erasure and distinct ambiguous submissions
remain. No migration or working-data merge/cleanup; provider/report work remains
separate. Exact next is R4-S2-T3; F14/sprint/PI remain open for T3/T4/Q.

### R4-S2-T3 — Bound requests and move blocking work off-loop

Status: in progress (2026-10-25). Audit mapping: F14. Prerequisites: R4-S2-T2, done.

**Development:** Add aggregate body limits before expensive parsing; move measured blocking SQL/SMTP/PDF boundaries to bounded workers without unsafe shared sessions.

**Acceptance:** Oversized batches refuse before full expensive processing; slow provider/PDF does not block an unrelated endpoint. Cancellation, timeout and worker saturation have defined behavior.

**Tests and journey:** HTTP size-bound tests and controlled blocking fakes; concurrent health/read request latency with a documented budget measured on the test host.

**Review focus:** Review sessions across threads, memory bounds and exception sanitization. Split individual boundaries into child tasks when needed.

Split before implementation into A/B/C below. A/B are complete;
T3/F14/sprint/PI remain open until all children and the parent acceptance review
are complete. Completed child evidence lives in the linked PI evidence record.

#### R4-S2-T3A - Bound aggregate HTTP request bodies before parsing

Status: done (2026-10-26). Prerequisite: T2, done.

[A contract/evidence](EVIDENCE-R4.md#r4-s2-t3a) owns the pre-implementation
scope, raw-byte budget before JSON/model/PDF work, red/green regressions,
full/focused/HTTP/restart/Chrome/static checks, harness corrections and separate
self-reviews. Known lengths refuse unread and streams count actual bytes;
equality, auth/tenant/CSRF, request IDs/CORS and existing item caps remain.
Refused batches create no partial registration. Disconnect/cancellation and
the per-request memory limitation are explicit. No schema/transaction or
working-store change. B/C execution and parent acceptance are tracked below.

#### <a id="r4-s2-t3b"></a>R4-S2-T3B - Bound PDF execution and keep it off the event loop

Status: done (2026-10-26), including reviewed publication/remote verification.
Prerequisite: A, done.

[B contract/evidence](EVIDENCE-R4.md#r4-s2-t3b) owns the pre-implementation
scope, bounded off-loop PDF/document execution, shared queue-free admission,
cancellation/timeout/shutdown, regressions, full/focused/migrated HTTP/restart/
Chrome/static checks, fixture corrections and separate self-reviews. Existing
per-parse limits, text precedence, safe refusals, ownership and atomic batch
registration remain; verification rechecks its gates after the awaited parse.
SQL sessions stay on the caller. This is per-service admission, not global RSS
or a whole-batch deadline; normal server shutdown first drains HTTP requests.
C and the parent acceptance review remain open; child status is tracked below.

#### <a id="r4-s2-t3c"></a>R4-S2-T3C - Bound remaining blocking SQL/SMTP boundaries

Status: in progress (2026-10-26). Prerequisite: B, done.

Measure remaining synchronous SQL/SMTP boundaries; move complete owning-session
operations to bounded workers without sharing sessions across threads. Define
saturation, timeout/cancellation, committed-write uncertainty and cleanup.
Require focused/full/API and actual PostgreSQL competing-connection evidence
where transaction/thread behavior changes; measure unrelated-request latency
with slow SQL/mail fakes. Complete the combined T3 acceptance review here only
after A/B/C evidence is complete. No live email delivery or deployment.

Split before implementation: C1/C2 are complete. C3, C, parent T3/F14/sprint/PI
remain open; follow the handoff for one bounded task per chat.

##### <a id="r4-s2-t3c1"></a>R4-S2-T3C1 - Bound signup/login code issuance

Status: done (2026-10-26). Prerequisite: B, done.

[C1 contract/evidence](EVIDENCE-R4.md#r4-s2-t3c1) owns the pre-implementation
contract, dedicated bounded owning-session execution for all five issuing
routes, uniform 202 caller timeout, retained admission during late work,
cancellation/cleanup, regressions and validation/review results. Organization
name checking moves with issuance. No live Session crosses threads; no schema
change. UI explains possible delivery delay and permits manual code entry.
Existing auth/erasure/local echo remain. This is a caller wait budget, not a
whole-operation deadline or durable mail queue. Contact and remaining SQL child
status is tracked below; verification/resolution and other SQL stay in C3.

##### <a id="r4-s2-t3c2"></a>R4-S2-T3C2 - Bound contact-verification mail operations

Status: done (2026-10-27). Prerequisite: C1, done and published.

[C2 contract/evidence](EVIDENCE-R4.md#r4-s2-t3c2) owns the pre-implementation
contract, complete owning-session contact start/resend execution, shared neutral
mechanics with separate code pools, safe admission/wait/cancel/cleanup, UI saved-
status/manual-code recovery, regressions and validation/review results. Existing
candidate/CSRF/destination/consent, cooldown/rollback/erasure and guarded local
echo remain. C1 keeps opaque 202 timeout; contact timeout reports uncertainty.
No schema change, thread kill or durable queue. SMTP transaction locks and earlier
auth/session touches remain explicit; remaining SQL and parent acceptance are C3.
Exact next after C2 is C3; do not start it in this session.

##### <a id="r4-s2-t3c3"></a>R4-S2-T3C3 - Bound remaining measured SQL and review combined T3 acceptance

Status: in progress. Prerequisite: C2, done. Inventory/measure remaining async SQL callers,
including auth verification/resolution, intake, screening and reporting. Define
bounded child groups here before implementation if needed. Require owning-session
operations, controlled SQL/PG concurrency, unrelated-request latency, failure/
cancellation/committed-write uncertainty and relevant browser journeys. Close C/
T3 only after every group and the combined A/B/C acceptance review pass.

The source inventory at `d319535` finds synchronous service/store work in all
protected router groups below. C1/C2 cover code issuance; request principal
dependencies and later SQL need separate coverage. Measure each actual boundary before
its implementation; this inventory does not claim every call has been profiled.
Large groups must be split here before implementation, rather than widened in
one session. Each child requires red behavioral regression, focused/full pytest,
migrated HTTP/restart, actual PG for SQL scheduling/concurrency and a recorded
implementation plus distinct final staged self-review. Browser checks cover the
affected user journey; fakes do not prove live delivery or assessment quality.

###### <a id="r4-s2-t3c3a"></a>R4-S2-T3C3A - Bound request principal resolution

Status: done (2026-10-27). This session's only implementation task.

[C3A contract/evidence](EVIDENCE-R4.md#r4-s2-t3c3a) owns the pre-implementation
inventory/contract, red regressions, complete request resolver worker operations,
separate admission/wait/cancel/drain, safe refusal/refresh UI, actual SQL/PG lock
and migrated HTTP/restart/Chrome/full regression evidence and two self-reviews.
Request state/CSRF and existing auth rules remain. Late last-seen writes may
commit; abandoned handlers never run or replay. No schema change or guarantee
against later revoke/erasure. C3B-F/Q and C3/C/T3/F14/sprint/PI remain open.

###### <a id="r4-s2-t3c3b"></a>R4-S2-T3C3B - Bound auth redemption and session-management SQL

Status: done (2026-10-29). Prerequisite: C3A, done. Measure and bound the three verify-code
handlers plus logout/list/revoke owning operations. Preserve OTP atomicity,
anti-enumeration, cookie issuance, CSRF, last-admin and subject isolation. Cover
late committed session/revocation uncertainty without replay or false cookie
success, concurrent redemption/revoke/erasure, HTTP/restart and browser recovery.

Split before implementation into B1/B2 because redemption's public cookie and
OTP uncertainty differs from authenticated session-management recovery. Both
children now pass their contracts: [B1 evidence](EVIDENCE-R4.md#r4-s2-t3c3b1) and
[B2 evidence](EVIDENCE-R4.md#r4-s2-t3c3b2). C3C-F/Q and C3/C/T3/F14/sprint/PI
remain open; this closes only the auth handler group.

**<a id="r4-s2-t3c3b1"></a>R4-S2-T3C3B1 - Bound code redemption**

Status: done (2026-10-29). This session's only implementation task.
[B1 contract/evidence](EVIDENCE-R4.md#r4-s2-t3c3b1) owns the pre-implementation
scope/split, measurements, regressions, owning-session workers on all three
verify routes, safe admission/wait/cancel/drain and caller-only cookies. Late
commits may consume a code and leave an unreachable session; UI explains manual
fresh-code recovery without replay. Actual SQL/PG races, migrated HTTP/restart,
Chrome, full regression and both self-reviews are recorded there. Existing
atomicity, policy and schema remain. B2 status is below; C3/T3 parents remain open.

**<a id="r4-s2-t3c3b2"></a>R4-S2-T3C3B2 - Bound session management**

Status: done (2026-10-29). Prerequisite: B1, published at `4227b9c`.
[B2 contract/evidence](EVIDENCE-R4.md#r4-s2-t3c3b2) owns pre-implementation scope,
red SQL/race/UI regressions, complete owning-session workers, safe uncertain
outcomes/cookie handling and retained admission/drain. Conditional revocations
have one SQL winner and atomic audit. UI reports unconfirmed logout, prevents
overlapping sign-in, and requires saved-device refresh before another uncertain
revoke. Focused/full/actual PG, migrated HTTP/restart, actual Chrome, initial
timing-gate failure and unchanged rerun, preservation and both self-reviews are
recorded there. No schema/migration/scoring/mail change. B closes with B1/B2;
C3C-F/Q and all combined T3 parents remain open. Exact next: C3C, separate session.

###### <a id="r4-s2-t3c3c"></a>R4-S2-T3C3C - Bound intake and profile-source SQL

Status: in progress (2026-10-29). Prerequisite: C3B, done. Measure candidate intake/resume persistence,
candidate reads/keys and profile-source pre/post-provider SQL in `candidates`,
`screening.ingest` and `profile_sources`; split before implementation if needed.
Preserve cross-process identity/resume dedupe, present consent, scoped access,
erasure and deterministic provider fallbacks. Prove concurrency/late-write
uncertainty and migrated two-actor intake/source HTTP/restart/browser journeys.

Source inventory at `950d641`: `api/candidates.py` has three synchronous read
handlers and key issuance, shared `_ingest_one` awaits providers but calls SQL
through `screening/ingest.py`, and source handlers/service mix SQL before/after
async GitHub work or LinkedIn parsing/curation. Admin candidate/resume erasure
adapters remain with shared candidate-rights work in C3E. Split before code:

**<a id="r4-s2-t3c3c1"></a>R4-S2-T3C3C1 - Bound operator candidate reads and keys**

Status: done (2026-10-29). This session's only implementation child.
[C1 contract/evidence](EVIDENCE-R4.md#r4-s2-t3c3c1) owns pre-implementation scope,
red SQL/erasure/concurrency regressions, complete owning-session candidate reads/
key workers, safe admission/wait/cancel/drain and final existence checks. Key
issuance/rotation serializes with erasure and preserves the profile clock; late
rotation can invalidate the old key without delivering its replacement. Recovery
is deliberate fresh issuance, never replay. Focused/full/actual PG, migrated
HTTP/restart, existing portal Chrome compatibility and both reviews are recorded.
No UI handler/schema/provider/scoring change. C2/C3/CQ, C3C and broader parents
remain open. Exact next is C3C2, separate session.

**<a id="r4-s2-t3c3c2"></a>R4-S2-T3C3C2 - Bound shared intake persistence**

Status: in progress. Prerequisite: C1. Measure and bound candidate/resume ingest,
fingerprint/comparison and pre/post-evaluation owning SQL in `screening/ingest`
and both intake adapters; define smaller children before implementation if needed.
Keep async extraction/evaluation on the caller and preserve cross-process dedupe,
versions, tenant/consent/erasure guards and deterministic fallbacks. Require
red/focused/full, real PG lock/race, migrated two-actor intake/restart, actual
intake Chrome/recovery and both reviews. Late writes require honest uncertainty
without replay; no working-store/schema change without its separate gate.

Inventory/split at `8c5b122`, before implementation: the shared async pipeline
calls (A) candidate/resume/extraction ingest with transactional batch callbacks,
(B) fingerprint save/comparison and (C) subject/report checks and report save
around awaited evaluation. Batch callers must not synchronously write a failed
status while an uncertain worker still owns the transaction. These boundaries
need separate acceptance; the first session implemented only A. B/C/Q own the
remaining boundaries and combined review.

**<a id="r4-s2-t3c3c2a"></a>R4-S2-T3C3C2A - Bound candidate/resume persistence**

Status: done (2026-10-29). This session implements only A.
[A contract/evidence](EVIDENCE-R4.md#r4-s2-t3c3c2a) owns the initial transaction
scope, SQL/UI red regressions, shared bounded workers, late commit/rollback and
batch checkpoint recovery. Safe refusal/uncertainty returns no partial IDs;
workers retain admission and never resume evaluation or replay. Existing
screening copy explains possible saving and deliberate recovery. Focused/full,
actual SQLite/PG locks/races, migrated HTTP/restart, actual Chrome and both
self-reviews are recorded there. No schema/store algorithm/provider change.
C2B/C/Q and C2/C3C/broader parents remain open. Exact next is C2B in a new session.

**<a id="r4-s2-t3c3c2b"></a>R4-S2-T3C3C2B - Bound fingerprint and comparison work**

Status: done (2026-10-30). Prerequisite: A, published at `813bde3`.
[B contract/evidence](EVIDENCE-R4.md#r4-s2-t3c3c2b) owns the pre-implementation
scope/acceptance, red regressions, whole-worker fingerprint/comparison operation,
separate shared admission and late-write/manual recovery semantics. Focused/full,
actual SQLite/PG locks/erasure, migrated HTTP/two-process restart, actual Chrome,
preservation and review evidence are recorded there. Async providers, advisory
semantics and tenant redaction remain. No schema/algorithm/provider change.
Only B closes; C2C/Q and all broader parents remain open. Exact next: C2C in a
new session. Distinct final staged self-review is recorded; scoped publication
follows.

**<a id="r4-s2-t3c3c2c"></a>R4-S2-T3C3C2C - Bound intake report and subject SQL**

Status: pending. Prerequisite: B. Bound pre/post-evaluation subject checks, report
save/checkpoint and final publication checks with safe uncertain-write behavior.
Preserve erasure/consent/tenant guards and provider ownership. Require red/focused/
full, actual PG races, migrated HTTP/restart, affected Chrome and both reviews.

**<a id="r4-s2-t3c3c2q"></a>R4-S2-T3C3C2Q - Review combined shared intake persistence**

Status: pending. Prerequisites: A-C. Inventory combined boundaries and budgets;
prove dedupe/versions, batch checkpoints, cancellation/late writes, tenant/erasure
and fallback through actual SQLite/PG, migrated HTTP/restart, intake Chrome and
full regression. Complete both reviews before closing C2; C3/CQ remain separate.

**<a id="r4-s2-t3c3c3"></a>R4-S2-T3C3C3 - Bound profile-source operations**

Status: pending. Prerequisite: C2. Measure candidate/handle checks, source
save/list/final guards and curation capture before/after async GitHub fetch;
include bounded LinkedIn parsing/SQL. Preserve advisory signals, present subject,
provenance/erasure, guarded best-effort curation and provider fallbacks. Keep
coroutines and live SQL sessions on their owners. Require red/focused/full,
real PG contention/erasure, migrated source/restart and relevant browser/contract
journeys plus both reviews. Define bounded children first if necessary.

**<a id="r4-s2-t3c3cq"></a>R4-S2-T3C3CQ - Review combined intake/source acceptance**

Status: pending. Prerequisites: C1-C3 and any children. Re-inventory these
boundaries and run combined real SQLite/PG, HTTP/restart, affected Chrome and full
regression gates. Review combined admission/uncertain writes/cleanup and preserve
dedupe, isolation, consent/erasure and fallbacks. Only then close C3C; C3D-F/Q
and all broader parents remain separate work. No live provider/quality claim.

###### <a id="r4-s2-t3c3d"></a>R4-S2-T3C3D - Bound evaluation, reporting and screening SQL

Status: pending. Prerequisite: C3C. Measure `reports`, `screening` and
graph/service SQL around async provider calls; define bounded operation children
before implementation. Preserve report publication/delivery/consent guards,
outcome scope, batch leases/terminal outcomes and retry semantics. Require actual
PG contention, late committed-result uncertainty and affected HTTP/browser/
restart workflows; do not move coroutine/provider execution into a SQL session.

###### <a id="r4-s2-t3c3e"></a>R4-S2-T3C3E - Bound candidate rights, verification and interview SQL

Status: pending. Prerequisite: C3D. Measure remaining `portal`, `verification`
and `interviews` SQL, plus admin candidate/resume erasure adapters; split into
owning-operation children first. Preserve
consent/access/erasure, challenge ordering/rollback, ownership and advisory
content-only scoring. Exercise actual lock/erasure interleavings, safe uncertain
writes, migrated HTTP/restart and relevant candidate/verification/interview Chrome.

###### <a id="r4-s2-t3c3f"></a>R4-S2-T3C3F - Bound employer and operator SQL

Status: pending. Prerequisite: C3E. Measure `employer`, `ledger`, `features`,
`operator` and `curation` synchronous SQL, including scope checks and retention;
define bounded children first. Preserve tenant/role/CSRF/last-admin rules,
cross-store erasure, curation provenance and compatibility. Prove controlled
SQL/PG responsiveness, late writes, migrated HTTP/restart and affected Chrome.

###### <a id="r4-s2-t3c3q"></a>R4-S2-T3C3Q - Review combined bounded-work acceptance

Status: pending. Prerequisites: C3A-F and all of their children. Recheck remaining
async call sites against measured coverage; account for any uncovered boundary
here before closing. Run combined T3 A/B/C admission/cancellation/drain, SQL/PG,
HTTP/restart/browser and full regression gates. Review aggregate per-service
budgets/limits and operating guidance. Close C3/C/T3 only after this evidence;
T4 and sprint/PI closure remain separate tasks.

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
