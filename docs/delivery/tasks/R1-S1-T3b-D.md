# R1-S1-T3b-D - Derived stores and ingest erasure races

Status: in progress (split 2026-09-21). Parent: [T3b](R1-S1-T3b.md).

| Child | Scope | Status |
|---|---|---|
| [D1](R1-S1-T3b-D1.md) | Feature-vector writes and materialization API accounting. | Done |
| [D2](R1-S1-T3b-D2.md) | Resolved ingest and post-ingest fingerprints. | Done |
| [D3](R1-S1-T3b-D3.md) | Screening input/completion, candidate-linked audits and cross-store ordering. | In progress |

Acceptance: refused writes cannot recreate erased data; surviving subjects,
idempotent duplicates and legitimate retries retain their behavior. Cover each
separate commit boundary with controlled regressions, including disclosures
computed from an earlier loaded pool. Do not change consent/identity policy.

D3 owns remaining ordering and combined validation. Parent stays open until
all children and evidence are complete. Follow child records for exact counts
and commands, and [PROGRESS.md](../../PROGRESS.md) for the next leaf task.
