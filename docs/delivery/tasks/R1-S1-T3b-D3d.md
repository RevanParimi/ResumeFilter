# R1-S1-T3b-D3d - Cross-store ordering and response review

Status: in progress (split 2026-09-24). Parent: [D3](R1-S1-T3b-D3.md).

| Child | Scope | Status |
|---|---|---|
| [D3d1](R1-S1-T3b-D3d1.md) | Shared-ingest candidate/resume response checks on uploads/batches, including short input. | Done |
| [D3d2](R1-S1-T3b-D3d2.md) | Report/source responses, login-state ordering and combined validation. | In progress |

Acceptance: trace both erasure routes and each read/write/commit boundary.
Candidate-linked SQL rows cascade; existing challenge cleanup now shares the
candidate-delete transaction (D3d2c1). Issuance/redemption remain distinct open
boundaries. Keep interrupted cleanup separate from response-snapshot guarantees.

D3d2 owns source-list/portal aggregate windows and the shared curation raw-display-
name policy. No new retention or identity policy is implicit. Do not close this
parent or F05/R1-S1-Q from individual-store evidence. See child records for
validation and [PROGRESS.md](../../PROGRESS.md) for the next leaf.
