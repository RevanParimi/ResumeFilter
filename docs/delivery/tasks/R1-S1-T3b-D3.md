# R1-S1-T3b-D3 - Screening, audits and cross-store ordering

Status: in progress (split 2026-09-22). Parent: [D](R1-S1-T3b-D.md).

| Child | Scope | Status |
|---|---|---|
| [D3a](R1-S1-T3b-D3a.md) | Screening completion refusal, retained-input cleanup and truthful counts. | Done |
| [D3b](R1-S1-T3b-D3b.md) | Earlier retained input, retry references and interrupted cleanup. | Done |
| [D3c](R1-S1-T3b-D3c.md) | Materialization/training/matching audit and disclosure boundaries. | Done |
| [D3d](R1-S1-T3b-D3d.md) | Ingest responses and cross-store ordering/combined validation. | In progress |

Acceptance: review each retained-data and disclosure boundary through its actual
caller. Preserve consent/scoring policy and anonymous completed-screening counts.
Older unresolved input pauses on erasure under D3b's authorized policy while
retaining its original TTL; this is not immediate erasure of unidentified text.

D3d retains login issuance/redemption and combined response/curation review.
Per-store completion does not prove atomic whole-ingest or HTTP delivery behavior.
Parent remains open until all children and required evidence are complete.
Counts/commands live with each leaf; next task: [PROGRESS.md](../../PROGRESS.md).
