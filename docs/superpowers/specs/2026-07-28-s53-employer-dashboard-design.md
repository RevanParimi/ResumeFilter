# S5.3 — Thin Employer Dashboard — Design Spec

**Date:** 2026-07-28
**Sprint:** PI-5 / S5.3 (demand side)
**Branch:** `s53-employer-dashboard`
**Status:** Approved design (brainstorm complete) — plan next.
**Depends on:** S5.1 (job requisitions + `run_match`), S5.2 (`CompService.benchmark`),
PI-3 ledger (orgs, consent, audit, DPDP CASCADE; audited `reputation_for_org` /
`query_coding_rounds_for_org` / `query_records_for_org`).
**Charter:** gap-analysis §5.G / §6 — *"Thin employer dashboard (read-only over
search/reports); API-first stays primary."*

---

## 1. Goal & non-goals

**Goal.** Give an organization **employer-ready read views** that fold the data it
already reaches through the org plane (requisitions, role-conditioned matches, comp
benchmark, cross-company reputation, coding rounds, interview records) into a small
number of **composed, render-ready JSON endpoints** — so a client no longer has to
stitch five calls together per screen.

**In scope (v0):**
- A pure **composition layer** (`app/dashboard/`) over the existing org-plane stores.
- Three org-plane read-models: an **org pipeline overview**, a per-requisition
  **board**, and a per-candidate **card** (the consent-gated drill-in).
- Graceful, **per-section** degradation when a consent purpose isn't granted.

**Non-goals (v0), each with its landing zone:**
- **No HTML / UI.** Pure JSON read-models; "API-first stays primary." A server-
  rendered or SPA surface is deferred (revisit post-PI-5 if an employer UI is wanted).
- **No candidate PII.** Every read-model is keyed by `candidate_id` + advisory
  signals only — name/contact stay platform-internal, exactly as S5.1 `MatchedCandidate`
  already does. The dashboard introduces **no new identity exposure**.
- **No new tables / migration / state.** The layer composes existing rows; it stores
  nothing of its own.
- **No new consent purpose.** Reuse `ledger_read` (the S3.2/S3.4 pattern).
- **No platform-internal depth `Report` exposure to orgs.** The dashboard surfaces
  match-derived signals + ledger signals only; the admin/org plane boundary stays clean
  (revisit if employer-facing depth is later wanted).
- **No write path, no scoring, no auto-anything.** Every output is advisory; the
  layer never mutates candidate data. No LLM.

## 2. Where it lives (package split)

One new home, pure composition:

| Concern | Home | Why |
|---|---|---|
| Dashboard *contracts* + *composition* (overview, board, card) | **`app/dashboard/`** (new) | Pure read-model assembly over `JobStore` + `CompService` + `LedgerStore`. Owns no tables, no I/O primitives of its own; catches `ConsentError` per card section. |

`Services.dashboard` is wired import-cycle-safe (the S4.3 / S5.1 / S5.2 pattern:
`TYPE_CHECKING` annotation + function-local builder). `app/dashboard/` never imports
the API layer; ledger/jobs/comp never import `app/dashboard/`.

```
app/dashboard/
  __init__.py
  schema.py     # pure contracts: DashboardOverview, RequisitionBoard,
                #   CandidateCard, CardSection[*], SectionStatus StrEnum
  service.py    # DashboardService: overview() / board() / card()
```

## 3. The three read-models (all on `org_router`, `X-Org-Key`)

### 3.1 `GET /dashboard/overview` → `DashboardOverview`
Org pipeline summary computed **only from the org's own requisitions** (`JobStore.
list_requisitions(org_id)`).

- `total_requisitions: int`
- `by_status: dict[str,int]` — counts keyed by `RequisitionStatus` value (draft/open/closed)
- `requisitions: tuple[RequisitionSummary, ...]` — per-req lightweight row:
  `id`, `title`, `status`, `must_have_skill_count`, `has_comp_band: bool`,
  `has_skill_coverage_gate: bool`, `created_at`, `updated_at`
- `advisory: bool = True`

**No consent gate, no new audit** (org's own data). **Lean by decision:** the
overview does **not** fan out to comp or the match pool — those live on the board.

### 3.2 `GET /jobs/{req_id}/board` → `RequisitionBoard`
One requisition's consolidated board.

- `requisition: JobRequisition` — the stored req (reuse `JobStore.get_requisition`)
- `comp: CompBenchmark` — reuse `CompService.benchmark(req, org_id=org_id)`
- `match: MatchResult` — reuse `JobStore.run_match(org_id, req_id, as_of=None,
  limit=dash_board_top_n)`; rows are the existing `MatchedCandidate`
  (match-derived, already consent-masked at S4.2) — **no extra cross-org reads**
- `advisory: bool = True`

`run_match` already audits each surfaced candidate as `match.surface` (the
disclosure log); the board adds **no** audit of its own. Error parity with
`POST /jobs/{id}/match`: **404** if the req isn't in this org; **422** if the
materialized pool is empty. `comp.benchmark` on a req whose role signal is
resolvable always returns (static floor when observed offers are below the
k-anonymity floor).

### 3.3 `GET /candidates/{candidate_id}/card` → `CandidateCard`
The consent-gated drill-in. Composes, **keyed by `candidate_id` (no PII)**, the
three cross-company signal sources — **each an independent section**, gated + audited
by **reusing the existing audited store methods** (the layer adds no new audit path):

| Section | Source (reused, audited) | Purpose |
|---|---|---|
| `reputation` | `LedgerStore.reputation_for_org(org_id, candidate_id)` | `ledger_read` |
| `coding_rounds` | `LedgerStore.query_coding_rounds_for_org(org_id, candidate_id)` | `ledger_read` |
| `records` | `LedgerStore.query_records_for_org(org_id, candidate_id)` | `ledger_read` |

**Card is `200` with a per-section `status`** (`SectionStatus`):

- `available` — consent granted; payload present.
- `consent_required` — the reused store call raised `ConsentError`; the section is
  present with a null payload and this status. The card **never hard-403s** just
  because one purpose isn't granted — a dashboard degrades gracefully.
- `no_data` — consent granted but the source returned nothing (e.g. no records yet;
  reputation `INSUFFICIENT_DATA`).

Card shape:
```
CandidateCard{
  candidate_id: str,
  reputation:    CardSection[ReputationAssessment | None],
  coding_rounds: CardSection[tuple[CodingRoundResult, ...]],
  records:       CardSection[tuple[InterviewRecord, ...]],
  advisory: bool = True,
}
CardSection[T]{ status: SectionStatus, data: T | None }
```

**Note (reputation-network semantics carry over):** as with the existing
`/reputation` and `/records` endpoints, a `ledger_read` grant exposes the candidate's
cross-org signals to this org; the card composes but does not widen that exposure
(same grant, same audit). A card for a candidate this org has no consent for is still
`200`, all sections `consent_required`.

## 4. Consent · audit · DPDP posture

- **Reuse `ledger_read`** — no new consent taxonomy.
- **Audit by reuse only** — the card fires the three already-audited store methods
  (each writes its own `*.query` / `comp.aggregate`-style audit row in-txn); the board
  reuses `run_match`'s `match.surface` audit; the overview touches only the org's own
  requisitions (no candidate-linked read → no audit). **No new audit code.**
- **Depth `Report`s stay platform-internal** — not surfaced on any org-plane read-model.
- **No new state** — read-models hold nothing; DPDP erasure already cascades the
  underlying ledger/candidate rows, so there is nothing new to sweep. After erasure a
  candidate drops from match pools (board) and card sections return `no_data` /
  `consent_required` as the underlying reads resolve to empty/denied.

## 5. Architecture & wiring

```
DashboardService(jobs: JobStore, comp: CompService, ledger: LedgerStore)
  .overview(org_id)            -> DashboardOverview        # jobs only
  .board(org_id, req_id)       -> RequisitionBoard | None  # None => req not in org (404)
  .card(org_id, candidate_id)  -> CandidateCard            # per-section ConsentError capture
```

- `service.py` is pure composition: it calls the injected stores, catches
  `ConsentError` **per card section**, and assembles contracts. It owns no DB/session.
- Empty-pool handling stays at the **endpoint** (parity with `POST /jobs/{id}/match`):
  `board()` returns a fully-composed `RequisitionBoard` whose `match.pool_size` may be
  `0`; the route raises **422** when `board.match.pool_size == 0`. `board()` itself
  returns `None` only when the requisition isn't in this org (**404**).
- `Services.dashboard` built function-locally (cycle-safe), sharing the same session
  factory as jobs/comp/ledger (conftest already builds these on one factory).
- Endpoints in `app/api/routes.py` on `org_router`, each `Depends(require_org)`:
  - `GET /dashboard/overview`
  - `GET /jobs/{req_id}/board` — 404 (cross-org) / 422 (empty pool)
  - `GET /candidates/{candidate_id}/card`
- Root endpoint catalog (`app/main.py`) updated with the three routes.

## 6. Config

| Knob | Default | Meaning |
|---|---|---|
| `dash_board_top_n` | `20` | Max ranked candidates returned on a board (passed as `run_match` limit). `ge=1`. |

`dash_*` prefix, `DEE_*`-overridable, in `config.yaml` + `app/core/config.py`.
No LLM knobs.

## 7. Testing (TDD-offline)

- **`DashboardService` unit tests** with store fakes:
  - overview counts by status; per-req flags (`has_comp_band`, `has_skill_coverage_gate`).
  - board composes req + comp + match; honors `dash_board_top_n`.
  - card per-section status matrix: `available` (granted), `consent_required`
    (`ConsentError`), `no_data` (granted but empty / `INSUFFICIENT_DATA`); one section
    denied while another is available on the same card.
- **API tests** via `with TestClient(...)` (lifespan sets `app.state.services`):
  - overview after creating N reqs in mixed statuses.
  - board 404 for a cross-org req; 422 for an unmaterialized/empty pool; 200 shape.
  - card 200 with all sections `consent_required` before any grant; sections flip to
    `available` after `grant_consent(ledger_read)`; back to `consent_required` after
    revoke.
  - every dashboard route rejects a missing/invalid `X-Org-Key` (401).
- ~25–30 new tests (653 → ~680), `pytest -q` green before merge.

## 8. Docs & smoke

- **`DASHBOARD.md`** (repo root, peer of `MATCHING.md` / `COMP.md` / `LEDGER.md`):
  the three read-models, the lean-board / drill-in-card decision, consent-by-reuse and
  the per-section degradation contract, plane boundary (no PII, no depth reports).
- **`scripts/smoke_s53.py`** (uvicorn + scripted HTTP, key-less capable):
  org + key → create req → `overview` shows 1 open → `board` (req + comp + ranked) →
  candidate `card` **without** consent (all sections `consent_required`) → grant
  `ledger_read` → card shows reputation/records `available` → revoke → sections back to
  `consent_required` → cross-org `board` 404. Exit 0 on all checks.

## 9. Sprint conventions (unchanged)

TDD-offline (fakes; `pytest -q` green before merge) · advisory only, no auto-reject ·
DPDP first-party + consent-gated + audited by reuse · config in `config.yaml`, secrets
`DEE_*` · no LLM · smoke ends the sprint. Whole-branch self-review before merge; update
`docs/ROADMAP.md` before finishing.
