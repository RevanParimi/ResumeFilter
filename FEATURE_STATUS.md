# Veritas feature status

Updated: 2026-11-16. The capabilities in the code today, with the guide that
describes each. All scoring is advisory and needs human review. Polished or
AI-assisted writing is not proof of fabricated experience, and interview
scoring judges answer content, not appearance or inferred emotion.

| Area | What exists | Guide |
|---|---|---|
| Resume evaluation | Domain-independent claim extraction, GitHub repository evidence, follow-up probes, timeline and duplicate-resume checks, risk band, writing-style observations and conservative advisory scoring with deterministic model fallbacks. Instant check (text or PDF) and saved reports with recorded outcomes. | [README](README.md), [FLOW](FLOW.md), [fabrication](FABRICATION.md), [logic](docs/FEATURE_LOGIC.md) |
| Candidate records | Extraction, contact-hash identity, versioned resumes, duplicate detection, extraction coverage and erasure. | [Candidates](CANDIDATES.md) |
| Screening | Batch upload, queue, processing, retry, summary, report view and outcomes, tenant-scoped. | [Screening](SCREENING.md), [tenancy](TENANCY.md) |
| Roles and matching | Roles (requisitions), role board, role match, dashboard overview and candidate card. | [Matching](MATCHING.md), [dashboard](DASHBOARD.md) |
| Compensation | Compensation estimate, role compensation band and observed offers. | [Comp](COMP.md) |
| Ledger and consent | Organisations, API keys, organisation reliability, purpose-scoped consent grants, audit log, interview and coding-round records and cross-company reputation. | [Ledger](LEDGER.md) |
| Features | Feature registry, materialisation, store, serving and ranking. | [Features](FEATURES.md) |
| Login and portal | Email-code login on every plane, sessions and signed-in devices, the candidate portal (my data, access log, consents, erasure) and the public grievance contact. | [Auth](AUTH.md), [portal](PORTAL.md) |
| Verification | Contact verification, assurance levels and manual review. | [Verification](VERIFICATION.md) |
| Interviews | Typed and voice answers, content scoring, the cheating check and consent-permitted employer summaries. | [Interviews](INTERVIEWS.md) |
| Operator | Organisations screen, operator accounts, retention sweep and metrics. | [Operating](OPERATING.md), [deploy](DEPLOY.md) |

Model choices are in [MODELS.md](MODELS.md); the original engine requirements
are in [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).
