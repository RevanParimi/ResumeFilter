# Veritas feature status

Updated: 2026-09-27. This is the common feature summary. For the exact next
development task read [PROGRESS.md](docs/PROGRESS.md); for acceptance and evidence
follow the linked task records. Existing features can still have open remediation.

## Existing capabilities

| Area | Implemented behavior | Detail / remaining work |
|---|---|---|
| Resume evaluation | Domain-independent claim analysis, evidence, follow-up probes and conservative advisory scoring; deterministic model fallbacks. | [Engine](README.md), [logic](docs/FEATURE_LOGIC.md). Input/provider validation and separating writing style from factual risk remain PI-R2. |
| Candidate records | Extraction, contact-hash identity resolution, versioned resumes, duplicate detection and erasure routes. | [Candidates](CANDIDATES.md). Concurrent erasure safeguards below; verified identity changes remain R1-S2-T4. |
| Consent and evaluation ledger | Interview/coding records, purpose-scoped consent and advisory reputation. | [Ledger](LEDGER.md). Current authorization across reads/exports remains R1-S2. |
| Features, training and matching | Feature registry/materialization, exports, talent search, job matching and employer dashboard. | [Features](FEATURES.md), [matching](MATCHING.md), [dashboard](DASHBOARD.md). Snapshot checks do not lock across delivery. |
| Profile intake and curation | GitHub/LinkedIn-export ingestion, advisory source signals and human taxonomy review. | [Sources](PROFILE_SOURCES.md), [curation](CURATION.md). Shared raw display-name retention needs D3d2d review. |
| Login and candidate portal | Email-code authentication, sessions, candidate access/consent controls and erasure. | [Auth](AUTH.md), [portal](PORTAL.md). Redemption across erasure remains open. |
| Screening | Batch processing, leases, retry handling and retained-input controls. | [Screening](SCREENING.md). Completed erasure safeguards below; UI journeys and bounded work remain PI-R3/R4. |
| Verification and interviews | Contact/manual verification and interview assessment workflows. | [Verification](VERIFICATION.md), [interviews](INTERVIEWS.md). Attempt races, unfinished journeys and assessment quality remain PI-R1/R3/R5. |

All scoring remains advisory and requires human review. Polished or AI-assisted
writing is not proof of fabricated experience. Interview scoring judges answer
content, not appearance or inferred emotion. Synthetic tests do not establish
representative assessment accuracy; see [delivery plan](docs/delivery/README.md).

## Completed erasure safeguards

| Completed work | Observable result | Evidence |
|---|---|---|
| New/legacy flywheel handling | Production avoids a duplicate unmanaged text stream; explicit-file legacy cleanup preserves user files by default. | [T1](docs/delivery/tasks/R1-S1-T1.md), [T2](docs/delivery/tasks/R1-S1-T2.md) |
| Reports and timestamps | Erased report/outcome writes fail safely; PostgreSQL feature timestamps bind as UTC. Historical timestamp repair remains a separate policy decision. | [T3a](docs/delivery/tasks/R1-S1-T3a.md) |
| Interview and vector writes | Writes refuse observed candidate erasure and preserve surviving subjects. | [Interview](docs/delivery/tasks/R1-S1-T3b-I.md), [vectors](docs/delivery/tasks/R1-S1-T3b-D1.md) |
| Ingest and fingerprints | Stale resolved-candidate/resume writes are refused; duplicate fingerprints remain idempotent. | [D2](docs/delivery/tasks/R1-S1-T3b-D2.md) |
| Screening input and retry | Erasure refusal scrubs input; retry references follow resume/report deletion; erasure pauses older unresolved input while preserving its TTL and allowing fresh uploads. | [Completion](docs/delivery/tasks/R1-S1-T3b-D3a.md), [input](docs/delivery/tasks/R1-S1-T3b-D3b.md) |
| Materialization/training/matching audits | Erased subjects are excluded at the checked boundaries without losing surviving subjects' audits/results. | [D3c](docs/delivery/tasks/R1-S1-T3b-D3c.md) |
| Ingest/report/source responses | Observed candidate, resume, report or saved-source disappearance produces a defined refusal. | [Ingest](docs/delivery/tasks/R1-S1-T3b-D3d1.md), [reports](docs/delivery/tasks/R1-S1-T3b-D3d2a.md), [sources](docs/delivery/tasks/R1-S1-T3b-D3d2b.md) |
| Existing login-state cleanup | Existing challenge cleanup and candidate deletion commit or roll back together through portal/admin erasure; unrelated principals and fresh signup survive. | [D3d2c1](docs/delivery/tasks/R1-S1-T3b-D3d2c1.md) |
| Login issuance | Erasure cancels pending send reservations; late delivery cannot restore a challenge. Send failures preserve previous valid codes, and fresh signup remains allowed. | [D3d2c2](docs/delivery/tasks/R1-S1-T3b-D3d2c2.md) |

## Open gates and validation

Next: [D3d2c3 - redemption](docs/delivery/tasks/R1-S1-T3b-D3d2c3.md), then D3d2d
combined review, including source-list/portal aggregate windows and curation
retention. T3, F05 and sprint R1-S1 remain open. Individual safeguards do not
establish atomic whole-request erasure or revoke already-delivered snapshots.

Latest application validation, exact counts, commands and limitations:
[D3d2c2 evidence](docs/delivery/tasks/R1-S1-T3b-D3d2c2.md).

## Where records live

- [PROGRESS.md](docs/PROGRESS.md): next task and current handoff.
- [Delivery plan](docs/delivery/README.md): PI/sprint status and active task links.
- [Completed evidence archive](docs/delivery/archive/README.md): detailed children
  of closed task groups, retained for regressions and audit traceability.
- [ROADMAP.md](docs/ROADMAP.md): historical session log; read only relevant entries.

Keep active task records and completed children of open groups in `tasks/`.
When a group closes, archive its detailed child records and retain the group
summary. Read archived evidence only when the current task needs it.

Documentation/runtime-clutter findings from the 2026-09-26 review are recorded in
the [existing audit](docs/CODEBASE_REVIEW_2026-09-07.md#follow-up-2026-09-26--repository-clutter-review).
Old `docs/superpowers/` plans and UI design records are historical, not a second
active backlog. Runtime simplification remains assigned to PI-R4.
