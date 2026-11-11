# Veritas feature status

Updated: 2026-10-29. This is the common feature summary. For the exact next
development task read [PROGRESS.md](docs/PROGRESS.md); for acceptance and evidence
follow the linked task records. Existing features can still have open remediation.

## Existing capabilities

| Area | Implemented behavior | Detail / remaining work |
|---|---|---|
| Resume evaluation | Domain-independent claim analysis, evidence, follow-up probes and conservative advisory scoring; deterministic model fallbacks. | [Engine](README.md), [logic](docs/FEATURE_LOGIC.md). [R2-S1-Q](docs/delivery/EVIDENCE-R2.md#r2-s1-q) closes the bounded input/provider/evidence gate. New factual-risk v2 excludes style; reports explain observations, uncertainty, missing coverage and historical v1. R2-S2/F08 combined acceptance complete at [Q](docs/delivery/EVIDENCE-R2.md#r2-s2-q); PI-R2 complete within scope, historical reports unchanged. [R3-S1-T1](docs/delivery/EVIDENCE-R3.md#r3-s1-t1) wires org/operator Instant check text/PDF, saved reports/reload, reviewer feedback and visible failure/retry states. [R3-S1-Q](docs/delivery/EVIDENCE-R3.md#r3-s1-q) closes combined acceptance and fixes feedback deadline/recovery and stale account callbacks. Bounded PI-R3 workflows are complete at [R3-S3-Q](docs/delivery/EVIDENCE-R3.md#r3-s3-q); broader browser regression remains R5-S2-T1. |
| Candidate records | Extraction, contact-hash identity resolution, versioned resumes, duplicate detection and erasure routes. | [Candidates](CANDIDATES.md). Concurrent erasure safeguards below; [T4](docs/delivery/EVIDENCE-R1.md#r1-s2-t4) validates proved mailbox ownership, protected upload hints and explicit identity-change refusal. [R1-S2-Q](docs/delivery/EVIDENCE-R1.md#r1-s2-q) closes the bounded current-system gate. |
| Consent and evaluation ledger | Interview/coding records, purpose-scoped consent and advisory reputation. | [Ledger](LEDGER.md). Current authorization across reads/exports is validated by [Q](docs/delivery/EVIDENCE-R1.md#r1-s2-q). |
| Features, training and matching | Feature registry/materialization, exports, talent search, job matching and employer dashboard. | [Features](FEATURES.md), [matching](MATCHING.md), [dashboard](DASHBOARD.md). Snapshot checks do not lock across delivery. |
| Profile intake and curation | GitHub/LinkedIn-export ingestion, advisory source signals and guarded human taxonomy review. | [Sources](PROFILE_SOURCES.md), [curation](CURATION.md). New raw terms use source ownership and expiry; the named working-database legacy inventory is empty. [R3-S2-T3](docs/delivery/EVIDENCE-R3.md#r3-s2-t3) closes required snapshot revisions, real map/create/ignore/reload, stale conflicts and safe browser recovery/privacy. [R3-S2-Q](docs/delivery/EVIDENCE-R3.md#r3-s2-q) closes combined operator acceptance; cross-worker overlay refresh remains R4. |
| Login and candidate portal | Email-code authentication, sessions, candidate access/consent controls and erasure. | [Auth](AUTH.md), [portal](PORTAL.md). Login ordering, aggregate refusal and sprint erasure validation are complete; current consent and exact challenge validity passed [Q](docs/delivery/EVIDENCE-R1.md#r1-s2-q). [C1](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c1) bounds signup/login issuance; [C2](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c2) bounds contact operations. Remaining SQL stays open. |
| Organization administration | Operator list/inspection, create, reliability update, confirmed key rotation/offboarding and one-time key display. | [R3-S2-T1](docs/delivery/EVIDENCE-R3.md#r3-s2-t1) owns current implementation/validation; list filtering/pagination is local over an unpaged API. Reliability is an operator multiplier, not measured accuracy. Combined acceptance passed [R3-S2-Q](docs/delivery/EVIDENCE-R3.md#r3-s2-q). |
| Operator accounts | Actual list/create/confirmed deletion with saved IDs, labels and enabled/disabled status; session revocation and self-lockout warning. | [R3-S2-T2](docs/delivery/EVIDENCE-R3.md#r3-s2-t2) owns completed implementation/validation. All accounts have one platform role; no role/membership/suspension controls or readable stored emails. Listing is unpaged; self/last-account deletion remains allowed by the existing API. Combined revocation/restart acceptance passed [R3-S2-Q](docs/delivery/EVIDENCE-R3.md#r3-s2-q). |
| Screening | Batch processing, leases, retry handling and retained-input controls. | [Screening](SCREENING.md). Completed erasure safeguards below; Bounded PI-R3 UI journeys passed; resource work remains PI-R4. |
| Verification and interviews | Contact/manual verification and interview assessment workflows. | [Verification](VERIFICATION.md), [interviews](INTERVIEWS.md). Contact races passed R1-S2; [R3-S1-T2](docs/delivery/EVIDENCE-R3.md#r3-s1-t2) wires configured email, honest delivery refusal/rollback and candidate controls with actual held/expired status. [R3-S1-Q](docs/delivery/EVIDENCE-R3.md#r3-s1-q) closes bounded F09/current contact acceptance. [R3-S3-T1](docs/delivery/EVIDENCE-R3.md#r3-s3-t1) adds bounded `s73.2` content scoring, evidence/version metadata, repetition/relevance guards and preserved historical values; mixed versions remain insufficient. [R3-S3-T2A](docs/delivery/EVIDENCE-R3.md#r3-s3-t2a) serializes lifecycle writes and commits the final answer/assessment/audit together. [R3-S3-T2B](docs/delivery/EVIDENCE-R3.md#r3-s3-t2b) wires actual candidate text lifecycle, reload/history, saved version/evidence explanations and guarded recovery; parent T2 is done. [R3-S3-T3](docs/delivery/EVIDENCE-R3.md#r3-s3-t3) completes explicit microphone capture/stop/discard/submit with typed fallback, cleanup and safe audio/provider refusals. Combined text/audio/restart and consent-permitted employer summaries passed [R3-S3-Q](docs/delivery/EVIDENCE-R3.md#r3-s3-q), closing bounded PI-R3. Video and measured quality remain PI-R5; phone delivery is unavailable. |

All scoring remains advisory and requires human review. Polished or AI-assisted
writing is not proof of fabricated experience. Interview scoring judges answer
content, not appearance or inferred emotion. Synthetic tests do not establish
representative assessment accuracy; see [delivery plan](docs/delivery/README.md).

## Completed erasure safeguards

| Completed work | Observable result | Evidence |
|---|---|---|
| New/legacy flywheel handling | Production avoids a duplicate unmanaged text stream; explicit-file legacy cleanup preserves user files by default. | [T1](docs/delivery/EVIDENCE-R1.md#r1-s1-t1), [T2](docs/delivery/EVIDENCE-R1.md#r1-s1-t2) |
| Reports and timestamps | Erased report/outcome writes fail safely; PostgreSQL feature timestamps bind as UTC. Historical timestamp repair remains a separate policy decision. | [T3a](docs/delivery/EVIDENCE-R1.md#r1-s1-t3a) |
| Interview and vector writes | Writes refuse observed candidate erasure and preserve surviving subjects. | [Interview](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-i), [vectors](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d1) |
| Ingest and fingerprints | Stale resolved-candidate/resume writes are refused; duplicate fingerprints remain idempotent. | [D2](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d2) |
| Screening input and retry | Erasure refusal scrubs input; retry references follow resume/report deletion; erasure pauses older unresolved input while preserving its TTL and allowing fresh uploads. | [Completion](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3a), [input](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3b) |
| Materialization/training/matching audits | Erased subjects are excluded at the checked boundaries without losing surviving subjects' audits/results. | [D3c](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3c) |
| Ingest/report/source responses | Observed candidate, resume, report or saved-source disappearance produces a defined refusal. | [Ingest](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d1), [reports](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2a), [sources](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2b) |
| Existing login-state cleanup | Existing challenge cleanup and candidate deletion commit or roll back together through portal/admin erasure; unrelated principals and fresh signup survive. | [D3d2c1](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2c1) |
| Login issuance | Erasure cancels pending send reservations; late delivery cannot restore a challenge. Send failures preserve previous valid codes, and fresh signup remains allowed. | [D3d2c2](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2c2) |
| Login redemption | Exact code consumption, principal and session/audit commit together against erasure; interrupted redemption rolls back and permits retry. | [D3d2c3](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2c3) |
| Source/portal aggregate reads | Observed candidate erasure before the final existence read yields a safe 404; later delivery remains a snapshot. | [D3d2d1](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2d1) |
| Curation input | Original terms over 128 code points or containing controls skip capture; capture failures log no submitted text. Owned runtime is active; named-database legacy inventory is empty. | [D2a](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2d2a) |
| Owned curation runtime | Source capture follows commit; raw observations cascade/expire, explicit approvals persist separately, and real operator review plus startup/daily purge are active. Other legacy stores require their own inventory/decision. | [D2b2b](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2d2b2b) |
| Legacy curation tooling | Read-only counts inventory and bounded explicit removal/approval, atomic conflict rollback and retry/restart validation. No cleanup was needed for the subsequently inventoried named working database. | [D2c](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2d2c) |
| Combined erasure validation | Migrated both-door rollback/interruption/restart, survivors across tenants, stale-work refusal, permitted fresh upload/signup and ancestor acceptance mapping. Synthetic application validation; actual named-database inventory is recorded separately below. | [D3d2d3](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2d3) |
| R1-S1 sprint gate | All candidate-FK SQL sinks and child content, paused evaluation, migrated SQLite/PostgreSQL restart, full regression and real Chrome screening/reviewer checks. Bounded current-system F05 gate complete. | [Q](docs/delivery/EVIDENCE-R1.md#r1-s1-q) |

## Open gates and validation

The [approved curation retention policy](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2d2)
and combined development acceptance are complete. The actual
[inventory/decision](docs/delivery/EVIDENCE-R1.md#r1-s1-t3b-d3d2d4) settles the named
working-database curation row-retention gap with an empty inventory and no cleanup.
T3 and its development ancestors are done. [R1-S1-Q](docs/delivery/EVIDENCE-R1.md#r1-s1-q)
closes R1-S1 and F05's current-system remediation gate within its recorded scope.
[R1-S2-Q](docs/delivery/EVIDENCE-R1.md#r1-s2-q) closes current authorization and identity
integration, including a stale login expiry/budget fix, migrated SQL restart
journeys and optional exports. PI-R1 is done within its bounded current-system
scope; future-media erasure/current authorization remains R5-S1-T4. The exact next task is maintained in
[PROGRESS.md](docs/PROGRESS.md). Backup/history and physical reclamation are outside
the inventory result. Individual safeguards do not establish atomic whole-request
erasure or revoke already-delivered snapshots.

Erasure sprint validation, exact counts, commands and limitations:
[Q evidence](docs/delivery/EVIDENCE-R1.md#r1-s1-q).

## Where records live

- [PROGRESS.md](docs/PROGRESS.md): next task and current handoff.
- [Delivery plan](docs/delivery/README.md): PI/sprint status and active task links.
- Completed evidence: [R1](docs/delivery/EVIDENCE-R1.md),
  [R2](docs/delivery/EVIDENCE-R2.md), [R3](docs/delivery/EVIDENCE-R3.md),
  [R4](docs/delivery/EVIDENCE-R4.md), under stable task anchors.
- [ROADMAP.md](docs/ROADMAP.md): historical session log; read only relevant entries.

Keep open task records in `tasks/`, with child contracts/evidence inline.
Read completed evidence only when the current task needs it; do not create
another file for a chat or test rerun.

Documentation/runtime-clutter findings from the 2026-09-26 review are recorded in
the [existing audit](docs/CODEBASE_REVIEW_2026-09-07.md#follow-up-2026-09-26--repository-clutter-review).
Superseded implementation plans and prototype UI records have been removed
from the working tree and remain recoverable from Git history. Runtime
simplification remains assigned to PI-R4.

[R4-S1-T1](docs/delivery/EVIDENCE-R4.md#r4-s1-t1) is complete: shared per-app SQL
resources, lazy owned GitHub/LLM/speech transports and async cleanup preserve
borrowed resources and existing workflows. Child records own final validation.
[R4-S1-T2](docs/delivery/EVIDENCE-R4.md#r4-s1-t2) removes unused Chroma/vector/hash
infrastructure; provenance remains evaluation-local and retired settings are
accepted and ignored. Final validation is recorded in T2. The bounded F12/F13
gate is complete at [R4-S1-Q](docs/delivery/EVIDENCE-R4.md#r4-s1-q).
No blanket leak-free, live-provider or
general measured performance claim.

[R4-S1-T3](docs/delivery/EVIDENCE-R4.md#r4-s1-t3) is complete: API handlers
and DTOs live in product modules, with `routes.py` limited to ordered assembly.
The full API/auth contract, tenant/subject ownership, consent/erasure and
advisory responses are preserved. A-M own their validation evidence.
[Frontend extraction T4](docs/delivery/EVIDENCE-R4.md#r4-s1-t4) is complete:
eight plain scripts own account, organization, curation, evaluation/report,
screening, portal/auth, interview and employer roles/compensation logic.
[T4I](docs/delivery/EVIDENCE-R4.md#r4-s1-t4i) simplifies shared display composition
and removes proven dead sample/default/helper paths, preserving live identities,
advisory/human review, saved operations and recovery. Useful shared lifecycle,
navigation, styles and formatters remain in the HTML. A-I own required evidence.
The separate [Q integration gate](docs/delivery/EVIDENCE-R4.md#r4-s1-q) is complete:
combined migrated production composition/restart, API/UI contracts, actual
multi-plane Chrome and SQL lifecycle/lock/migration gates pass. R4-S1 closes;
PI-R4 continues with concurrency/bounded work and cross-worker/reproducibility
tasks. Synthetic providers/media prove mechanics, not empirical quality.

[R4-S2-T1A](docs/delivery/EVIDENCE-R4.md#r4-s2-t1a) is complete: processing claims
each item when work starts, counts ingest/error failures only after an
acknowledged write and stops after a refused terminal write. Task cancellation
leaves only active work leased, recoverable through existing timeout/input rules.
[R4-S2-T1B1](docs/delivery/EVIDENCE-R4.md#r4-s2-t1b1) distinguishes committed
success/erasure failure from a refused completion; only newly acknowledged
transitions affect this call's counters.
[R4-S2-T1B2a](docs/delivery/EVIDENCE-R4.md#r4-s2-t1b2a) checks terminal eligibility
with a fresh clock after row/writer locking and after writes, including erasure
rollback. Expired terminal writes roll back without increasing counters;
exact timeout equality remains eligible. This is commit admission under the
held lock, not a physical delivery deadline.
[R4-S2-T1B2b1](docs/delivery/EVIDENCE-R4.md#r4-s2-t1b2b1) adds fresh clock checks
after lock waits and private-input operations to ingest/report-save callbacks;
refusal rolls back their whole transaction, preserves prior input/report
bindings and original input TTL, and stops without incrementing either counter.
Earlier admitted commits can survive later expiry/terminal refusal.
[R4-S2-T1B2b2a](docs/delivery/EVIDENCE-R4.md#r4-s2-t1b2b2a) preserves the first
ingest's three matching facts on its private retry reference, with the original
TTL. Historical facts remain unknown and public responses exclude this metadata.
[R4-S2-T1B2b2b](docs/delivery/EVIDENCE-R4.md#r4-s2-t1b2b2b) recovers the same
still-authorized report with those original facts, without extraction/evaluation
or another saved report. First-write binding rejects replacement/same-ID mutation;
invalid, unknown, swept or TTL-expired checkpoints require a fresh upload. Lease
refusal rolls back and stops without counters. No-report retries retain their
existing path; provider work before a checkpoint and historical duplicates remain
possible. Combined acceptance closes B2b2/B2b/B2/B/T1; F14/sprint/PI remain
open for their other tasks.
[R4-S2-T2](docs/delivery/EVIDENCE-R4.md#r4-s2-t2) orders unresolved contact lookups
with a transactional recheck, preserving mailbox proof and ambiguous-submission
policy. Competing safe matches share a candidate; caller-owned text deduplication
and candidate-wide versions remain serialized. Existing duplicates are preserved;
provider/report work is separate.
[R4-S2-T3A](docs/delivery/EVIDENCE-R4.md#r4-s2-t3a) adds the
[raw HTTP body budget](OPERATING.md#raw-http-body-budget) before JSON/model/PDF
work, including streamed bodies; request IDs/CORS and existing per-item limits
remain. Rejected batches create no partial registration.
[R4-S2-T3B](docs/delivery/EVIDENCE-R4.md#r4-s2-t3b) moves PDF/document parsing
off the event loop with shared per-service admission, safe 503 saturation,
retained capacity during cancellation cleanup and owned shutdown. Existing
per-parse limits remain; verification rechecks its gates after parsing. See the
[PDF budget](OPERATING.md#pdf-execution-budget) for scope and operational limits.
[R4-S2-T3C1](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c1) moves all five signup/login
code operations, including their owning SQL sessions and mail, to bounded
workers. Busy admission refuses safely; caller timeout keeps opaque acceptance
and capacity until actual completion. UI permits manual code entry and explains
possible delivery delay. The [auth budget](OPERATING.md#authentication-code-execution-budget)
states cancellation/shutdown and uncertain-write limits. C/parent T3/F14/sprint/
PI remain open for remaining measured SQL (C3) and combined acceptance.
[R4-S2-T3C2](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c2) moves complete contact
start/resend operations to a separate bounded pool with owning SQL sessions.
Busy admission refuses before verification work; caller wait returns an honest
uncertain outcome with saved-status/manual-code recovery and no automatic replay.
Both code pools share execution mechanics and join before owned SQL disposal.
SMTP's candidate transaction and other SQL remain;
the [contact budget](OPERATING.md#contact-code-execution-budget) states these
limits. Exact next is maintained in the handoff.
[R4-S2-T3C3A](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3a) bounds all four request
principal resolvers, including owning-session SQL and periodic last-seen writes,
with separate admission and safe 503 timeout/refusal before handler execution.
Late touches retain capacity; abandoned actions never replay. UI explains
unavailable session checks and manual refresh restores the original cookie.
The [resolution budget](OPERATING.md#request-principal-resolution-budget) states
defaults and limits.
[R4-S2-T3C3B1](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3b1) bounds complete code
redemption on all three planes with a separate pool and owning SQL sessions.
Busy/closed admission and uncertain waits return safe 503 without cookies;
late work retains capacity and never replays. UI explains possible code use and
deliberate fresh-code recovery. The [redemption budget](OPERATING.md#code-redemption-execution-budget)
states defaults and late-session limits.
[R4-S2-T3C3B2](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3b2) bounds logout, own-device
reads and revocation with separate owning-session admission and safe uncertain
responses. Revocations have one SQL winner and atomic audit. UI reports
unconfirmed logout, protects sign-in overlap and requires saved-device refresh
before another uncertain revoke. See the [session budget](OPERATING.md#session-management-execution-budget).
C3D-F/Q and broader parent acceptance remain open.
[R4-S2-T3C3C1](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3c1) bounds the operator
candidate detail/resume/report reads and access-key issuance in a separate pool.
Pending/refused work returns no partial data or undisclosed replacement key;
loaded results recheck observed candidate erasure. Key issuance/rotation locks
the candidate and preserves its profile clock. A late rotation can invalidate
the old key; recovery is deliberate fresh issuance. The
[record budget](OPERATING.md#operator-candidate-record-execution-budget) states
API-only scope and limits. C3D-F/Q and all broader parents remain
open; other handler/graph/store SQL stays synchronous. Exact task status and next
action are owned by the PI/handoff.

[R4-S2-T3C3C2A](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3c2a) moves the initial
candidate/resume/extraction transaction and batch checkpoint callbacks to a
separate bounded pool shared by admin/employer uploads and batch processing.
Pending writes return no partial IDs and never resume evaluation automatically;
batch uncertainty preserves the lease/checkpoint for deliberate recovery. The
existing screening error explains possible saving and refresh/manual restart. The
[intake budget](OPERATING.md#candidate-intake-persistence-budget) explains late
commits, manual recovery and identity/dedupe limits.
[R4-S2-T3C3C2B](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3c2b) extends the shared
budget to complete fingerprint computation/save/comparison and advisory assessment.
Late fingerprint completion never resumes evaluation; later admission refusal
can follow a committed resume.
[R4-S2-T3C3C2C](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3c2c) extends that same
budget to pre/post-evaluation subject SQL, complete report/checkpoint saves and
final publication guards, including uploads without evaluation. A late report
commit can be recovered deliberately by a batch without another evaluation.
Batch management and other handler/graph SQL remain separate work.
[R4-S2-T3C3C2Q](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3c2q) closes the combined
shared intake persistence gate with fresh SQLite/actual PostgreSQL, HTTP/restart,
two-process races, actual Chrome/manual recovery and full regression evidence.
No production change was needed; combined intake/source acceptance is recorded
below. Broader parents remain open.

[R4-S2-T3C3C3A](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3c3a) bounds the complete
operator source-list initial/history/final snapshot on the existing candidate-
record pool, preserving filtering, subject scope and observed-erasure refusal.
Busy/closed/pending reads return safe 503 without partial data; cancellation
retains admission and a deliberate fresh GET reads current saved history. There
is no dedicated source-list UI or new executor/config/schema.
[R4-S2-T3C3C3B](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3c3b) extends the same pool
to complete GitHub candidate/handle checks before its async fetch and complete
save/curation/final guards afterwards. Provider wait holds no SQL admission.
Timeout/cancel retains capacity and never replays; late post work may commit.
Read saved history before a deliberate fresh POST, which may fetch and append
another source. Existing separate commits, advisory fallbacks and guarded
best-effort curation remain.
[R4-S2-T3C3C3C](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3c3c) admits LinkedIn
candidate/transport/decode checks and complete parse/transform/save/curation/final
work separately on that same pool. Candidate-before-transport errors, archive/
row limits and advisory signals remain. Accepted service work may late-commit;
transport abandonment never later starts parsing. Saved-history recovery precedes
a deliberate fresh POST that can append another source. Actual SQLite/PG locks,
erasure and migrated HTTP/restart are covered; portal Chrome is compatibility
evidence because source ingestion is API-only.
[R4-S2-T3C3C3Q](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3c3q) closes combined source
acceptance and its bounded parent after source/budget self-review and fresh
SQLite/actual PG contention/erasure, all source/record HTTP/restart modes,
portal compatibility, curation Chrome/restart and full regression. No production
or test change was needed; separate commits, late-write/manual recovery and the
documented resource/snapshot limits remain.
[R4-S2-T3C3CQ](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3cq) closes combined intake/
source acceptance and bounded parent C3C after fresh full/SQLite/actual PG,
all seven HTTP/restart modes and two-process races on each DB, affected Chrome
and separate self-reviews. The original PG hook-wait timeout and unchanged
six-case rerun are retained in the evidence. No production/test change was
needed; separate record/intake pools, late commits, manual recovery and the
documented budgets/limits remain. C3D-F/Q and broader parents remain open.

[R4-S2-T3C3D1](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3d1) bounds the five
operator/employer report and outcome-history GET operations in a separate pool.
Busy/closed/pending reads return safe 503 without partial reports/notes; admission
persists through timeout/cancellation and saved-state recovery is a deliberate
GET. History checks refuse observed erasure or changed employer ownership before
publishing loaded notes. Read failures offer reload guidance while keeping the
saved reference. Tenant projection, private-note filtering, generic 404,
empty candidate-report lists and advisory/scorer semantics remain. The
[report read budget](OPERATING.md#report-read-execution-budget) states defaults
and snapshot/driver/drain limits. Standalone publication has its own budget
below; batch SQL remains D4-D6/Q. C3D and broader parents stay open.

[R4-S2-T3C3D2](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3d2) bounds both human-outcome
POSTs in a separate pool covering lookup, shared validation, SQL append and the
existing optional observer. Read admission remains independent. Timeout/cancel
retains capacity through actual completion, without automatic replay; a late
append or observer failure does not imply rollback. The UI preserves notes and
requires a successful fresh history read after uncertainty before allowing
another submission. That read is a snapshot and a fresh judgment is additive.
Tenant/author/user scope, private-note filtering, FK/erasure and advisory policy
remain. The [outcome budget](OPERATING.md#human-outcome-write-execution-budget)
owns defaults and limits; the evidence owns validation and task status.

[R4-S2-T3C3D3](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3d3) bounds standalone
evaluation report publication after async assessment, using a separate owning
save/final-read pool. Pending publication returns a report reference for GET
recovery without another assessment. The UI preserves input/reference and
requires deliberate fresh-evaluation intent before another POST; late saves
remain possible and fresh assessments may create another report. Operator scope,
erasure snapshots, advisory/domain/fallback and existing success DTOs remain.
The [publication budget](OPERATING.md#standalone-evaluation-publication-budget)
owns defaults/limits; batch SQL and broader acceptance remain D4-D6/Q work.

[R4-S2-T3C3D4A](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3d4a) bounds complete batch
detail/list/queue/summary reads on a separate owning-session pool. Final batch
visibility refuses observed scope loss without rewriting keyset cursors; values
remain snapshots. Human refusal guidance and visible GET recovery preserve the
selected reference/draft without starting screening. Account/refresh/page guards
reject late callbacks and paging waits for the current base read. The
[batch read budget](OPERATING.md#batch-view-read-execution-budget) owns defaults
and limits. Retry/delete, processing and combined acceptance remain
D4Q and D5-D6/Q; D4 and broader parents remain open.

[R4-S2-T3C3D4B](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3d4b) bounds complete
batch registration separately from PDF decoding and batch views. Uncertain
registration returns a server batch reference; the UI retains drafts and uses
explicit saved-state reads, with no automatic registration or processing replay.
Only confirmed initial success on the same account, screen and draft starts
screening. The [registration budget](OPERATING.md#batch-registration-execution-budget)
owns defaults, recovery behavior and limitations. Validation status belongs to
the linked task evidence; broader D4 work remains open.

[R4-S2-T3C3D4C](docs/delivery/EVIDENCE-R4.md#r4-s2-t3c3d4c) bounds complete
batch retry/delete operations on a separate owning-session pool and enforces
current tenant ownership at the write boundary. Retry only requeues eligible
failures; processing requires a separate human action. Uncertain changes retain
their batch reference and require GET-only recovery plus explicit intent before
another write or Start. The [mutation budget](OPERATING.md#batch-retry-and-deletion-execution-budget)
owns defaults and limits. Validation status belongs to the linked evidence;
D4Q and broader parents remain open.
