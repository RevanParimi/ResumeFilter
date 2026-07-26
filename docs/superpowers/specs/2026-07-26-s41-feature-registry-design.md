# S4.1 — Feature registry design

**Date:** 2026-07-26
**Sprint:** S4.1 (PI-4 ML Feature Store & Ranking — first sprint)
**Status:** Approved direction (user, 2026-07-26): registry shape =
**code-first `@register_feature` decorator** (recommended); ledger/reputation
features =**included in the seed catalog, tagged consent-gated** (recommended).
User delegated the remaining technical choices.
**Builds on:** PI-1 (candidate backbone + India normalization), PI-2 (fabrication
defense), PI-3 (evaluation ledger + coding rounds + cross-company reputation).

## What we are building

The first sprint of the ML layer: a **versioned, in-code catalog of feature
definitions** over the data three subsystems already produce — candidate
profiles, depth-evaluation reports, and the consent-gated evaluation ledger
(interview records, coding rounds, reputation).

A *feature definition* is a named, typed, versioned descriptor plus a **pure
extractor function** that computes one scalar from a single candidate's
point-in-time snapshot. The registry is the metadata + compute-contract layer
that the rest of PI-4 consumes:

- **S4.2** materializes registered features into a wide `ml_features` table and
  CSV/parquet export (point-in-time-correct);
- **S4.3** ranks/searches candidates over a composite of registered features;
- **S4.4** exports registered features ⋈ ground-truth outcomes as a training set.

S4.1 defines *what features exist and how each is computed*. It deliberately
stops short of persisting feature **values** (S4.2), serving them over HTTP
(S4.3), and joining **labels/outcomes** (S4.4).

## Where the registry lives (and where it does not)

A new pure package **`app/features/`**, a peer of `app/domains/`,
`app/fabrication/`, and `app/ledger/`. Like them it is deterministic,
LLM-free, hand-testable, and has no I/O in its core.

Boundaries, stated the way S3.4 stated reputation's:

- **Not in the depth-evaluation graph.** The graph is per-resume and
  identity-blind; features are computed *for materialization and ranking* over a
  candidate's full cross-subsystem snapshot, which the graph never assembles.
  (Same reasoning that put resume-farm detection and reputation outside the
  graph.)
- **Not a `Report` field.** Features are a separate ML artifact, not
  candidate/resume-facing advisory output. Keeping them apart avoids leaking a
  consent-gated cross-company signal into the ungated report.
- **No migration, no HTTP endpoint this sprint.** The wide `ml_features` table
  is S4.2; the search/ranking API is S4.3. S4.1 is pure definitions + a registry
  + a seed catalog + a thin context assembler, exercised by a **direct-module
  smoke** (the S3.1 pattern, not an HTTP smoke).

## Decisions taken

| Decision | Choice | Rationale |
|---|---|---|
| Registry shape | **Code-first `@register_feature` decorator** over pure extractor functions | User-approved. Exactly the `@register_domain` pattern the codebase already blesses: typed, git-versioned, deterministic, hand-testable, migration-free. DB persistence belongs to feature *values* (S4.2's `ml_features` table), not definitions. |
| Ledger/reputation features | **In the seed catalog, tagged `requires_consent=True`** | User-approved. Gives a complete, forward-looking catalog; the tag is the DPDP hook S4.2/S4.3 enforce at compute/serve time. Definition-time carries no consent obligation. |
| Feature versioning | **Integer `version` per feature name**, bumped when the computation changes | Simple, reviewable in git; a `FeatureView` pins exact `(name, version)` pairs so materialization/training runs are reproducible. Semver is unnecessary for a scalar's compute. |
| Persist definitions in a table? | **No** | Would create two sources of truth (code extractor vs DB row) needing a drift guard, and a migration for what is really code metadata. YAGNI. |
| Feature values / point-in-time slicing | **Deferred to S4.2** | S4.1 defines the `as_of`-aware context + the no-leakage convention and assembles at `as_of=now`; the historical slicer is S4.2's "point-in-time-correct materialization". |
| Labels / outcomes | **Deferred to S4.4** | The registry catalogs *predictors only*; outcome fields are join-time targets, never stored features (original spec). Extractors that would read an outcome are out of scope by construction. |
| Graph / Report / flywheel | **Untouched** | Features are an offline ML artifact assembled outside the pipeline. |
| LLM | **None** | Pure deterministic extraction, like domains and the fabrication/reputation math. |
| Config surface | **One knob** (`feat_default_view`); no numeric behavior knobs | Feature logic is code-versioned (like `@register_domain` and the reputation outcome map), not deploy-tuned. |

## Package layout

```
app/features/
├── __init__.py          public API: get_feature_registry(), register_feature,
│                        build_context(), FeatureView helpers
├── schema.py            contracts (below) — no I/O, no LLM
├── registry.py          FeatureRegistry + @register_feature + module-global default
├── context.py           build_context(candidate_id, *, stores, as_of=now)
└── definitions/
    ├── __init__.py      imports every definitions module so decorators fire
    │                    (mirrors app/domains/__init__.py)
    ├── candidate.py     profile-derived features (source CANDIDATE)
    ├── depth.py         depth-report-derived features (source DEPTH)
    ├── fabrication.py   fabrication-risk-derived features (source FABRICATION)
    └── ledger.py        ledger + reputation features (LEDGER/REPUTATION, consent-gated)
```

`get_feature_registry()` imports `app.features.definitions` (firing every
`@register_feature`) then returns the populated module-global registry — the
exact load pattern of `app/domains/__init__.py` + `get_domain`.

## Contracts (`app/features/schema.py`)

**`FeatureDType(StrEnum)`** — `NUMERIC`, `INTEGER`, `BOOLEAN`, `CATEGORICAL`,
`ORDINAL`. Drives output validation now and column typing in S4.2.

**`FeatureSource(StrEnum)`** — `CANDIDATE`, `DEPTH`, `FABRICATION`, `LEDGER`,
`REPUTATION`. Which subsystem the extractor reads.

**`FeatureValue`** = `float | int | bool | str | None`. The scalar a feature
computes; `None` means "not available for this candidate" (only legal when
`nullable`).

**`FeatureSpec`** — the JSON-serializable metadata (no callable):

| Field | Type | Meaning |
|---|---|---|
| `name` | `str` | stable id, namespaced by source, e.g. `"candidate.years_experience"` (`<namespace>.<snake_case>`, validated) |
| `version` | `int ≥ 1` | bump when the computation changes |
| `dtype` | `FeatureDType` | output type |
| `source` | `FeatureSource` | originating subsystem |
| `description` | `str` | human-readable; non-empty |
| `nullable` | `bool = True` | may the value be `None`? |
| `requires_consent` | `bool = False` | `True` ⇒ derived from ledger data; S4.2/S4.3 must hold an active `ledger_read` grant to materialize/serve it |
| `valid_range` | `tuple[float, float] \| None` | asserted output bounds (NUMERIC/INTEGER only) |
| `categories` | `tuple[str, ...] \| None` | allowed values, **ordered** for ORDINAL (CATEGORICAL/ORDINAL only) |
| `tags` | `tuple[str, ...] = ()` | free-form grouping |

Coherence rules (validated at registration): `valid_range` only on
NUMERIC/INTEGER; `categories` required for CATEGORICAL/ORDINAL and forbidden
otherwise; `requires_consent` implied-consistent with `source ∈ {LEDGER,
REPUTATION}` (asserted, not silently corrected).

**`FeatureContext`** — the read-only per-candidate snapshot an extractor
computes over (a lightweight, read-only-by-convention dataclass exposing a
cached `reputation` accessor; hand-constructable in tests):

```
candidate_id: str
as_of: datetime                      # point-in-time boundary (tz-aware UTC)
profile: CandidateProfile | None
report: Report | None                # latest depth report at/<= as_of
interview_records: tuple[InterviewRecord, ...] = ()
coding_rounds: tuple[CodingRoundResult, ...] = ()
```

Convention (enforced by S4.2's builder, assumed by every extractor): a context
contains **only** data visible at `as_of`. Extractors read `ctx` and nothing
else — never a store, never `datetime.now()`. Reputation-derived features call
`assess_reputation(ctx.interview_records, ctx.coding_rounds, now=ctx.as_of)`; the
context memoizes that one assessment so the three reputation features share it.

**`FeatureView`** — a named, versioned bundle that pins exact feature versions,
making a materialization/training run reproducible:

```
name: str
version: int
members: tuple[tuple[str, int], ...]   # (feature_name, feature_version)
def resolve(registry) -> list[RegisteredFeature]
```

Helper `latest_view(registry, name, version)` builds a view pinning every
currently-registered feature at its latest version. S4.1 ships the default view
**`core_v1`** = all seed features at version 1.

**`FeatureVector`** — the output of computing a view over a context
(serializable; the row shape S4.2 will persist):

```
candidate_id: str
as_of: datetime
view_name: str
view_version: int
values: dict[str, FeatureValue]        # name -> value (missing features -> None)
missing: tuple[str, ...]               # features that returned None
```

## The registry (`app/features/registry.py`)

Mirrors `app/domains/base.py`'s `_REGISTRY` + `register_domain` + `get_domain`.

**`RegisteredFeature`** = `(spec: FeatureSpec, fn: Callable[[FeatureContext],
FeatureValue])`.

**`FeatureRegistry`**:
- `register(spec, fn)` — validates name format + metadata coherence; rejects a
  duplicate `(name, version)` (collision ⇒ `ValueError`), so re-registering the
  same version with different logic is caught.
- `get(name, version=None) -> RegisteredFeature` — `version=None` ⇒ latest;
  unknown ⇒ `KeyError` listing what's registered (like `get_domain`).
- `latest_version(name) -> int`; `names() -> list[str]`;
  `specs() -> list[FeatureSpec]` (deterministic sort by name, version).
- `compute_one(name, ctx, *, version=None) -> FeatureValue` — runs `fn(ctx)`,
  then **validates the output**: type matches `dtype` (with int/float coercion),
  `None` only if `nullable`, within `valid_range`, in `categories`. A violation
  raises (a feature that returns an out-of-contract value is a bug, surfaced
  loudly in tests — never silently clamped).
- `compute_view(view, ctx) -> FeatureVector` — computes each member, collecting
  `None`s into `missing`.
- `manifest() -> list[dict]` / `manifest_json() -> str` — serialize every
  `FeatureSpec` deterministically; the catalog artifact S4.2/S4.4 read.

**`@register_feature(...)`** — decorator that builds a `FeatureSpec` from its
kwargs and registers `(spec, fn)` into the module-global default registry,
returning `fn` unchanged. Escape hatch `_register(spec, fn, registry=...)` for
tests / programmatic registration (parallels `_register_instance`).

## Context assembly (`app/features/context.py`)

`build_context(candidate_id, *, candidate_store, report_store, ledger_store,
as_of=None) -> FeatureContext | None`:

- `as_of` defaults to `utcnow()`. Returns `None` if the candidate does not exist.
- Assembles: `candidate_store.latest_profile(candidate_id)`; the most recent
  `report_store.for_candidate(candidate_id)` entry created at/<= `as_of`;
  `ledger_store.records_for_candidate(candidate_id)` and
  `coding_rounds_for_candidate(candidate_id)` (the raw ungated internal reads —
  see DPDP note below).
- **Point-in-time slicing is S4.2.** S4.1 assembles the *current* snapshot
  (`as_of=now`); the seam for slicing ledger/report history to an arbitrary
  `as_of` is documented here and filled in S4.2. (This is why `as_of` is already
  a first-class context field.)

The builder is the only part of `app/features/` that touches stores; it stays
thin so the registry + extractors remain pure and unit-testable against
hand-built contexts.

## Seed catalog (`app/features/definitions/`)

~28–30 features, each a pure extractor returning `None` gracefully when its input
is absent (never raising on missing data). Representative set (final list settled
in the plan):

**`candidate.py`** — source `CANDIDATE`, `requires_consent=False`:
- `candidate.years_experience` — NUMERIC [0, 60]; **non-overlapping** experience
  months / 12 (parse `YYYY-MM`/`YYYY` `DateRange`s, merge overlapping intervals,
  `is_current` ⇒ `as_of`); `None` if no dated experience.
- `candidate.num_experiences` / `num_projects` / `num_certifications` — INTEGER.
- `candidate.num_skills` / `num_canonical_skills` — INTEGER (all vs
  taxonomy-mapped).
- `candidate.highest_degree_level` — ORDINAL `["none","diploma","bachelor",
  "master","doctorate"]` from `degree_level`.
- `candidate.max_cgpa_10` — NUMERIC [0, 10], nullable; max `grade_cgpa_10`.
- `candidate.top_institution_tier` — ORDINAL `["none","tier_2","tier_1"]`.
- `candidate.notice_period_days` — INTEGER [0, 365], nullable.
- `candidate.location_tier` — ORDINAL `["unknown","tier_2","metro"]`.
- `candidate.has_github` — BOOLEAN (any `LinkType.GITHUB`).

**`depth.py`** — source `DEPTH`, `requires_consent=False` (first-party eval of
the candidate's own resume):
- `depth.depth_score` — NUMERIC [0, 1]; `depth.overall_confidence` — NUMERIC.
- `depth.depth_band` — ORDINAL `["insufficient_signal","superficial","emerging",
  "solid","deep"]`.
- `depth.flagged_claim_count` / `deferred_claim_count` / `verdict_count` —
  INTEGER.
- `depth.coherent_claim_ratio` — NUMERIC [0, 1], nullable (coherent /
  total verdicts).

**`fabrication.py`** — source `FABRICATION`, `requires_consent=False`:
- `fabrication.risk_score` — NUMERIC [0, 1], nullable
  (`report.fabrication_risk.score`).
- `fabrication.risk_band` — ORDINAL `["insufficient_data","low","moderate",
  "elevated"]`.
- `fabrication.ai_generation_band` — ORDINAL `["insufficient_text","unlikely",
  "possible","likely"]`.
- `fabrication.cross_field_major_count` — INTEGER (major findings).
- `fabrication.resume_farm_band` — ORDINAL `["insufficient_data","unique",
  "similar","near_duplicate"]`.

**`ledger.py`** — source `LEDGER`/`REPUTATION`, **`requires_consent=True`**:
- `ledger.interview_record_count` / `coding_round_count` — INTEGER.
- `ledger.distinct_orgs` — INTEGER (distinct `org_id` across records + coding).
- `ledger.best_coding_percentile` — NUMERIC [0, 100], nullable (max
  `percentile`).
- `reputation.score` — NUMERIC [0, 1]; `reputation.confidence` — NUMERIC [0, 1];
  `reputation.band` — ORDINAL `["insufficient_data","guarded","mixed",
  "favorable","strong"]`. All three from the context's memoized
  `assess_reputation`.

Each ordinal's `categories` are ordered least→greatest **with the subsystem's
insufficient/unknown sentinel at index 0** (so the raw band string validates
directly against `categories` — the extractor returns the band verbatim, never a
recoded integer). The sentinel is a valid band value, not "least quality"; S4.2
owns the numeric encoding (e.g. mapping the sentinel to null rather than the low
end) so no information is lost. Keeping the encoding in S4.2 is why the registry
stores ordered category names, not integers.

## Point-in-time correctness (the S4.1 stance)

Label leakage is a PI-4-wide non-negotiable. S4.1's contribution:

1. `as_of` is a first-class, required context field (tz-aware UTC).
2. The no-leakage **convention**: a `FeatureContext` holds only data visible at
   `as_of`; extractors read only `ctx`, never a store or the wall clock.
3. Reputation features pass `now=ctx.as_of` into `assess_reputation`, so recency
   decay is computed relative to the snapshot, not real time.

The historical **slicer** (filtering ledger rows / report versions to `<=
as_of`) is S4.2's materialization job; S4.1 assembles at `as_of=now` and leaves
the documented seam.

## Config (`config.yaml` + `app/core/config.py`, `DEE_*`-overridable)

| Knob | Default | Meaning |
|---|---|---|
| `feat_default_view` | `"core_v1"` | name of the default `FeatureView` the smoke (and S4.2's materializer) resolve |

No numeric behavior knobs: feature logic is code-versioned, not deploy-tuned
(consistent with `@register_domain` and the reputation outcome-value map, which
are also code constants). New numeric tunables, if any arise, land with the
subsystem that needs them.

## DPDP

- **No new table, no new candidate-linked rows ⇒ no new erasure path.** Every
  input the context reads (profile, reports, ledger rows) already CASCADEs on
  `CandidateStore.delete_candidate`; after erasure `build_context` returns
  `None` (candidate gone), consistent with the other reads.
- **Consent boundary.** The `build_context` reads of ledger data are
  *platform-internal* (the platform assembling features over its own store for
  materialization), the same raw internal reads `reputation_for_org` performs
  *after* its gate — not an org disclosing another org's data. The
  cross-org **disclosure** gate is enforced where disclosure happens: S4.2
  materialization / S4.3 serving must hold `ledger_read` before emitting any
  `requires_consent` feature. S4.1 marks those features so that enforcement has
  something to key on; it introduces no new disclosure surface itself.
- First-party data only; no new consent taxonomy.

## Testing strategy (TDD, fully offline)

- **Contracts (`schema.py`):** `FeatureSpec` validation — name format;
  `valid_range` only numeric; `categories` required/forbidden by dtype;
  `requires_consent`↔source coherence. `FeatureView.resolve`;
  `latest_view`; `FeatureVector` shape.
- **Registry (`registry.py`):** register + duplicate-`(name,version)` collision;
  `get` latest vs pinned; unknown ⇒ `KeyError`; `compute_one` output validation
  (type coercion, nullability, range, categories — each rejection tested);
  `compute_view` collects `missing`; `manifest()` deterministic + round-trips.
- **Seed features:** each computes the expected value on a built context and
  returns `None` on absent input without raising. Dedicated tests for
  `years_experience` non-overlap merge math and the ordinal maps
  (`highest_degree_level`, `depth_band`, `reputation.band`). Reputation features
  use `ctx.as_of` as `now` (recency decays against the snapshot).
- **Catalog integrity:** every registered feature is in `core_v1`; every
  `requires_consent` feature has source `LEDGER`/`REPUTATION`; manifest lists all.
- **Context builder (`context.py`):** assembles profile + latest≤as_of report +
  ledger rows for a real ingested candidate; returns `None` for an
  unknown/erased candidate.
- **Smoke `scripts/smoke_s41.py`** (direct-module, key-less-capable, S3.1 style):
  ingest a fixture candidate → auto depth-eval → create an org + grant
  `ledger_write` → submit a couple of interview records + a coding round → build
  the context → compute `core_v1` → assert the vector is well-formed (declared
  dtypes/ranges honored, expected non-null features present, `requires_consent`
  ledger features populated), print the manifest + vector, exit 0. Also runs
  against a candidate with **no** ledger data (ledger features → `missing`,
  nothing raises).

Estimated ~40–50 new tests (468 → ~510–515).

## Explicitly out of scope (later PI-4 sprints)

- The wide `ml_features` table, value persistence, CSV/parquet export, and
  point-in-time historical slicing — **S4.2**.
- Any HTTP surface; composite scoring, filtering, talent search/ranking — **S4.3**.
- Labels/outcomes and the features ⋈ outcomes training-set join — **S4.4**.
- Consent **enforcement** on `requires_consent` features (S4.1 only tags them);
  learned per-org reliability; real embeddings / semantic features — S4.2+/PI-8.
- Any graph node, `Report` field, LLM, or auto-reject. All remain non-goals.

## Sprint workflow

spec (this doc) → implementation plan (`docs/superpowers/plans/`) → TDD-offline
build → `pytest -q` green → direct-module smoke → update `docs/ROADMAP.md`
(status board `S4.1 [x]`, "Current state", session log). A `FEATURES.md`
architecture doc (peer of `LEDGER.md`/`FABRICATION.md`) is written with the
build to document the registry + catalog.
