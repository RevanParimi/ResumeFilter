# Veritas feature status

Updated: 2026-10-16. This is the common feature summary. For the exact next
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
| Login and candidate portal | Email-code authentication, sessions, candidate access/consent controls and erasure. | [Auth](AUTH.md), [portal](PORTAL.md). Login ordering, aggregate refusal and sprint erasure validation are complete; current consent and exact challenge validity passed [Q](docs/delivery/EVIDENCE-R1.md#r1-s2-q). |
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
accepted and ignored. Final validation is recorded in T2. F12/F13 remain open
for their remaining sprint tasks/gate. No blanket leak-free, live-provider or
general measured performance claim.

[R4-S1-T3](docs/delivery/EVIDENCE-R4.md#r4-s1-t3) is complete: API handlers
and DTOs live in product modules, with `routes.py` limited to ordered assembly.
The full API/auth contract, tenant/subject ownership, consent/erasure and
advisory responses are preserved. A-M own their validation evidence. Frontend
extraction T4 and sprint integration remain pending; F13/sprint/PI stay open.
