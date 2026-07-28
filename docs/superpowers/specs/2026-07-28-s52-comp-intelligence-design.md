# S5.2 — Comp Intelligence v0 — Design Spec

**Date:** 2026-07-28
**Sprint:** PI-5 / S5.2 (demand side)
**Branch:** `s52-comp-intelligence`
**Status:** Approved design (brainstorm complete) — plan next.
**Depends on:** S5.1 (job requisitions carry an advisory `comp_band`), PI-3 ledger
(orgs, consent, audit, DPDP CASCADE), S1.4 normalization (skill/city-tier tables).
**Charter:** gap-analysis §5.E / §6 — *"Comp intelligence v0 (static bands +
ledger-observed offers, advisory) — consumes S5.1's stored `comp_band`."*

---

## 1. Goal & non-goals

**Goal.** Give an organization an **advisory, explainable compensation band** for a
role, combining a deterministic **static prior** with **consent-gated,
ledger-observed offers** the platform has accumulated, and let it **benchmark a
job requisition's own `comp_band` against market**.

**In scope (v0):**
- A curated, license-clean **static comp table** (the deterministic prior / floor).
- **Observed-offer capture**: a new consent-gated, candidate-linked ledger record
  carrying an offer's CTC + the role signal it pertains to.
- A pure **blend engine** (static prior ⊕ observed aggregate → advisory band).
- Two org-plane read surfaces: a **role estimate** and a **requisition benchmark**.

**Non-goals (v0), each with its landing zone:**
- **No comp-fit match term** in `POST /jobs/{id}/match`. There is no
  candidate-submitted expected-CTC signal to score against; premature until one
  exists. (Deferred — revisit when candidate comp expectations land, PI-6+.)
- **No candidate-facing comp surface** (what a candidate "should" earn). Employer
  intelligence only.
- **No scraped/third-party comp data.** Static bands are hand-authored placeholders
  (license-clean); real market-data licensing is an open item (gap-analysis §8).
- **No auto-anything.** Every output is `advisory=True`; nothing gates or rejects.
- **No LLM.** Comp is deterministic arithmetic (static table + weighted aggregate).

## 2. Where it lives (package split)

Two homes, each holding the concern it owns:

| Concern | Home | Why |
|---|---|---|
| Observed-offer *record* (table, submit, consent-gated read) | **`app/ledger/`** | It is consent-gated, candidate-linked, audited cross-company data — a peer of `coding_round_results`. Keeps consent/audit/erasure uniform. |
| Comp *intelligence* (static bands, blend, estimate, benchmark) | **`app/comp/`** (new) | Pure, table-driven math + role resolution. Reads offers *via* `LedgerStore`; owns no tables. |

`Services.comp` is wired import-cycle-safe (the S4.3 / S5.1 pattern: `TYPE_CHECKING`
annotation + function-local builder). `app/comp/` never imports the API layer;
the graph never imports `app/comp/`.

```
app/comp/
  __init__.py
  schema.py     # pure contracts + SeniorityBand StrEnum + role-family constants
  bands.py      # static curated prior table + deterministic role/seniority/tier resolvers
  estimate.py   # pure blend: static prior (+) observed aggregate -> CompBandEstimate/CompBenchmark
  service.py    # thin: wires LedgerStore observed-offer reads + engine (holds no state beyond deps)
app/ledger/
  models.py     # + ObservedOfferRow
  schema.py     # + ObservedOffer contract
  store.py      # + submit_observed_offer, observed_offers_for_comp
  migrations/   # + 0009_observed_offers
```

## 3. Static bands — the deterministic prior (`app/comp/bands.py`)

A hand-authored, **illustrative, license-clean** seed table (mirrors the
`app/candidates/normalize/` static tables), keyed
**(role_family × seniority × city_tier)** → a band descriptor:

```
CompCell = (fixed_low, fixed_mid, fixed_high, variable_fraction)   # annual INR
```

- Clearly documented at the top of the module as **replaceable seed data**, not
  scraped/licensed; order-of-magnitude realistic for the IT launch vertical.
- **Overridable** via an optional config path (`comp_bands_path`): if set and the
  file loads, it replaces the built-in table; else the built-in seed is used. This
  is how an operator swaps in real, license-clean numbers without a code change.

**Role signal resolution** (deterministic, no LLM):

- `role_family` — a small curated IT set (~8–10): `backend_engineer`,
  `frontend_engineer`, `fullstack_engineer`, `data_engineer`, `data_scientist`,
  `ml_engineer`, `devops_sre`, `qa_engineer`, `mobile_engineer`,
  `engineering_manager`. Resolved by **title keyword ▸ must-have-skill signature ▸
  default `backend_engineer`**. (Alias/keyword tables in-module, `normalize/` style.)
- `seniority` — `SeniorityBand` StrEnum `{junior, mid, senior, lead}`, derived from
  `min_years_experience` via config thresholds (`comp_mid_years` 2, `comp_senior_years`
  5, `comp_lead_years` 9); explicit override allowed on the estimate endpoint.
- `city_tier` — from `location_tiers[0]` (`metro`/`tier_2`); `remote` or unknown →
  `metro` baseline, flagged in `reasoning`.

Any `(role_family, seniority, city_tier)` miss falls back conservatively (nearest
lower seniority, then the role's metro cell) and records the fallback in `reasoning`
— the estimate is **always** answerable from the static table alone.

## 4. Observed offers — capture (`app/ledger/`, migration `0009`)

A new table `observed_offers`, a **peer of `coding_round_results`**:

| Column | Notes |
|---|---|
| `id` | uuid pk |
| `org_id` | FK → organizations, **CASCADE** |
| `candidate_id` | FK → candidates, **CASCADE** (DPDP erasure sweeps it) |
| `consent_id` | the `ledger_write` grant this was submitted under |
| `role_family` | the offer's role signal (an offer's comp belongs to the *role*, |
| `seniority` | not re-derivable from the candidate later — so we store it) |
| `city_tier` | `metro` / `tier_2` |
| `ctc_fixed` | annual fixed CTC, `ge=0` |
| `ctc_variable` | optional annual variable/bonus, `ge=0` |
| `currency` | default `INR` |
| `offered_at` | when the offer was made (drives recency) |
| `created_at` | row write time |

Contract `ObservedOffer` (pydantic; bounds are data hygiene, **not** scoring). Enums
(`SeniorityBand`, role-family) are shared from `app/comp/schema.py` so capture and
intelligence agree on vocabulary.

**Store methods** (mirror interview records / coding rounds exactly):

- `submit_observed_offer(...)` — **`ledger_write`-gated** → raises `ConsentError`
  without an active grant; stamps `consent_id`; audits `offer.submit` in the same
  transaction. `total_ctc = ctc_fixed + (ctc_variable or 0)` is computed at read
  time, never stored (derivable).
- `observed_offers_for_comp(role_family, seniority, city_tier, *, as_of)` — the
  consent-respecting aggregation read (see §6): returns only offers matching the
  role signal whose **stamped grant is still active at `as_of`** (unrevoked,
  unexpired). Audits `comp.aggregate` once with included/excluded counts (never
  per-candidate). Never raises on withheld rows — they are simply excluded.

**Endpoint** `POST /ledger/offers` (org plane, `X-Org-Key`) → 403 (no write consent),
404 (unknown candidate), 422 (malformed), 401 (bad key). Consistent with
`POST /ledger/records` and `POST /ledger/coding-rounds`. **No new `ConsentPurpose`.**

## 5. The blend engine (`app/comp/estimate.py`, pure)

`reputation.py`-style shrinkage of observed data toward the static prior. No I/O,
no clock (`as_of` passed in).

Given a role signal → static cell `(f_low, f_mid, f_high, var_frac)` and a list of
matching observed offers `[(total_ctc_i, offered_at_i)]`. **Everything blends on a
total-CTC basis**: the observed offers already carry total CTC
(`ctc_fixed + (ctc_variable or 0)`), and the static cell is converted to total up
front — `t_low = f_low·(1+var_frac)`, `t_mid = f_mid·(1+var_frac)`,
`t_high = f_high·(1+var_frac)` — so no fixed-vs-total mismatch.

1. **Recency weight** each offer: `w_i = 0.5 ** (age_days_i / comp_recency_halflife_days)`.
   Evidence mass `W = Σ w_i`; weighted observed mean `μ_obs = Σ(w_i·ctc_i) / W`.
2. **k-anonymity floor.** If the raw count `n < comp_min_observations`, the observed
   component is **withheld** — estimate is static-only, `confidence` at its floor,
   `sources = [static]`, `reasoning` says why. (Prevents any small-n re-identification.)
3. **Blend p50** (only when included): pseudo-count `k0 = comp_prior_strength`,
   `p50 = (k0·t_mid + W·μ_obs) / (k0 + W)`. Few offers → static dominates; many →
   observed dominates. Static-only → `p50 = t_mid`.
4. **p25/p75** preserve the **static band's relative spread** around the blended
   midpoint: `p25 = p50 · (t_low/t_mid)`, `p75 = p50 · (t_high/t_mid)`. Deterministic
   and defensible for v0 (observed quantiles are a v1 refinement).
5. **Confidence** grows saturating with `W`: `min(comp_confidence_cap,
   comp_confidence_floor + (1-comp_confidence_floor)·W/(W + comp_confidence_k))`;
   static-only pins to `comp_confidence_floor`.

Output `CompBandEstimate`:

```
currency: str
p25, p50, p75: float                 # annual total CTC
confidence: float [0,1]
role_family, seniority, city_tier    # the resolved signal (echoed back)
n_observed: int                      # included offers (>= comp_min_observations or 0)
sources: tuple[str, ...]             # ("static",) or ("static","observed") — de-identified
reasoning: str                       # resolution + fallback + inclusion notes
advisory: bool = True
```

`sources`/`reasoning` **never** carry candidate or org identities (mirrors the
reputation aggregate's "does not re-leak identities").

**Benchmark** `CompBenchmark` (for `GET /jobs/{id}/comp`): resolve the requisition's
role signal, compute the estimate, then compare the requisition's stored
`comp_band` **midpoint** (mid of `ctc_min`/`ctc_max`; whichever is set if only one;
`None` if neither):

```
estimate: CompBandEstimate
requisition_band: CompBand | None
position: "below" | "at" | "above" | None    # None when no comp_band on the req
delta_pct: float | None                      # (req_mid - p50)/p50
reasoning: str
advisory: bool = True
```

`position` = `at` when `|delta_pct| <= comp_benchmark_tolerance`, else `below`/`above`.

## 6. Consent & DPDP posture (the two judgment calls)

**(A) Cross-candidate aggregation consent basis.** Comp aggregation spans *many*
candidates, so there is no single `ledger_read` grant to check (unlike reputation,
which is per-candidate). v0 basis, defense-in-depth:
1. **Revocation-respecting inclusion** — an observed offer is aggregated only if its
   stamped submitting grant is still active (unrevoked, unexpired) at `as_of`. A
   candidate's revocation removes their offer from future estimates.
2. **k-anonymity floor** — `comp_min_observations`; below it the observed component
   is withheld entirely (estimate stays static-only).
3. **De-identified output** — the aggregate never returns candidate/org ids or
   individual amounts, only the blended band + counts.
4. **Audited** — every aggregation is `comp.aggregate` with included/excluded counts.

Deliberately **no new `comp_intelligence` `ConsentPurpose`**: a purpose no candidate
separately grants would make observed offers permanently empty, defeating the
charter. This is a documented **DPDP residual to revisit** (a dedicated purpose or a
Consent-Manager-mediated aggregation basis is the long-term answer) — logged like
the S3.2 event-append grant-inheritance residual.

**(B) `observed_offers` lives in the ledger, not `app/comp/`** — so consent gating,
`audit_log`, and candidate-erasure CASCADE are the *same* machinery as every other
consent-gated record; comp stays a pure consumer.

**DPDP invariants:** `observed_offers` CASCADEs on candidate erasure (offer vanishes
from future aggregates) and org deletion; `consent_id` stamped; submit is
`ledger_write`-gated; drift/index/FK-ondelete/nullability guards extended to the new
table (the established migration-test discipline).

## 7. Config (`comp_*`, all `DEE_*`-overridable; ASCII comments only)

| Knob | Default | Meaning |
|---|---|---|
| `comp_currency_default` | `INR` | default currency |
| `comp_min_observations` | `5` | k-anonymity floor for the observed component |
| `comp_recency_halflife_days` | `365` | offer recency half-life |
| `comp_prior_strength` | `8.0` | static-prior pseudo-count `k0` |
| `comp_confidence_floor` | `0.30` | static-only confidence (and blend floor) |
| `comp_confidence_cap` | `0.90` | confidence ceiling |
| `comp_confidence_k` | `4.0` | evidence mass where confidence gains half its range |
| `comp_mid_years` | `2` | seniority: junior→mid threshold (years) |
| `comp_senior_years` | `5` | seniority: mid→senior threshold |
| `comp_lead_years` | `9` | seniority: senior→lead threshold |
| `comp_benchmark_tolerance` | `0.10` | ±band around p50 counted as "at market" |
| `comp_bands_path` | *(unset)* | optional path to an operator-supplied static table |

## 8. HTTP summary (org plane, `X-Org-Key`, all advisory)

- `POST /comp/estimate` — body: `{skills?, title?, years_experience?, location_tiers?,
  remote?, role_family?, seniority?}` (overrides win) → `CompBandEstimate`. 400
  malformed, 401 bad key.
- `GET /jobs/{id}/comp` — benchmark the org's requisition → `CompBenchmark`. 404
  cross-org/unknown, 401 bad key.
- `POST /ledger/offers` — submit an observed offer (§4). 403/404/422/401.

## 9. Testing & smoke

- **TDD, fully offline** (NullLLM/fakes; there is no LLM here anyway). Pure units
  (`bands.py` resolvers + table, `estimate.py` blend math, benchmark position) tested
  in isolation; store methods tested against the shared SQLite session; endpoints via
  `TestClient` under the lifespan (the S5.1 `with TestClient(...)` discipline).
- **Migration parity** proven by the drift guard extended to `observed_offers`.
- **Smoke** `scripts/smoke_s52.py` (uvicorn + HTTP), key-less-capable:
  1. estimate for a role with **no observed offers** → static-only band, `sources=(static,)`,
     confidence at floor.
  2. submit `comp_min_observations` offers under a `ledger_write` grant → estimate
     **shifts toward observed**, `sources=(static,observed)`, confidence rises.
  3. submit `< k` offers for a different role → observed **withheld** (static-only).
  4. benchmark a requisition whose `comp_band` sits below / at / above p50 → correct
     `position` + `delta_pct`.
  5. **DPDP**: erase a candidate → their offer drops from the aggregate (estimate
     recomputes; if it falls below `k`, observed withholds again).
  6. revoke a grant → that candidate's offer drops from future estimates.

## 10. Deliverables checklist

- [ ] `app/comp/schema.py` — `SeniorityBand`, role-family constants, `RoleSignal`,
      `CompBandEstimate`, `CompBenchmark` (+ reuse S5.1 `CompBand`).
- [ ] `app/comp/bands.py` — static seed table + config-path override + resolvers.
- [ ] `app/comp/estimate.py` — pure blend + benchmark.
- [ ] `app/comp/service.py` + `Services.comp` wiring.
- [ ] `app/ledger/` — `ObservedOfferRow`, `ObservedOffer`, `submit_observed_offer`,
      `observed_offers_for_comp`, migration `0009_observed_offers` (+ guards).
- [ ] Endpoints: `POST /comp/estimate`, `GET /jobs/{id}/comp`, `POST /ledger/offers`.
- [ ] `comp_*` config knobs (config.yaml + `app/core/config.py`).
- [ ] `COMP.md` (peer of `MATCHING.md`/`LEDGER.md`/`FEATURES.md`).
- [ ] `scripts/smoke_s52.py`; ROADMAP updated; `pytest -q` green.

## 11. Seams for later

- **Real market data** — swap the seed table via `comp_bands_path` (operator) or a
  future licensed-data loader; the blend engine is source-agnostic.
- **Comp-fit match term** — once candidates submit expected CTC, a `match.comp_fit`
  term joins `compile_ranking` (the `MatchWeights`/`match.py` seam already exists).
- **Dedicated aggregation consent** — replace the revocation-respecting basis (§6.A)
  with a `comp_intelligence` purpose or Consent-Manager-mediated aggregation.
- **Observed quantiles** — replace static-shaped p25/p75 with observed quantiles once
  volume supports it.
