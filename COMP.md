# COMP.md — comp intelligence: advisory salary bands (PI-5 / S5.2)

Advisory compensation intelligence for the demand side. Given a role, an
organization gets an **advisory comp band** (annual total CTC) built from a
deterministic **static prior** blended with **consent-gated, ledger-observed
offers**, and can **benchmark a job requisition's own `comp_band` against
market**. Peer of `MATCHING.md` / `LEDGER.md` / `FEATURES.md`.

**Advisory, always.** Every output carries `advisory=True`. Comp never gates,
ranks, or rejects — it informs a human. No LLM (deterministic arithmetic).

## Two homes

| Concern | Where | Why |
|---|---|---|
| The observed-offer **record** | `src/app/ledger/` (`observed_offers` table, `submit_observed_offer`, `observed_offers_for_comp`, migration `0009`) | Consent-gated, candidate-linked, audited, DPDP-swept — same machinery as interview records / coding rounds. |
| The comp **intelligence** | `src/app/comp/` (`schema.py`, `bands.py`, `estimate.py`, `service.py`) | Pure, table-driven math + role resolution. Reads offers *via* `LedgerStore`; owns no tables. |

**Layering:** `src/app/ledger/` never imports `src/app/comp/`. The comp vocabulary
(`SeniorityBand`, `ROLE_FAMILIES`, `CITY_TIERS`) lives in `src/app/comp/schema.py`;
`observed_offers` stores `role_family`/`seniority`/`city_tier` as plain strings,
validated at the API boundary (`routes.py`). `Services.comp` is wired
import-cycle-safe (TYPE_CHECKING + function-local build, the S4.3/S5.1 pattern).

## The static prior (`src/app/comp/bands.py`)

An **illustrative, license-clean seed table** (mirrors `src/app/candidates/normalize/`
static tables): per-role metro-mid fixed CTC (INR) scaled by seniority and
city-tier multipliers, with a spread and a variable fraction. It is **not**
scraped or licensed — hand-authored, order-of-magnitude priors for the IT launch
vertical, and is the **deterministic no-observed fallback**.

- **Override:** set `comp_bands_path` to a JSON file keyed
  `"role_family|seniority|city_tier" -> [fixed_low, fixed_mid, fixed_high,
  variable_fraction]`. It wins where present; the computed seed fills any gap, so
  a lookup **never misses**.
- **Role-signal resolution** (deterministic, no LLM):
  - `role_family` (one of ~10 IT families): **title keyword ▸ skill-signature
    vote ▸ default `backend_engineer`**.
  - `seniority` (`junior|mid|senior|lead`): from `min_years_experience` via
    `comp_mid_years`/`comp_senior_years`/`comp_lead_years` (2/5/9); overridable.
  - `city_tier`: `location_tiers[0]`; remote/unknown → `metro` baseline.

## The blend (`src/app/comp/estimate.py`)

`reputation.py`-style shrinkage toward the prior, **all on a total-CTC basis**
(observed offers carry total; the static cell's fixed figures are grossed up by
its variable fraction first):

1. Recency-weight each offer (`comp_recency_halflife_days`) → mass `W`, mean `μ`.
2. **k-anonymity floor:** if raw count `< comp_min_observations` the observed
   component is **withheld** — estimate stays static-only, `confidence` at
   `comp_confidence_floor`, `n_observed = 0`, `sources = (static,)`.
3. Blend: `p50 = (k0·t_mid + W·μ) / (k0 + W)`, `k0 = comp_prior_strength`.
4. `p25`/`p75` preserve the static band's relative spread around the blended p50.
5. `confidence` saturates with `W` up to `comp_confidence_cap`.

`CompBandEstimate.sources`/`reasoning` are **de-identified** — never a candidate
or org id, mirroring the reputation aggregate's "does not re-leak identities".

**Benchmark:** `CompBenchmark` compares a requisition's stored `comp_band`
midpoint to the estimate p50 → `position` (`below`/`at`/`above`, where `at` is
within `±comp_benchmark_tolerance`) + `delta_pct`. No `comp_band` on the req →
`position=None`, estimate returned anyway.

## Consent & DPDP posture

`observed_offers` is a peer of `coding_round_results`: candidate-linked with
`ondelete="CASCADE"` FKs (erasure sweeps it), org-linked (org delete cascades),
`consent_id`-stamped, submit **`ledger_write`-gated** → `ConsentError`, audited
`offer.submit`. **No new `ConsentPurpose`.**

**Cross-candidate aggregation** (`observed_offers_for_comp`) spans many
candidates, so there is no single `ledger_read` grant to check. The v0 basis,
defense-in-depth:

1. **Revocation-respecting inclusion** — an offer is aggregated only if its
   stamped `ledger_write` grant is still active (unrevoked, unexpired) at
   `as_of`. A candidate's revocation removes their offer from future estimates.
2. **k-anonymity floor** (`comp_min_observations`) — below it the observed
   component is withheld entirely (comp engine).
3. **De-identified output** — the store returns only `ObservedOfferPoint`
   (`total_ctc` + `offered_at`); no candidate/org id ever reaches the engine.
4. **Audited** — every aggregation is `comp.aggregate` (matched/active/excluded
   counts, `candidate_id=None`: the aggregate is about a *role*, not a person).

**Open residual (DPDP, to revisit):** offer data is collected under
`ledger_write` (cross-company evaluation) and reused for comp aggregation. v0
reuses it — only de-identified, k-anonymized, revocation-respecting — rather than
add a `comp_intelligence` purpose that no candidate would separately grant (which
would make observed offers permanently empty). A dedicated purpose or a
Consent-Manager-mediated aggregation basis is the long-term answer. Logged like
the S3.2 event-append grant-inheritance residual.

## HTTP (org plane, `X-Org-Key`, all advisory)

- `POST /ledger/offers` — submit an observed offer. `403` no write consent, `404`
  unknown candidate/org, `400` invalid `role_family`/`city_tier`, `401` bad key.
- `POST /comp/estimate` — body `{skills?, title?, years_experience?,
  location_tiers?, remote?, role_family?, seniority?}` (overrides win) →
  `CompBandEstimate`. `400` malformed, `401` bad key.
- `GET /jobs/{req_id}/comp` — benchmark the org's requisition → `CompBenchmark`.
  `404` cross-org/unknown, `401` bad key.

## Config (`comp_*`)

`comp_currency_default` (INR), `comp_min_observations` (5, k-floor),
`comp_recency_halflife_days` (365), `comp_prior_strength` (8.0),
`comp_confidence_floor` (0.30) / `comp_confidence_cap` (0.90) /
`comp_confidence_k` (4.0), seniority thresholds `comp_mid_years` (2) /
`comp_senior_years` (5) / `comp_lead_years` (9), `comp_benchmark_tolerance`
(0.10), `comp_bands_path` (unset → built-in seed).

## Seams for later

- **Real market data** — swap the seed via `comp_bands_path` or a future
  licensed-data loader; the blend engine is source-agnostic.
- **Comp-fit match term** — once candidates submit expected CTC, a
  `match.comp_fit` term joins `compile_ranking` (`MatchWeights` already has room).
- **Dedicated aggregation consent** — replace the revocation-respecting basis
  with a `comp_intelligence` purpose / Consent-Manager integration.
- **Observed quantiles** — replace static-shaped p25/p75 with observed quantiles
  once volume supports it.
