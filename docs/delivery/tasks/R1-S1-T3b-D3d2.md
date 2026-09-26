# R1-S1-T3b-D3d2 - Cross-store cleanup ordering and combined validation

Status: in progress (split 2026-09-24). Parent: [D3d](R1-S1-T3b-D3d.md). Prerequisite: D3d1.

| Child | Scope | Status |
|---|---|---|
| [D3d2a](R1-S1-T3b-D3d2a.md) | Report-only erasure after save, before ingest/standalone response. | Done |
| [D3d2b](R1-S1-T3b-D3d2b.md) | Profile-source persistence refusal and exact-row response checks. | Done |
| [D3d2c](R1-S1-T3b-D3d2c.md) | Login-state cleanup and in-flight issuance/redemption. | In progress |
| D3d2d | Combined ordering and parent-coverage review; define its brief when c closes. | Pending |

Combined acceptance:
- Trace portal/admin erasure, report counts, challenge cleanup and candidate
  deletion. Separate shared transactions/cascades from independent commits.
- Cover both erasure doors, unrelated subjects/tenants, retries, failures and
  interruption on isolated stores. Preserve independent report lifetime after
  resume-only deletion, consent/identity policy and fresh-upload permission.
- Include source-list/portal aggregate response windows and shared curation
  raw-display-name retention/input policy. No identity FK does not establish
  de-identification, and final reads do not lock across HTTP delivery.
- Map the combined evidence back to D3d/D3/D/T3b/T3. Code changes require red/green
  regressions, focused/full pytest, relevant migrated HTTP/restart and diff review;
  SQL concurrency/transaction changes also require controlled PostgreSQL and
  applicable migration checks. Browser gates apply to visible UI changes.

Existing challenge cleanup is atomic (c1); reserved sends activate only if they
survive erasure (c2). Redemption consumes before principal/session establishment;
c3 must validate that boundary before c or this parent closes. Evidence counts live
with each child; exact next leaf: [PROGRESS.md](../../PROGRESS.md).
