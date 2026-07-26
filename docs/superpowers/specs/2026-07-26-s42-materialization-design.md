# S4.2 — Feature Materialization (design)

> PI-4 · Sprint S4.2. Predecessor: S4.1 feature registry
> (`docs/superpowers/specs/2026-07-26-s41-feature-registry-design.md`,
> `FEATURES.md`). Successors consume this: S4.3 ranks/searches over materialized
> features; S4.4 joins them to outcomes for a training set.

## 1. Problem & goal

S4.1 shipped the **definition/compute layer**: 31 pure, versioned features over a
per-candidate `FeatureContext` snapshot, the `core_v1` view, and `build_context`
(a coarse `created_at <= as_of` assembler). It deliberately deferred three things
to S4.2:

1. **Persistence** — nothing writes feature values anywhere.
2. **The full point-in-time slicer** — `build_context` still reads
   `latest_profile` (wall-clock latest, *not* as-of) and does only a coarse
   timestamp cutoff; consent validity is checked at `now`, not `as_of`.
3. **Consent enforcement** — `ledger.*`/`reputation.*` features are tagged
   `requires_consent=True`, but nothing enforces `ledger_read` yet.

S4.2 delivers a **materializer** that turns a `FeatureView` + point-in-time-sliced
`FeatureContext`s into persisted rows in a new `ml_feature_vectors` table, plus a
**wide CSV/parquet export**. It is **point-in-time-correct (no label leakage)** and
enforces `ledger_read` on consent-tagged features **before materializing** them.

**Non-negotiables inherited from the roadmap / CLAUDE.md.** Advisory only (a
feature value is never an auto-reject gate). DPDP: first-party data only, consent
objects + delete paths on any new candidate-linked table. TDD, fully offline
tests (no API key, no network). Every LLM step degrades to a deterministic
fallback — S4.2 is **LLM-free**, so this is trivially satisfied. Config tunables
in `config.yaml`; DB via SQLAlchemy + Alembic on SQLite, Postgres-shaped.

## 2. Design decisions (taken with the user, 2026-07-26)

The user delegated all three to the recommended option.

- **D1 — Consent enforcement model:** *per-candidate gate, one global platform
  table.* A candidate's `requires_consent` features materialize only when the
  candidate has an **active `ledger_read` grant in effect at `as_of`** (org-specific
  or org=NULL — i.e. they opted into the reputation network); otherwise those
  cells are **null with a recorded `consent_withheld` reason**. First-party
  features (`candidate.*`/`depth.*`/`fabrication.*`) always materialize. Every
  gated decision is **audited in-transaction** (allowed/withheld), mirroring
  `reputation_for_org`. Fail-closed and DPDP-clean; one reusable table rather than
  one per consuming org.
- **D2 — Storage shape:** *compact row-per-vector with a JSON `values` column.*
  One row per `(candidate_id, as_of, view_name, view_version)`; maps 1:1 to
  `FeatureVector`; **no migration when features are added/versioned** (the code-first
  registry owns feature identity, and views pin arbitrary version sets that fixed
  columns could not represent). The **wide** deliverable is a *pivot at export
  time*.
- **D3 — Parquet:** *CSV always (stdlib `csv`); parquet optional via a guarded
  `pyarrow` import.* pyarrow is an optional extra, **not** core `requirements.txt`.
  Offline tests never require pyarrow; the smoke exercises CSV always and parquet
  only when the lib is present. Preserves the repo's lean-deps + graceful-degrade
  stance.

## 3. Architecture

New/changed units, each with one purpose and a narrow interface:

```
app/features/
  context.py      (CHANGED)  build_context → true point-in-time assembler
  materialize.py  (NEW)      MaterializedVector + materialize_candidate/_all
  store.py        (NEW)      FeatureStore over ml_feature_vectors (+ builder)
  models.py       (NEW)      FeatureVectorRow ORM (shared Base)
  export.py       (NEW)      wide CSV (stdlib) + guarded parquet pivot
app/candidates/store.py      (CHANGED)  + profile_as_of(candidate_id, as_of)
app/ledger/consent.py        (CHANGED)  + has_any_active(grants, purpose, at)
app/ledger/store.py          (CHANGED)  + materialization_consent(candidate_id, at)
alembic/versions/0007_ml_feature_vectors.py  (NEW)  + drift-guard extension
config.yaml / app/core/config.py             (reuse feat_default_view; no new knob)
FEATURES.md                                  (CHANGED)  S4.2 section
scripts/smoke_s42.py                         (NEW)  uvicorn populate → materialize → export
```

Dependency direction stays clean: `app/features/*` depends on the candidate/report/
ledger stores (as `build_context` already does); the ledger and candidate packages
do **not** import `app/features`.

### 3.1 Point-in-time slicer — `build_context` (context.py, changed)

`build_context` remains the single store-touching assembler and the `as_of` seam.
It becomes fully point-in-time-correct:

| Axis | S4.1 (today) | S4.2 |
|---|---|---|
| profile | `latest_profile` (wall-clock latest) | **`profile_as_of(cid, as_of)`** — newest extraction with `created_at <= as_of` |
| report | max report with `created_at <= as_of` | unchanged (already correct) |
| interview records | filter `interviewed_at <= as_of` | unchanged |
| coding rounds | filter `taken_at <= as_of` | unchanged |
| reputation | decays relative to `as_of` (cached accessor) | unchanged |

`build_context` still performs **raw platform-internal ledger reads** (the same
raw reads `reputation_for_org` performs after its gate) and populates the full
context. **Consent policy is NOT applied here** — assembly and policy stay
separated; the materializer masks consent-tagged values. This keeps `build_context`
reusable and keeps `reputation` (which needs the raw records) intact.

New store method **`CandidateStore.profile_as_of(candidate_id, as_of)`**: the
`latest_profile` query with an added `ExtractionRow.created_at <= as_of` filter,
ordered `ResumeRow.version.desc(), ExtractionRow.created_at.desc()`, limit 1.
Returns `None` when no extraction existed by `as_of` (a candidate materialized
before their first resume was parsed legitimately has a null profile). `as_of`
defaults to `now` — so `build_context(as_of=None)` still yields the current
snapshot, and the S4.1 smoke/tests keep passing.

### 3.2 Consent gate — `has_any_active` + `materialization_consent`

Materialization is a **platform-internal** batch use of cross-company data, not a
single org's read. The consent basis is therefore "**the candidate has opted into
the reputation network**" = there exists at least one active `ledger_read` grant
at `as_of`, regardless of which org it names.

- **`consent.has_any_active(grants, *, purpose, at) -> ConsentDecision`** (pure):
  like `check_consent` but **org-agnostic** — filters grants on `purpose` +
  active-window (`granted_at <= at < expires_at`, not revoked at/before `at`,
  reusing `as_utc`), ignoring `org_id`; selects the authorizing grant with the
  existing `_selection_key` (org-specific ▸ newest ▸ lowest id) for determinism.
  Returns `allowed=False` with a clear reason when none are active.
- **`LedgerStore.materialization_consent(candidate_id, *, at=None) -> ConsentDecision`:**
  loads the candidate's `ledger_read` grants, calls `has_any_active` at `at`
  (default `now`, coerced via `as_utc`), and **audits `feature.materialize`**
  (actor `system`/`"platform"`, entity `candidate`) with `{allowed, consent_id?,
  purpose:"ledger_read"}` **in the same transaction** — allowed *and* withheld are
  both recorded, so the platform's use of cross-company data is itself observable
  (the S3.2/S3.4 audit discipline). Raises `LookupError` for an unknown candidate.
  Unlike the org-facing gated reads, it **does not raise** on withheld — it returns
  the decision, because a withheld candidate still yields a valid row (first-party
  features + nulled consent features).

### 3.3 Materializer — materialize.py (new)

```python
@dataclass(frozen=True)
class MaterializedVector:
    vector: FeatureVector          # from registry.compute_view
    consent_state: dict            # {"allowed": bool, "consent_id"|"reason": ...}
    materialized_at: datetime
```

- **`materialize_candidate(candidate_id, *, view, registry, as_of, candidate_store,
  report_store, ledger_store) -> Optional[MaterializedVector]`:**
  1. `ctx = build_context(candidate_id, …, as_of=as_of)`; `None` (absent/erased) ⇒
     return `None`.
  2. `vector = registry.compute_view(view, ctx)` (S4.1, unchanged — validates each
     value against its spec).
  3. `decision = ledger_store.materialization_consent(candidate_id, at=as_of)`.
  4. If **withheld**: for every resolved feature whose `spec.requires_consent` is
     true, set `values[name] = None` and add `name` to `missing` (dedup, preserve
     view order); `consent_state = {"allowed": False, "reason": decision.reason}`.
     If **allowed**: leave values as computed; `consent_state = {"allowed": True,
     "consent_id": decision.grant_id}`.
  5. Return `MaterializedVector(vector, consent_state, materialized_at=now)`.

  First-party features are never touched by step 4. Masking uses the resolved
  view's specs (`view.resolve(registry)`) to know which names are consent-tagged,
  so it stays correct as the catalog grows.
- **`materialize_all(candidate_ids, *, view, registry, as_of, …stores) ->
  list[MaterializedVector]`:** maps `materialize_candidate` over the ids, dropping
  `None`s. Batch driver only — no persistence side effects; the caller persists.
  (Enumerating "all candidates" is a `CandidateStore` concern the smoke drives via
  known ids; a store-wide `list_candidate_ids` is out of scope unless a task needs
  it — YAGNI.)

### 3.4 Storage — ml_feature_vectors + FeatureStore

**`FeatureVectorRow`** (models.py, on the shared `Base`, Postgres-shaped):

| column | type | notes |
|---|---|---|
| `id` | String(36) PK | uuid4 default |
| `candidate_id` | FK→candidates.id **ondelete CASCADE**, indexed | DPDP sweep |
| `as_of` | DateTime(tz) | point-in-time cutoff of the vector |
| `view_name` | String | e.g. `core_v1` |
| `view_version` | Integer | pinned view version |
| `values` | JSON | `{feature_name: value}` (post-consent-masking) |
| `missing` | JSON | list of null feature names |
| `consent_state` | JSON | `{allowed, consent_id|reason}` |
| `materialized_at` | DateTime(tz) | wall-clock write time (audit/debug) |
| `created_at` | DateTime(tz) | default now |

- **Unique** `(candidate_id, as_of, view_name, view_version)` — re-materializing the
  same cut is an **idempotent upsert**, not a duplicate. **Index** `(view_name,
  view_version)` for export/range scans.
- **Migration `0007_ml_feature_vectors`** creates the table with the CASCADE FK, the
  unique constraint, and both indexes. The metadata-wide **drift guard** (table
  columns / indexes / FK-ondelete / nullability) is extended to cover it, matching
  every prior migration.
- **DPDP:** candidate-linked CASCADE FK ⇒ `CandidateStore.delete_candidate` already
  sweeps materialized vectors. **No new erasure code.** `build_context` already
  returns `None` after erasure, so re-materialization of an erased candidate is a
  no-op.

**`FeatureStore`** (store.py) over its own session factory on the shared
`candidates_db_url` (the ledger/candidate pattern):
- `upsert_vector(mv: MaterializedVector) -> str` — insert or update the row keyed by
  the unique tuple; returns the row id. (`mv.vector` already carries
  `candidate_id`/`as_of`/`view_name`/`view_version`/`values`/`missing`, so no
  separate view arg is needed.)
- `get_vector(candidate_id, *, view_name, view_version, as_of) -> Optional[...]`.
- `vectors_for_view(view_name, view_version, *, as_of=None) -> list[...]` — all
  vectors for a view (optionally pinned to one `as_of`), ordered deterministically
  (`candidate_id`), for export.
- `build_feature_store(settings=None) -> FeatureStore` — engine on
  `candidates_db_url`; schema is Alembic's job, not the builder's.

Row↔contract conversion normalizes datetimes via `as_utc` (SQLite naive-readback,
the established ledger-store fix).

### 3.5 Export — export.py (new)

The **wide** deliverable. Both take an iterable of stored vectors + the resolved
`FeatureView` (for column order):

- **`export_view_csv(rows, *, view, path, null_token="")`** — stdlib `csv`.
  Header: `candidate_id, as_of, view_name, view_version` then each feature **in
  `view.members` order**. One line per vector; `None` (missing or consent-withheld)
  → `null_token`. Deterministic column order ⇒ reproducible files.
- **`export_view_parquet(rows, *, view, registry, path)`** — **guarded** `import
  pyarrow` inside the function; on `ImportError` raise `ParquetUnavailable` (a
  module-level exception) with an actionable message. Takes `registry` to resolve
  each member's `FeatureSpec`; builds one column per fixed field + one per feature,
  typed from `spec.dtype` (numeric→float64, integer→int64 nullable, boolean→bool
  nullable, categorical/ordinal→string); nulls preserved as arrow nulls. Same column
  order as CSV (`view.members`).

Neither export re-applies consent — the stored `values` are already masked at
materialization, so an exported file can never leak a consent-withheld value.

### 3.6 Config / docs / smoke

- **Config:** reuse `feat_default_view` (already `core_v1`) as the view the
  materializer/smoke resolve. **No new numeric knob** — feature logic and view
  membership are code-versioned, not tunable.
- **Docs:** `FEATURES.md` gains an S4.2 section (materialization, point-in-time
  slicer, consent gate, storage, export).
- **Smoke `scripts/smoke_s42.py`** (S4.1 style: uvicorn to populate over HTTP, then
  direct materialize/export). Checks:
  1. Ingest fixture candidate **A** → depth-eval; submit consented interview +
     coding rows for A (needs a `ledger_write` grant); grant A a `ledger_read`.
  2. Ingest a distinct candidate **B** (distinct email — identity resolution merges
     same-contact uploads) → depth-eval; **no** ledger rows, **no** grant.
  3. Materialize `core_v1` at `as_of=now`. **A**: consent features populated,
     `consent_state.allowed=True`, an audit row `feature.materialize allowed=True`.
     **B**: `ledger.*`/`reputation.*` **null** and in `missing`,
     `consent_state.allowed=False`, first-party features present, an audit row
     `allowed=False`.
  4. **Point-in-time proof:** materialize A at an `as_of` **before** A's ledger rows
     were submitted → ledger counts 0 / consent-features null (data that exists
     *now* is invisible at the earlier cut) — this is the no-leakage assertion.
  5. `export_view_csv` → assert header order == `view.members`, row count, A's
     consent cells populated, B's empty. `export_view_parquet` if pyarrow importable
     (skip-log otherwise).
  6. DPDP: erase A → A's `ml_feature_vectors` row cascaded away
     (`get_vector` → `None`).

## 4. Point-in-time correctness & no label leakage (the core guarantee)

- `as_of` threads through **every** axis: profile (versioned-extraction cutoff),
  report, ledger records/coding, consent validity, reputation decay. A vector
  computed at `as_of=T` reflects **only** data timestamped `<= T`, even when newer
  rows exist in the store at materialization wall-clock time.
- The row persists its `as_of`; **S4.4** will join outcome labels strictly *after*
  `as_of`, so features never see their own future. S4.2's job is to make the `as_of`
  cut honest — proven by the smoke's step 4 and a unit test that inserts data after
  `T` and shows a `T`-cut vector ignores it.

## 5. Testing (fully offline)

- **Slicer:** `profile_as_of` returns the version current at `as_of` and `None`
  before the first extraction; report/ledger cutoffs (regression-guard the existing
  behavior); consent validity evaluated at `as_of` (a grant revoked after `T` is
  still active at `T`).
- **Consent:** `has_any_active` (org-agnostic active/expired/revoked window +
  deterministic selection); `materialization_consent` allowed/withheld + both audit
  rows + `LookupError` on unknown candidate.
- **Materializer:** consent masking nulls exactly the `requires_consent` features
  and never first-party ones; `missing` updated; absent candidate → `None`;
  allowed path leaves values intact.
- **Store:** upsert idempotency (second materialize of the same cut updates, not
  duplicates — unique constraint holds); `get_vector`/`vectors_for_view`;
  **cascade** on `delete_candidate`; **drift guard** green for `0007`.
- **Export:** CSV wide shape, column order == `view.members`, null cells, masked
  consent cells; parquet guarded (assert `ParquetUnavailable` when pyarrow absent,
  else round-trip column names/order).
- **Smoke** `scripts/smoke_s42.py` as in §3.6.

Target test count: ~30 new (roughly S3.3/S3.4-sized), 507 → ~537, `pytest -q` green.

## 6. Scope boundaries (defer)

- **S4.3** — talent search/ranking API (filters + composite score) over the
  materialized table. S4.2 only *produces* the table + export.
- **S4.4** — training-set export (features ⋈ outcomes). S4.2 records the honest
  `as_of` seam that makes the future label-join leakage-free; it does not join
  labels.
- Incremental/streaming/scheduled materialization, change-data-capture, and a
  store-wide candidate enumerator beyond what the smoke needs — YAGNI.
- Postgres cutover + real embeddings — PI-8.
- Parquet typing beyond primitive dtypes; pyarrow in core deps — out (D3).

## 7. Risks & mitigations

- **Consent proxy too broad?** "Any active `ledger_read`" lets the platform's own
  ML use a candidate's cross-company features once the candidate has consented to
  *any* reader. This is deliberately the reputation-network opt-in, is fail-closed
  (no grant ⇒ null), advisory-only, and fully audited per candidate. If a stricter
  platform-specific consent purpose is ever wanted, it is an additive change (new
  purpose + gate) — not a rework of this table.
- **JSON `values` vs typed columns for S4.3 querying.** S4.3 may want indexed
  per-feature filters. The compact JSON row keeps S4.2 migration-free; S4.3 can add
  a projection/index (or a materialized wide view) when it knows its query shape,
  without changing how S4.2 writes. Documented as an S4.3 seam.
- **Idempotency vs history.** The unique key includes `as_of`, so distinct cuts
  coexist while a re-run of the *same* cut upserts. Two materializations at
  different wall-clock `now`s produce different `as_of`s (both retained) — expected
  for a feature store; not a bug.
```
