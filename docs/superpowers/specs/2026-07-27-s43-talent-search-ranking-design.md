# S4.3 — Talent Search / Ranking API (design)

**Sprint:** PI-4 / S4.3 · **Date:** 2026-07-27 · **Status:** approved, pre-plan

Prereqs: S4.1 (feature registry) + S4.2 (materialization → `ml_feature_vectors`,
`FeatureStore`, point-in-time slicer) are merged. This sprint adds the
read/rank/serve layer on top; it introduces **no new table, no LLM, no
migration**.

## 1. Goal

A deterministic, **advisory** engine that filters and ranks the materialized
candidate pool by a caller-supplied composite score, returning full per-feature
explainability. It **narrows and orders** a pool — it never auto-rejects, and a
candidate is **never penalized for consent-withheld or absent data**.

Non-goals (guardrails, YAGNI): no org-facing / job-conditioned matching (that is
PI-5 demand side), no persisted searches, no pagination cursor, no SQL-side JSON
projection/index (documented future optimization), no LLM, no new config numeric
scoring knobs.

## 2. Where it sits

S4.2 persists one compact row per `(candidate_id, as_of, view_name,
view_version)` in `ml_feature_vectors`, with consent-tagged features already
**masked to null at materialization** on the reputation-network opt-in basis, and
exposes `FeatureStore.vectors_for_view(view_name, view_version, as_of=None)`. S4.3
reads those rows and ranks over them. The `FeatureRegistry` supplies each
feature's `FeatureSpec` (dtype, `valid_range`, `categories`) needed to normalize.

```
ml_feature_vectors ──vectors_for_view──▶ ranking engine (pure) ──▶ SearchResult
   (consent already                        filter → normalize →        (advisory)
    masked at S4.2)                         score → sort → limit
```

## 3. Design decisions (taken with user, 2026-07-27)

- **D1 — Admin plane only (`X-API-Key`).** Platform-internal search. Reading the
  masked vectors as-is means **no new consent gate** and no new disclosure
  surface (a withheld feature is already null in the row). Org-facing matching,
  where per-org `ledger_read` consent must be re-designed, is deferred to PI-5.
- **D2 — Pool-independent normalization** via `FeatureSpec.valid_range` (numerics)
  and category index (ordinals); boolean 0/1. For ranged features this is
  reproducible: a candidate scores identically regardless of who else is in the
  pool (matches PI-4's point-in-time reproducibility ethos). A **range-less**
  numeric/integer — notably the count features (`num_experiences`,
  `verdict_count`, `distinct_orgs`, `interview_record_count`, …) that carry no
  natural bound — falls back to **pool min-max** and is pool-dependent by
  necessity; this is stated, not hidden.
- **D3 — Drop-term + renormalize + report coverage.** A missing/withheld term is
  dropped, remaining weights renormalized, and each result surfaces a `missing`
  list and a `coverage` fraction (share of ranking weight that had data — the
  `risk.py`/`reputation.py` confidence pattern). Honest (invents no value),
  transparent, and consent-neutral.

## 4. Components

Three isolated units + one endpoint. Units 1–2 are pure (no I/O, no store, no
wall clock), mirroring `app/fabrication/risk.py` and `app/ledger/reputation.py`.

### 4.1 Contracts — `app/features/ranking_schema.py`

Pydantic models + StrEnums, all serializable, no callables:

- `FilterOp` (StrEnum): `eq, ne, gt, gte, lt, lte, in_, not_in, exists, missing`.
- `SortDirection` (StrEnum): `higher_better, lower_better`.
- `FeatureFilter{ feature: str, op: FilterOp, value: FilterValue | None }`
  — `value` is required for all ops except `exists`/`missing` (validated).
  `FilterValue = float | int | bool | str | list[...]` (list only for
  `in_`/`not_in`).
- `RankingTerm{ feature: str, weight: float > 0, direction: SortDirection =
  higher_better }`.
- `RankingSpec{ terms: tuple[RankingTerm, ...] }` — non-empty (validated).
- `Contribution{ feature, raw: FeatureValue, normalized: float, weight: float,
  weighted: float }` — the per-feature explanation.
- `RankedCandidate{ candidate_id, score: float, coverage: float,
  contributions: tuple[Contribution, ...], missing: tuple[str, ...] }`.
- `SearchResult{ advisory: bool = True, as_of, view_name, view_version,
  pool_size: int, filtered_size: int, ranked: tuple[RankedCandidate, ...] }`.

### 4.2 Pure engine — `app/features/ranking.py`

Operates over `FeatureVector` objects (or their `values` dicts) + a
`specs_by_name: dict[str, FeatureSpec]` the caller resolves from the registry.

- **`apply_filters(vectors, filters, specs_by_name) -> list[FeatureVector]`**
  — dtype-aware predicate eval over `values`:
  - A `null`/absent value fails every comparison op; only `missing` matches it,
    only `exists` matches a present value.
  - Ordinal comparisons (`gt`/`gte`/`lt`/`lte`) use the **category index** so
    `highest_degree_level gte "bachelor"` is meaningful; `eq`/`in_` compare the
    string.
  - Unknown feature name, an op invalid for the dtype (e.g. `gt` on categorical),
    or a malformed `value` raises `ValueError` → **400** at the boundary.
- **`normalize_value(spec, value, pool=None) -> float | None`** → `[0, 1]`:
  - numeric/integer: `(x - lo) / (hi - lo)` clamped to `[0,1]` from
    `spec.valid_range`; if the spec has no range, min-max over `pool` (the
    fallback, common for count features); if the pool is degenerate (all equal /
    size 1), return `0.5`.
  - ordinal: `categories.index(x) / (len(categories) - 1)` (single-category
    ⇒ `1.0`).
  - boolean: `1.0`/`0.0`.
  - categorical (non-ordinal): **not rankable** — a `RankingTerm` on one raises
    `ValueError`.
  - `None` → `None` (the missing-term signal for scoring).
  - `direction == lower_better` ⇒ `1 - normalized`.
- **`score(vectors, spec, specs_by_name) -> list[RankedCandidate]`**:
  - For each vector, for each term: normalize; if `None`, record in `missing` and
    exclude the term's weight; else accumulate `weighted = normalized * weight`
    and a `Contribution`.
  - `present_weight = Σ weights of present terms`; `total_weight = Σ all weights`.
  - `score = (Σ weighted) / present_weight` if `present_weight > 0` else `0.0`;
    `coverage = present_weight / total_weight`.
  - Sort: `score` desc, then `candidate_id` asc (deterministic).

`score` builds the per-feature `pool` (all present values of that feature across
the filtered vectors) internally and passes it to `normalize_value`, so the
range-less-numeric fallback works without the caller assembling pools. For a
ranged feature the `pool` argument is ignored, keeping those normalizations
pool-independent.

### 4.3 Serving — `POST /talent/search`

One endpoint on the admin `router` (behind `require_api_key`) in
`app/api/routes.py`.

**Request** (`TalentSearchRequest`):
```
{ view_name?: str,           # default settings.feat_default_view ("core_v1")
  view_version?: int,        # default 1 (default_view(...).version)
  as_of?: datetime,          # default: newest cut present for that view/version
  filters?: [FeatureFilter],
  ranking: RankingSpec,      # required, non-empty
  limit?: int }              # default settings.search_default_limit
```

The view is code-defined; S4.2 only ever materializes `default_view`
(`core_v1` / v1). `view_name`/`view_version` are therefore just the
`ml_feature_vectors` **store key** for forward-compat — an unmaterialized view is
not an error, it yields an empty pool. Only the features referenced in
`filters`/`ranking` are validated against the registry.

**Handler flow:**
1. Resolve `specs_by_name` **per referenced feature** (every `filters[].feature`
   and `ranking.terms[].feature`): `registry.get(name).spec`. An unknown feature
   → `KeyError` → **400**. (No whole-view reconstruction; independent of which
   view is queried.)
2. Default `view_name = settings.feat_default_view`, `view_version = 1` (from
   `default_view(registry, settings=…).version`).
3. `pool = Services.features.vectors_for_view(view_name, view_version, as_of)`.
   If `as_of` is omitted, use `FeatureStore.latest_as_of(view_name,
   view_version)`; `None` (nothing materialized) ⇒ empty pool ⇒ empty result,
   still `advisory=True`.
4. `filtered = apply_filters(pool, filters, specs_by_name)`.
5. `ranked = score(filtered, ranking, specs_by_name)`; sort; truncate to `limit`.
6. Return `SearchResult(advisory=True, …, pool_size=len(pool),
   filtered_size=len(filtered), ranked=…)`.

Errors: unknown feature or dtype-invalid filter op → `ValueError`/`KeyError` →
**400**; missing/empty `ranking` → **422** (Pydantic); no/invalid `X-API-Key` →
**401** (existing gate).

**Wiring:** add `features: FeatureStore` to `Services` (built via
`build_feature_store`, sharing `candidates_db_url`), injected the same way
`ledger` is. `conftest` builds it on the shared session factory.

## 5. Consent, point-in-time, DPDP

- **Consent:** not re-applied at query time. S4.2 masked consent-tagged features
  at materialization (network opt-in basis); a withheld feature is already null,
  so it drops out of scoring and is never a penalty. The admin plane keeps this
  consistent — S4.3 adds **no new disclosure surface**. This is stated in
  FEATURES.md's S4.3 section.
- **Point-in-time:** `as_of` selects the materialized cut; ranking is pure over
  whatever `vectors_for_view` returns. No leakage is introduced (S4.4's
  label-join still depends on the S4.2 cut).
- **DPDP:** no new candidate-linked table ⇒ no new erasure path. Search reads
  `ml_feature_vectors`, which already CASCADE-deletes on candidate erasure; an
  erased candidate simply is not in the pool.

## 6. Config

- **`search_default_limit`** (int, default `50`, `ge=1`) in `config.yaml` +
  `Settings`. The only new knob. No numeric scoring knobs — weights and
  directions are per-request; normalization is code + spec driven.

## 7. Testing (fully offline)

Unit:
- **Filters:** each `FilterOp` per dtype; ordinal `gte`/`lt` via category index;
  `eq`/`in_` on categorical; null value fails comparisons, `missing`/`exists`
  behave; unknown feature and dtype-invalid op raise `ValueError`.
- **Normalization:** numeric via `valid_range` (+ clamp), ordinal via index,
  boolean, `lower_better` inversion, range-less numeric pool min-max fallback
  (incl. degenerate pool ⇒ `0.5`), categorical term rejected.
- **Scoring:** weighted-mean math, renormalization when a term is missing,
  `coverage` value, `missing` list, deterministic tie-break; a consent-withheld
  candidate is ranked (not dropped) and **not penalized** relative to the same
  candidate with the feature present-but-neutral.
- **Contracts:** `RankingSpec` non-empty; filter `value` required except
  `exists`/`missing`.

Endpoint:
- 200 with `advisory=True`, correct `pool_size`/`filtered_size`, `ranked` in
  score-desc order, `limit` honored; a filter narrows the pool; `as_of`
  selects the right cut; an unmaterialized view yields an empty pool (still 200,
  `advisory=True`); 400 on an unknown feature or dtype-invalid filter op; 401
  without the key; 422 on empty `ranking`.

Smoke — `scripts/smoke_s43.py` (uvicorn + HTTP, S4.2 style): populate ≥3
candidates (one consent-withheld), materialize + persist via `FeatureStore`, then
`POST /talent/search`: assert a sensible ranking with visible contributions, a
filter that narrows the pool, and that the consent-withheld candidate appears
with reduced `coverage` but is not pushed to the bottom purely for the withheld
feature. Exit 0.

Target: 529 → ~560 tests.

## 8. Deliverables

- `app/features/ranking_schema.py` (contracts)
- `app/features/ranking.py` (pure engine)
- `FeatureStore.latest_as_of(...)` helper (+ existing `vectors_for_view`)
- `POST /talent/search` in `app/api/routes.py`; `Services.features` wiring
- `search_default_limit` in `config.yaml` + `Settings`
- FEATURES.md S4.3 section
- Tests + `scripts/smoke_s43.py`

## 9. S4.4 seam

S4.4 (training-set export) joins these features ⋈ outcomes. S4.3 changes nothing
about how vectors are written; it only reads them. The `as_of` cut remains the
honest point-in-time boundary the label-join will respect.
