# FEATURES.md — ML feature registry (PI-4, S4.1)

The **feature registry** is a versioned, in-code catalog of ML *feature
definitions* over the data two subsystems already produce — candidate
profiles and depth-evaluation reports. It is the definition/compute
layer the rest of PI-4 consumes: **S4.2** materializes registered features into
`ml_feature_vectors`; **S4.3** adds the ranking engine that job matching uses.

S4.1 defines *what features exist and how each is computed from one candidate's
point-in-time snapshot*. It does **not** persist feature values (S4.2) or rank
them (S4.3).

## Model (`src/app/features/`)

Pure package, LLM-free, hand-testable — mirrors `src/app/domains/`.

- **`FeatureSpec`** (`schema.py`) — serializable metadata for one feature:
  `name` (`<namespace>.<snake_case>`), integer `version`, `dtype`
  (`numeric`/`integer`/`boolean`/`categorical`/`ordinal`), `source`, `description`,
  `nullable`, `requires_consent`, optional `valid_range` / `categories`. Metadata
  coherence (range only on numerics, categories only on categorical/ordinal,
  `requires_consent` ↔ ledger/reputation source) is validated at construction.
- **`FeatureContext`** (`schema.py`) — the read-only per-candidate snapshot an
  extractor computes over: `candidate_id`, `as_of`, `profile`, `report`.
  **Extractors read only the context** — never a store, never the wall clock.
- **`@register_feature`** + **`FeatureRegistry`** (`registry.py`) — the decorator
  registers a pure `FeatureContext -> FeatureValue` extractor into the
  module-global registry (the `@register_domain` pattern). `compute_one`
  **validates** every output against its spec (type, nullability, range,
  category) so an out-of-contract value is a loud bug, never a silent clamp.
- **`FeatureView`** — a named, versioned bundle pinning exact `(name, version)`
  pairs; the default view **`core_v1`** (config knob `feat_default_view`) pins
  every seed feature at its latest version, making a materialization run
  reproducible. `compute_view` yields a **`FeatureVector`** (values + `missing`).
  Since R2-S2-T1 its risk score/band members use factual-risk v2 and exclude
  writing style. The bundle is now version **3**, retaining the configured name:
  v3 dropped the ledger and reputation members, so vectors stored under an older
  member set are never served under it.
  Historical v1 reports/vectors remain distinct; opposite/unknown report
  semantics yield missing risk features. See [current risk logic](docs/FEATURE_LOGIC.md#combined-advisory-risk).
- **`build_context`** (`context.py`) — the only store-touching helper; assembles
  a snapshot from the candidate and report stores. See point-in-time below.

## Seed catalog (24 features)

| Source | Consent | Examples |
|---|---|---|
| `candidate.*` (12) | no | `years_experience` (non-overlapping tenure), `highest_degree_level` (ordinal), `top_institution_tier`, `max_cgpa_10`, `notice_period_days`, `location_tier`, `has_github`, `num_skills`/`num_canonical_skills`/`num_experiences`/`num_projects`/`num_certifications` |
| `depth.*` (7) | no | `depth_score`, `depth_band` (ordinal), `overall_confidence`, `verdict_count`, `flagged_claim_count`, `deferred_claim_count`, `coherent_claim_ratio` |
| `fabrication.*` (5) | no | `risk_score`, `risk_band` (ordinal), `ai_generation_band`, `cross_field_major_count`, `resume_farm_band` |

**Ordinal categories** are ordered least→greatest with the subsystem's
insufficient/unknown sentinel at index 0; the extractor returns the band string
verbatim (S4.2 owns the numeric encoding, e.g. sentinel→null).

## Point-in-time correctness

Label leakage is a PI-4-wide non-negotiable. S4.1's contribution: `as_of` is a
first-class context field; extractors read only the (already-consistent)
context. `build_context` assembles the
*current* snapshot with a coarse `created_at <= as_of` cutoff. The full
historical **slicer** (versioned resumes/reports, consent-validity-at-`as_of`) is
S4.2's materialization job — `as_of` is already the seam.

## Consent (`requires_consent`)

A spec from a `ledger` or `reputation` source must carry
`requires_consent=True`. **Enforcement is a serving-time concern (S4.2/S4.3):**
whoever materializes or serves a `requires_consent` feature for an org must hold
an active `ledger_read` grant. The shipped catalog has no consent-tagged feature
since the cross-company ledger was removed, so this path is dormant; tests keep
it exercised with probe features. No new table ⇒ no new erasure path; after
`delete_candidate`, `build_context` returns `None`.

## Adding a feature

Drop a `@register_feature(...)`-decorated pure function into the right
`src/app/features/definitions/` module (imported by `definitions/__init__.py`). Keep
it deterministic and `None`-safe on absent input. **Bump `version`** whenever the
computation changes — old and new coexist in the registry, and views pin exact
versions, so historical materializations stay reproducible.

## Testing

Fully offline. Contracts + registry validation + each seed feature (incl.
`years_experience` non-overlap math and the ordinal maps) + catalog integrity
(every feature in `core_v1`; `requires_consent` ↔ source) + `build_context`.

## S4.2 — Materialization

S4.2 turns the S4.1 *definitions* into persisted, point-in-time-correct rows.
Nothing here scores or ranks (S4.3).

### Point-in-time slicer (`context.py`)

`build_context` is now a true `as_of` slicer, not a coarse cutoff:

- **profile** — `CandidateStore.profile_as_of(candidate_id, as_of)`: the newest
  extraction with `created_at <= as_of` (tie-break newest resume version, then
  newest created_at); `None` if the candidate had no extraction by `as_of`.
- **report** — cut at its own `created_at <= as_of`.

`build_context` stays a **raw platform-internal assembler**: it applies **no
consent policy** — that is the materializer's job. A vector at `as_of=T` reflects only data timestamped `<= T`, even when newer
rows exist now.

### Consent gate (`consent.has_any_active` + `LedgerStore.materialization_consent`)

Materialization is a platform-internal batch use, so the basis is
org-agnostic: any active `ledger_read` grant at `as_of` (org-specific or
org=NULL).
`has_any_active` is the pure org-agnostic check; `materialization_consent`
resolves it against the candidate's grants and **audits `feature.materialize`**
(actor `system`/`platform`, allowed *and* withheld) in the same transaction. It
returns the decision — withheld does **not** raise.

If erasure wins before this audit commits, the store raises the specific
`MaterializationCandidateMissingError` (a `LookupError`). The materializer
returns `None`; `POST /features/materialize` counts that subject as skipped and
continues the batch. A failed audit transaction is rolled back before checking
whether the candidate disappeared; unrelated errors propagate. If the audit
commits first, candidate erasure cascades it away and the feature-store write
guard refuses later vector persistence. Allowed/withheld consent rules are
unchanged.


### Materializer (`materialize.py`)

`materialize_candidate` slices the context, computes the view (`compute_view`
validates every value against its spec), then applies the consent decision: if
withheld, every `requires_consent` feature is set to `None` and added to
`missing`; first-party features (`candidate` / `depth` / `fabrication`) are never
touched. Result is a `MaterializedVector` (`vector`, `consent_state`,
`materialized_at`). `materialize_all` maps it over candidate ids.

### Storage (`ml_feature_vectors` + `FeatureStore`, migration `0007`)

One **compact row per `(candidate_id, as_of, view_name, view_version)`**: JSON
`feature_values` (post-masking) + `missing` + `consent_state` + `materialized_at`.
The unique cut makes re-materialization an **idempotent upsert** — distinct
`as_of` cuts coexist; the same cut updates in place. `as_of` is stored/queried as
naive-UTC so the equality lookup round-trips on SQLite. The `candidate_id` FK is
`ondelete=CASCADE`, so **DPDP erasure sweeps materialized rows with the
candidate** — no new erasure path (proven by the cascade test + drift guard).

### S4.3 seam

The JSON `feature_values` column keeps S4.2 migration-free as the catalog grows.
When S4.3 knows its query shape it can add a per-feature projection/index (or a
materialized wide view) without changing how S4.2 writes.

### Testing (S4.2)

Slicer (`profile_as_of`, point-in-time `build_context`), `has_any_active`,
`materialization_consent` (allowed/withheld + audit), materializer masking,
`FeatureStore` (upsert idempotency + cascade-on-erase), migration drift guard extended to `ml_feature_vectors`.

## S4.3 — Ranking engine

S4.3 adds the **rank** layer over the S4.2 rows that job matching uses: an
advisory engine that filters and ranks the materialized candidate pool by a
composite score, with per-feature explainability. It **narrows and orders** — it
never auto-rejects, and a candidate is **never penalized for consent-withheld or
absent data**. No new table, no migration, no LLM.

### Pure engine (`ranking_schema.py` + `ranking.py`)

Two pure modules (no I/O, no store, no clock — the `fabrication/risk.py` pattern):

- **`ranking_schema.py`** — contracts: `FilterOp` / `SortDirection` StrEnums;
  `FeatureFilter{feature, op, value}` (a value is required for every op except
  `exists`/`missing`; list only for `in_`/`not_in`); `RankingTerm{feature,
  weight>0, direction}`; `RankingSpec{terms}` (non-empty); `Contribution` (the
  per-feature explanation); `RankedCandidate{candidate_id, score, coverage,
  contributions, missing}`.
- **`ranking.py`** — `apply_filters` (dtype-aware predicate eval; null fails every
  comparison, only `missing`/`exists` handle it; ordinal ordered ops use the
  category index; unknown feature → `KeyError`, ordered op on a non-orderable
  dtype → `ValueError`), `normalize_value` (see below), and `score` (weighted mean
  of present terms, renormalized by present weight; `coverage = present /
  total weight`; `missing` lists dropped terms; sort `score` desc then
  `candidate_id` asc).

### Normalization (pool-independent where possible)

`normalize_value` maps a value to `[0,1]`: numerics by `FeatureSpec.valid_range`,
ordinals by category index `/ (len-1)`, booleans 0/1; `lower_better` returns
`1 - x`. Ranged features are **reproducible** — a candidate scores identically
regardless of who else is in the pool. A **range-less** numeric/integer (the count
features carry no natural bound) falls back to pool min-max and is pool-dependent
by necessity; a degenerate pool (size < 2) yields a neutral `0.5`. A non-ordinal
categorical is not rankable (`ValueError`).

### Missing / consent-withheld handling

A missing term (null value — absent data or a feature withheld at materialization
or by current serving authorization) is **dropped**, the candidate's remaining weights are
**renormalized**, and the result surfaces both a `missing` list and a `coverage`
fraction (share of ranking weight that had data — the `risk.py` confidence
pattern). Missing consent adds no score penalty or automatic rejection.
Relative rank can still change when terms drop or normalization pools change.

### Consent, point-in-time, DPDP

- **Current consent** is checked before filters, normalization and scoring.
  `JobStore` requires a grant for the requesting org or a wildcard. Historical `as_of` and
  cached `consent_state.allowed` cannot authorize current use. Gated values are
  masked in a serving copy; historical materialization stays intact. A new grant
  cannot fill historically withheld values. Existing job rankings use first-party
  and synthetic terms. Consent reads are snapshots, not locks across delivery.
- **Point-in-time**: `as_of` is a cutoff. Job matching selects each
  candidate's latest snapshot at or before it, so refreshing one candidate does
  not remove the others from the pool. Matching reads each profile at its own
  vector's timestamp.
- **Batch refresh**: omitted `as_of` is resolved once per run, shared across all
  candidates, and returned by `POST /features/materialize`.
- **DPDP**: no new candidate-linked table ⇒ no new erasure path; matching reads
  `ml_feature_vectors`, which already CASCADE-deletes with the candidate.

### Testing (S4.3)

Fully offline: filter ops per dtype (incl. null/exists/missing, ordinal-index
comparisons, dtype-invalid op), normalization per dtype + `lower_better` +
range-less fallback, scoring math (renormalization, coverage, tie-break, and the
consent-withheld-not-penalized invariant asserted directly) and `latest_as_of`.
