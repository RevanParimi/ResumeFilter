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

## Model (`app/features/`)

Pure package, LLM-free, hand-testable — mirrors `app/domains/`.

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
`app/features/definitions/` module (imported by `definitions/__init__.py`). Keep
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
