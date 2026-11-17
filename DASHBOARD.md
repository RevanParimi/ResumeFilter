# DASHBOARD.md — the requisition board (PI-5 / S5.3)

One org-plane read-model, `GET /jobs/{req_id}/board` → `RequisitionBoard`: the
shortlist for one role, comp-benchmarked. Given an org's `X-Org-Key` or org
session, it runs the existing S5.1 `run_match` (limit `dash_board_top_n`, 20)
and S5.2 `benchmark` and returns their outputs as-is. `src/app/dashboard/` is a
pure composition layer (`DashboardService.board`) that owns no tables and holds
no state. Peer of `MATCHING.md` and `COMP.md`.

- **404** for a requisition the org does not own, byte-identical to an unknown
  id. **200** with `match.reason == "no_materialized_candidates"` when nothing
  is materialized yet: an empty feature store is a server-side state the caller
  cannot fix.
- **No candidate PII and no depth `Report`.** Candidates appear by
  `candidate_id` with ranking contributions only; nothing in
  `src/app/dashboard/` reads `ReportStore`.
- **Audit is inherited, not new.** The reused `run_match` writes one
  `match.surface` row per returned candidate and the reused `benchmark` writes
  one `comp.aggregate` row; the board adds no audit action of its own.
- **DPDP.** No new candidate-linked state: an erased candidate drops from the
  vector pool and their `match.surface` rows CASCADE with them.

`dash_board_top_n` (20) is deliberately smaller than `match_default_limit`
(25): the board is a glance; `POST /jobs/{id}/match` returns the full ranked
list.
