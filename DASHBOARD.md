# DASHBOARD.md — employer dashboard: read-models over the org plane (PI-5 / S5.3)

Employer-ready JSON read-models composed over the demand-side org plane. Given
an org's `X-Org-Key`, the dashboard answers "what's my pipeline look like",
"who's in the running for this role, with comp context", and "what do I know
about this one candidate, given what they've consented to" — without adding
any new state, tables, or consent path of its own. Peer of `MATCHING.md` /
`COMP.md` / `LEDGER.md`.

**API-first, JSON only.** There is no server-rendered UI here — `src/app/dashboard/`
is a pure composition layer (`DashboardService`) that assembles already-audited
reads from `JobStore`, `CompService`, and `LedgerStore` into three render-ready
contracts. It owns no tables and holds no state.

## Two views: lean board, drill-in card

| Surface | Endpoint | Shape | Purpose |
|---|---|---|---|
| Pipeline overview | `GET /dashboard/overview` | `DashboardOverview` | One glance across all requisitions. |
| Requisition board | `GET /jobs/{req_id}/board` | `RequisitionBoard` | The shortlist for one role, comp-benchmarked. |
| Candidate card | `GET /candidates/{candidate_id}/card` | `CandidateCard` | Drill-in on one candidate, per-section consent-gated. |

The board is deliberately **lean** — it runs the existing S5.1 `run_match` +
S5.2 `benchmark` and returns their outputs as-is (ranked candidate ids +
contributions, plus a comp benchmark). It is *not* per-candidate detail. Seeing
more about any one ranked candidate is a second, explicit request: the **card**.
This split keeps the disclosure surface auditable — loading a board discloses a
list, opening a card discloses one candidate's ledger-derived signals — instead
of one endpoint that silently fans out to N candidate reads.

### `GET /dashboard/overview` → `DashboardOverview`

```json
{
  "total_requisitions": 3,
  "by_status": {"open": 2, "closed": 1},
  "requisitions": [
    {"id": "...", "title": "Backend Engineer", "status": "open",
     "must_have_skill_count": 2, "has_comp_band": true,
     "has_skill_coverage_gate": false,
     "created_at": "...", "updated_at": "..."}
  ],
  "advisory": true
}
```

A summary row is derived from the requisition itself (skill counts, whether a
`comp_band`/`min_skill_coverage` is set) — no match is run, no comp estimate is
computed. Cheap by construction; safe to poll.

### `GET /jobs/{req_id}/board` → `RequisitionBoard`

```json
{
  "requisition": { /* full JobRequisition, S5.1 */ },
  "comp": { /* CompBenchmark, S5.2 — advisory: true */ },
  "match": { /* MatchResult, S5.1 — advisory: true, pool_size, ranked[...] */ },
  "advisory": true
}
```

Composes `JobStore.get_requisition` + `CompService.benchmark` +
`JobStore.run_match` (limited to `dash_board_top_n`, not `match_default_limit`
— the board is a glance, not the full ranked list). `404` if the requisition
isn't found *or* isn't owned by the calling org (cross-org lookups are
indistinguishable from unknown, same as every other org-plane read). `422` if
the candidate pool is empty (nothing materialized yet) — `pool_size == 0` is
the same signal S5.1's `/jobs/{id}/match` already uses; the board just surfaces
it at the HTTP boundary instead of returning a hollow 200.

### `GET /candidates/{candidate_id}/card` → `CandidateCard`

```json
{
  "candidate_id": "...",
  "reputation": {"status": "consent_required", "data": null},
  "coding_rounds": {"status": "no_data", "data": []},
  "records": {"status": "available", "data": [ /* InterviewRecord[] */ ]},
  "advisory": true
}
```

Three independent sections, each a `{status, data}` pair. `status` is a
`SectionStatus`:

- `available` — consent is active and the source returned something.
- `consent_required` — the reused store read raised `ConsentError` (no active
  `ledger_read` grant for this org/candidate).
- `no_data` — consent is active but the source is empty (e.g. nothing
  submitted yet).

## Consent-by-reuse, not new plumbing

The card adds **zero** new consent code. Each section calls the exact store
method an org would call directly, and catches exactly the error that method
already raises:

| Section | Reused call | On `ConsentError` |
|---|---|---|
| `reputation` | `LedgerStore.reputation_for_org` | → `consent_required` |
| `coding_rounds` | `LedgerStore.query_coding_rounds_for_org` | → `consent_required` |
| `records` | `LedgerStore.query_records_for_org` | → `consent_required` |

All three are gated on the same purpose, `ledger_read` — no new
`ConsentPurpose` is introduced. Because each call is already self-auditing
(every read attempt, allowed or denied, writes its own `*.query` audit row in
`audit_log`), the card contributes no separate audit path either — the
existing per-section audit rows *are* the card's audit trail.

**The card is always `200` for a known candidate** — a missing grant degrades
a section to `consent_required` rather than failing the whole request. This
matters because a dashboard render should never break just because one of
three signals is withheld; the employer still sees the two sections (if any)
they *do* have consent for. `404` is reserved for the one case reuse can't
paper over: an **unknown `candidate_id`**. Store methods check org and
candidate existence before the consent check and raise `LookupError`, not
`ConsentError`, for an unknown candidate — the API route lets `LookupError`
propagate to `404` and catches only `ConsentError` per section internally.
Order of the three calls only matters for this case: whichever runs first is
the one that raises.

## Plane boundary: no PII, no depth `Report`, minimal new audit

- **No candidate PII anywhere in these three payloads.** Requests are
  addressed by `candidate_id`; nothing surfaces name, email, phone, or resume
  text. This mirrors every other org-plane read (`MATCHING.md`, `COMP.md`) —
  the org plane never sees first-party contact data, only ledger-derived,
  consent-gated signals and the candidate's own opt-in canonical skills (via
  the match).
- **No depth `Report` (`src/app/schemas/report.py`) is ever surfaced.** The
  fabrication-defense depth score is a platform-internal signal
  (`FABRICATION.md`) — it is deliberately absent from `RequisitionBoard` and
  `CandidateCard`. This is enforced by omission: nothing in `src/app/dashboard/`
  imports `Report` or reads `ReportStore` directly.
- **Audit rows, by endpoint:**
  - `overview` writes **no** audit rows — it's a read-only summary derived
    from data the requesting org already owns.
  - `board` writes two kinds of reused (not new) audit rows: **`match.surface`**
    rows (one per *returned* candidate, candidate-linked, CASCADE) as a side
    effect of the reused `run_match` call — the S5.1 disclosure log — **and**
    one **`comp.aggregate`** row (role-linked, `candidate_id=None`) from the
    reused `comp.benchmark` → `observed_offers_for_comp` call, which audits
    every aggregation (`COMP.md`). Both are inherited audit paths; the
    dashboard adds no audit action of its own.
  - `card` writes each reused store method's **own** audit action
    (`reputation.query` / `record.query` / `coding_round.query`) — allowed
    and denied attempts alike, exactly as if the org had called those reads
    directly. The dashboard adds no audit action of its own.
- **DPDP.** Nothing here is new candidate-linked state, so erasure behavior is
  inherited unchanged from S5.1/S5.2/S3.x: an erased candidate drops from the
  vector pool (board's `pool_size` shrinks), their `match.surface`/
  ledger-query audit rows CASCADE-sweep with them, and a card request for a
  since-erased `candidate_id` becomes the unknown-candidate `404` case.

## Config (`dash_*`)

`dash_board_top_n` (20) — the board's match limit, deliberately smaller than
`match_default_limit` (25, S5.1's own default) since the board is meant as a
glance, not the definitive shortlist; an employer who wants the full ranked
list still has `POST /jobs/{id}/match` directly.

## Seams for later

- **Per-candidate board annotations** — today the board returns the raw
  `MatchResult`; a future pass could join in per-candidate card-status
  summaries (e.g. "consent available") without a card round-trip, at the cost
  of a new disclosure-audit question (does *listing* consent status count as
  a read?).
- **Pagination** — `overview.requisitions` and `board.match.ranked` are
  unbounded within `dash_board_top_n`/store defaults; a real UI would want
  cursor-based paging once org pipelines grow past a glance.
- **PI-6 (candidate side & intake):** this dashboard stays employer-facing
  only; a candidate-facing equivalent (their own applications, their own
  consent ledger) is out of scope here and belongs to the next PI.
