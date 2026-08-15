# FEATURES.md — ML feature registry (PI-4, S4.1)

The **feature registry** is a versioned, in-code catalog of ML *feature
definitions* over the data three subsystems already produce — candidate
profiles, depth-evaluation reports, and the consent-gated evaluation ledger
(interview records, coding rounds, reputation). It is the definition/compute
layer the rest of PI-4 consumes: **S4.2** materializes registered features into a
wide `ml_features` table + export; **S4.3** ranks/searches over them; **S4.4**
exports features ⋈ outcomes as a training set.

S4.1 defines *what features exist and how each is computed from one candidate's
point-in-time snapshot*. It does **not** persist feature values (S4.2), serve
them over HTTP (S4.3), or join labels/outcomes (S4.4).

## Model (`src/app/features/`)

Pure package, LLM-free, hand-testable — mirrors `src/app/domains/`.

- **`FeatureSpec`** (`schema.py`) — serializable metadata for one feature:
  `name` (`<namespace>.<snake_case>`), integer `version`, `dtype`
  (`numeric`/`integer`/`boolean`/`categorical`/`ordinal`), `source`, `description`,
  `nullable`, `requires_consent`, optional `valid_range` / `categories`. Metadata
  coherence (range only on numerics, categories only on categorical/ordinal,
  `requires_consent` ↔ ledger/reputation source) is validated at construction.
- **`FeatureContext`** (`schema.py`) — the read-only per-candidate snapshot an
  extractor computes over: `candidate_id`, `as_of`, `profile`, `report`,
  `interview_records`, `coding_rounds`. Exposes a cached `reputation` accessor
  (`assess_reputation` over the snapshot, dated to `as_of`). **Extractors read
  only the context** — never a store, never the wall clock.
- **`@register_feature`** + **`FeatureRegistry`** (`registry.py`) — the decorator
  registers a pure `FeatureContext -> FeatureValue` extractor into the
  module-global registry (the `@register_domain` pattern). `compute_one`
  **validates** every output against its spec (type, nullability, range,
  category) so an out-of-contract value is a loud bug, never a silent clamp.
- **`FeatureView`** — a named, versioned bundle pinning exact `(name, version)`
  pairs; the default view **`core_v1`** (config knob `feat_default_view`) pins
  every seed feature at its latest version, making a materialization/training run
  reproducible. `compute_view` yields a **`FeatureVector`** (values + `missing`).
- **`build_context`** (`context.py`) — the only store-touching helper; assembles
  a snapshot from the candidate/report/ledger stores. See point-in-time below.

## Seed catalog (31 features)

| Source | Consent | Examples |
|---|---|---|
| `candidate.*` (12) | no | `years_experience` (non-overlapping tenure), `highest_degree_level` (ordinal), `top_institution_tier`, `max_cgpa_10`, `notice_period_days`, `location_tier`, `has_github`, `num_skills`/`num_canonical_skills`/`num_experiences`/`num_projects`/`num_certifications` |
| `depth.*` (7) | no | `depth_score`, `depth_band` (ordinal), `overall_confidence`, `verdict_count`, `flagged_claim_count`, `deferred_claim_count`, `coherent_claim_ratio` |
| `fabrication.*` (5) | no | `risk_score`, `risk_band` (ordinal), `ai_generation_band`, `cross_field_major_count`, `resume_farm_band` |
| `ledger.*` (4) | **yes** | `interview_record_count`, `coding_round_count`, `distinct_orgs`, `best_coding_percentile` |
| `reputation.*` (3) | **yes** | `score`, `confidence`, `band` (ordinal) |

**Ordinal categories** are ordered least→greatest with the subsystem's
insufficient/unknown sentinel at index 0; the extractor returns the band string
verbatim (S4.2 owns the numeric encoding, e.g. sentinel→null).

## Point-in-time correctness

Label leakage is a PI-4-wide non-negotiable. S4.1's contribution: `as_of` is a
first-class context field; extractors read only the (already-consistent)
context; reputation decays relative to `as_of`. `build_context` assembles the
*current* snapshot with a coarse `created_at <= as_of` cutoff. The full
historical **slicer** (versioned resumes/reports, consent-validity-at-`as_of`) is
S4.2's materialization job — `as_of` is already the seam.

## Consent (`requires_consent`)

`ledger.*` and `reputation.*` features are derived from consent-gated
cross-company data, so their specs carry `requires_consent=True`. **Enforcement
is a serving-time concern (S4.2/S4.3):** whoever materializes or serves a
`requires_consent` feature for an org must hold an active `ledger_read` grant.
Definition-time carries no consent obligation, and S4.1 adds no new disclosure
surface — `build_context`'s ledger reads are platform-internal (the same raw
internal reads `reputation_for_org` performs after its gate). No new table ⇒ no
new erasure path; after `delete_candidate`, `build_context` returns `None`.

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
Direct-module smoke `scripts/smoke_s41.py` (S3.1 style): ingest a fixture
candidate → depth-eval → submit consented ledger rows → build context → compute
`core_v1` → assert the vector is well-formed, plus a no-ledger candidate.

## S4.2 — Materialization

S4.2 turns the S4.1 *definitions* into persisted, point-in-time-correct rows +
a wide export. Nothing here scores or ranks (S4.3) or joins labels (S4.4).

### Point-in-time slicer (`context.py`)

`build_context` is now a true `as_of` slicer, not a coarse cutoff:

- **profile** — `CandidateStore.profile_as_of(candidate_id, as_of)`: the newest
  extraction with `created_at <= as_of` (tie-break newest resume version, then
  newest created_at); `None` if the candidate had no extraction by `as_of`.
- **report / interview records / coding rounds** — cut at their own
  `created_at` / `interviewed_at` / `taken_at` `<= as_of`.
- **reputation** — decays relative to `as_of` (S4.1 cached accessor).

`build_context` stays a **raw platform-internal assembler**: it reads the full
ledger snapshot and applies **no consent policy** — that is the materializer's
job. A vector at `as_of=T` reflects only data timestamped `<= T`, even when newer
rows exist now (the no-leakage guarantee S4.4's label-join depends on).

### Consent gate (`consent.has_any_active` + `LedgerStore.materialization_consent`)

Materialization is a platform-internal batch use of cross-company data, so the
basis is org-agnostic: **the candidate has opted into the reputation network** =
any active `ledger_read` grant at `as_of` (org-specific or org=NULL).
`has_any_active` is the pure org-agnostic check; `materialization_consent`
resolves it against the candidate's grants and **audits `feature.materialize`**
(actor `system`/`platform`, allowed *and* withheld) in the same transaction. It
returns the decision — withheld does **not** raise.

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

### Export (`export.py`)

The **wide** deliverable is an export-time pivot: header `candidate_id, as_of,
view_name, view_version` then one column per feature **in `view.members` order**.
`export_view_csv` (stdlib `csv`) is always available; null / consent-withheld →
empty cell. `export_view_parquet` types each column from `spec.dtype` and raises
`ParquetUnavailable` when `pyarrow` is not installed (an optional extra, **not**
in core requirements). Exports never re-apply consent — values were masked at
materialization, so a file can never leak a withheld value.

### S4.3 seam

The JSON `feature_values` column keeps S4.2 migration-free as the catalog grows.
When S4.3 knows its query shape it can add a per-feature projection/index (or a
materialized wide view) without changing how S4.2 writes.

### Testing (S4.2)

Slicer (`profile_as_of`, point-in-time `build_context`), `has_any_active`,
`materialization_consent` (allowed/withheld + audit), materializer masking,
`FeatureStore` (upsert idempotency + cascade-on-erase), export (wide CSV shape +
guarded parquet), migration drift guard extended to `ml_feature_vectors`. Smoke
`scripts/smoke_s42.py`: two candidates (A consented with future-dated ledger
rows; B no consent) → materialize/persist/export → prove the point-in-time cut
(A's future rows invisible at `now`, visible later), consent masking (B nulled),
wide CSV header, guarded parquet, and DPDP cascade on erase.

## S4.3 — Talent search / ranking

S4.3 adds the **read/rank/serve** layer over the S4.2 rows: an advisory engine
that filters and ranks the materialized candidate pool by a caller-supplied
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
  contributions, missing}`; `SearchResult{advisory=True, as_of, view_name/version,
  pool_size, filtered_size, ranked}`.
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

A missing term (null value — absent data *or* a consent-withheld feature already
nulled at S4.2) is **dropped**, the candidate's remaining weights are
**renormalized**, and the result surfaces both a `missing` list and a `coverage`
fraction (share of ranking weight that had data — the `reputation.py`/`risk.py`
confidence pattern). Withholding consent can only lower `coverage`, never rank:
a candidate scored on its present terms alone is never pushed below a candidate
whose extra term merely scored low.

### Serving (`POST /talent/search`, admin plane)

One endpoint on the admin `router` (`X-API-Key`). Body: `ranking` (required,
non-empty), `filters` (optional), `view_name`/`view_version` (default the
materialized `core_v1`/v1), `as_of` (default the view's newest cut via
`FeatureStore.latest_as_of`), `limit` (default `search_default_limit`, 50). The
handler resolves specs **per referenced feature** from the registry (unknown name
→ 400), loads the pool via `FeatureStore.vectors_for_view`, then filter → score →
sort → limit. Errors: unknown feature / dtype-invalid op → 400; empty `ranking` →
422; no admin key → 401. An unmaterialized view is not an error — it yields an
empty pool (still 200, `advisory=True`).

### Consent, point-in-time, DPDP

- **Consent** is **not re-applied at query time**. S4.2 masked consent-tagged
  features at materialization on the reputation-network opt-in basis, so a
  withheld feature is already `null` in the row and simply drops out of scoring.
  The admin plane keeps this consistent — S4.3 adds **no new disclosure surface**.
  (Org-facing, per-org-consented search is PI-5 demand-side work.)
- **Point-in-time**: `as_of` selects the materialized cut; ranking is pure over
  whatever `vectors_for_view` returns — no leakage introduced.
- **DPDP**: no new candidate-linked table ⇒ no new erasure path; search reads
  `ml_feature_vectors`, which already CASCADE-deletes with the candidate.

### Config

One knob: **`search_default_limit`** (int, default 50, `ge=1`). No numeric scoring
knobs — weights/directions are per-request; normalization is code + spec driven.

### Testing (S4.3)

Fully offline: filter ops per dtype (incl. null/exists/missing, ordinal-index
comparisons, dtype-invalid op), normalization per dtype + `lower_better` +
range-less fallback, scoring math (renormalization, coverage, tie-break, and the
consent-withheld-not-penalized invariant asserted directly), `latest_as_of`,
`Services.features` wiring, and endpoint 200/400/401/422 + `advisory=True` + limit
+ `as_of` selection + empty pool. Smoke `scripts/smoke_s43.py` (uvicorn + HTTP):
three candidates (none consented) → materialize/persist → search proves a sensible
ranking with contributions, a filter that narrows the pool, and that
consent-withheld candidates are ranked with reduced `coverage` (reputation dropped)
rather than pushed to the bottom.

## S4.4 — Training-set export (features ⋈ outcomes)

S4.4 adds the **label-join / training-set export** layer: each stored
`ml_feature_vectors` row (features at `as_of=T`) joined to a **ground-truth label
derived only from ledger outcomes strictly after T** — the point-in-time-correct,
leakage-free training set. Read-side only: **no new table, no migration, no HTTP,
no LLM, no config knob** (mirrors S4.3).

### No-leakage seam

Features come from data timestamped `≤ T`; the label from `interview_records`
with `interviewed_at > T` and `coding_round_results` with `taken_at > T`. The
**strict `>`** is the guarantee — a record at exactly `T` fed the features and can
never be a label (asserted directly in tests + smoke).

### Label (`training_schema.py` + `training.py`)

`build_label` is pure (no store/clock — the `risk.py`/`reputation.py` pattern).
Per vector it emits a `TrainingLabel`:

- `outcome` — **terminal-best** post-cut interview outcome, ranked
  `hired>offer>advanced>rejected>no_show`; **`withdrawn` excluded** (non-signal,
  per S3.4). `hired` = terminal ∈ `{hired, offer}`.
- `event_at` / `lag_days` — earliest `interviewed_at` carrying that outcome, and
  its distance from `as_of` in days (lets a modeler window/censor).
- `coding_best_percentile` — max post-cut coding percentile (independent of the
  interview label).
- `observed` — a post-cut non-withdrawn interview record exists. When False the
  example is **right-censored** (`hired`/`outcome` null) — *not* a negative.
- `withheld` — consent was not active at `as_of`; the label is unread and null.

### Consent (reuse S4.2 decision + audit)

The label is derived from the same consent-gated cross-company records S4.2 masks,
so it **inherits the S4.2 decision** stored in `MaterializedVector.consent_state`.
`build_training_set` reads the ledger only for a consented vector (a withheld
candidate's outcomes are never fetched) and audits every join via
`LedgerStore.audit_training_label` → `training.label` (allowed/withheld), keeping
platform use of gated data observable without a new gate. A withheld vector's
`ledger.*` features are already null *and* its label is withheld — consistent.

### Export (`export.py`)

`export_training_csv` / `export_training_parquet` = the S4.2 wide feature pivot
(shared `feature_columns` / `vector_cells` helpers) **plus** appended
`label_hired, label_outcome, label_coding_best_percentile, label_event_at,
label_lag_days, label_observed, label_withheld`. Values are already
masked/withheld, so a file can never leak. Parquet stays guarded
(`ParquetUnavailable` without pyarrow).

### DPDP

No new candidate-linked table ⇒ no new erasure path; labels recompute from ledger
rows that already CASCADE on erasure, and the `training.label` audit rows are
candidate-linked and CASCADE too.

### Testing (S4.4)

Pure `build_label` (no-leakage boundary, terminal-best + withdrawn-excluded,
event_at/lag, hire-positive set, censoring, coding-best, consent-withheld),
`audit_training_label`, `build_training_set` over a mix (labeled / censored /
withheld) proving no ledger read when withheld + every join audited, and labeled
export shape (CSV header + values, guarded parquet). Smoke `scripts/smoke_s44.py`:
A consented+labeled (post-cut hired, point-in-time features), B consented+censored
(pre-cut hired does NOT leak), C withheld (features + label null, `training.label`
withheld audit).
