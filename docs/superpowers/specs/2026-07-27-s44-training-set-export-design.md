# S4.4 — Training-set Export (features ⋈ outcomes) (design)

**Sprint:** PI-4 / S4.4 (final PI-4 sprint) · **Date:** 2026-07-27 · **Status:**
approved, pre-plan

Prereqs: S4.1 (feature registry), S4.2 (materialization → `ml_feature_vectors`,
`FeatureStore`, point-in-time slicer), S4.3 (ranking/serve) are merged. This
sprint adds the **label-join / training-set export** layer on top; it introduces
**no new table, no migration, no HTTP, no LLM, and no new config knob**. It
mirrors S4.3's read-side footprint.

## 1. Goal

Produce a **point-in-time-correct, leakage-free training set**: join each stored
`ml_feature_vectors` row (a candidate's features at `as_of=T`, already
consent-masked at S4.2) to a **ground-truth label derived only from outcomes that
strictly post-date T**. The result is a set of `TrainingExample`s (features +
label block) and a wide CSV/parquet export a model trainer can consume directly.

The one non-negotiable is the **no-leakage guarantee**: features are computed from
data timestamped `≤ T`; the label is computed from ledger events timestamped
`> T`. The strict inequality is the seam — a record *at exactly* `T` fed the
features and therefore can never become a label.

Non-goals (guardrails, YAGNI): no model training/evaluation (this exports the
data, nothing learns), no persisted training table, no bounded label horizon knob
(we record `lag_days` so a modeler windows/censors themselves), no flywheel
outcome mining (its `outcome` field is a permanent `None` placeholder today — see
§3 D1), no HTTP endpoint, no new migration.

## 2. Where it sits

S4.2 persists one compact row per `(candidate_id, as_of, view_name, view_version)`
in `ml_feature_vectors` — feature `values` (consent-tagged ones already masked to
null), `missing`, and the `consent_state` decision that governed them — and
exposes `FeatureStore.vectors_for_view(...)`. The ledger holds the outcomes:
`interview_records` (typed `outcome` at `interviewed_at`) and
`coding_round_results` (typed `percentile`/`score` at `taken_at`), read raw via
`LedgerStore.records_for_candidate` / `coding_rounds_for_candidate`.

```
ml_feature_vectors ──vectors_for_view──▶  build_training_set  ──▶ TrainingExample[]
   (features @ T,                          per vector:               (features + label)
    consent_state)                         · reuse consent_state         │
                                           · read ledger (if allowed)    ▼
LedgerStore (interview_records,  ────────▶ · build_label(> T)      export_training_csv/parquet
             coding_round_results)         · audit training.label   (wide pivot + label cols)
```

## 3. Design decisions (taken with user, 2026-07-27 — all recommendations accepted)

- **D1 — Ledger-only label source.** Labels derive from `interview_records.outcome`
  (the hire signal) and `coding_round_results` (the coding signal), both
  timestamped and queryable. The flywheel's `outcome` field is written `None` on
  every record today (`app/graph/nodes/report.py`, "closed later by human/hiring
  signal") and the flywheel is an append-only JSONL log, not a point-in-time
  store — there is nothing to join. Flywheel-fed report outcomes remain a future
  source (they need an outcome-feedback API first; out of S4.4 scope).
- **D2 — Compact, censoring-aware label block.** Each example carries `hired`
  (bool | null), `outcome` (terminal-best interview outcome | null),
  `coding_best_percentile` (float | null), `event_at` (datetime | null),
  `lag_days` (float | null), `observed` (bool), `withheld` (bool). `observed`
  vs `hired=False` distinguishes a **right-censored** example (no post-cut outcome
  yet) from a real negative — critical for honest training.
- **D3 — Reuse the S4.2 consent decision, and audit the join.** The label is
  derived from the same consent-gated cross-company records S4.2 masks, so it
  inherits the same gate. The training layer reads each vector's stored
  `consent_state`: withheld ⇒ the label is withheld (all fields null,
  `withheld=True`) and **no ledger read happens**; allowed ⇒ read + label. Either
  way it writes a `training.label` audit row (allowed/withheld, at `as_of`) —
  observability without a new gate, consistent with S4.2's `feature.materialize`.
- **D4 — Library + script deliverable (no HTTP, no table).** Training-set export
  is an offline/batch artifact best produced as a file by a script. A pure join
  module + export functions + a smoke script keeps DPDP clean (labels recompute
  from ledger rows that already CASCADE on erasure) and matches S4.2, where
  materialization + export were script concerns with no endpoint.

## 4. Components

Two new units + a light refactor of `export.py`. The label logic is pure (no I/O,
no store, no wall clock), mirroring `app/fabrication/risk.py` and
`app/ledger/reputation.py`; the orchestrator is the only store-touching piece,
mirroring `app/features/materialize.py`.

### 4.1 Contracts — `app/features/training_schema.py`

Pydantic models, all serializable, no callables:

- `TrainingLabel`:
  - `hired: Optional[bool]` — positive terminal outcome (`outcome ∈ {hired,
    offer}`) among post-cut interview records; `None` when `observed` is False or
    `withheld` is True.
  - `outcome: Optional[str]` — the terminal-best `InterviewOutcome` value (§4.2
    ordering); `None` when none/withheld.
  - `coding_best_percentile: Optional[float]` — max `percentile` among post-cut
    coding rounds that carry one; `None` otherwise.
  - `event_at: Optional[datetime]` — `interviewed_at` of the earliest post-cut
    record carrying the terminal-best `outcome`; `None` when none.
  - `lag_days: Optional[float]` — `(event_at − as_of)` in days (float); `None`
    when `event_at` is `None`.
  - `observed: bool` — at least one post-cut **non-withdrawn** interview record
    exists (the hire label's basis). Independent of `coding_best_percentile`.
  - `withheld: bool` — the label was withheld because the vector's consent was not
    active at `as_of`. When True, every value field is `None` and `observed` is
    False (we did not look).
- `TrainingExample`:
  - `vector: FeatureVector` — the S4.2 feature vector (carries `candidate_id`,
    `as_of`, `view_name`, `view_version`, `values`, `missing`).
  - `label: TrainingLabel`.

### 4.2 Pure label logic — `app/features/training.py` (pure part)

- **`_TERMINAL_ORDER`** — code-constant ranking of `InterviewOutcome` for
  terminal-best selection: `hired(5) > offer(4) > advanced(3) > rejected(2) >
  no_show(1)`; **`withdrawn` is excluded entirely** (non-signal — mirrors S3.4
  reputation, which also drops `withdrawn`). `hired`-positive set = `{hired,
  offer}`.
- **`build_label(*, as_of, interview_records, coding_rounds, consent_allowed) ->
  TrainingLabel`** — pure, no I/O/clock:
  - If `consent_allowed` is False → return the **withheld** label (all null,
    `observed=False`, `withheld=True`). (Callers already avoid reading the ledger
    in this case, but the function is defensively self-contained.)
  - `post = [r for r in interview_records if as_utc(r.interviewed_at) > as_utc(as_of)
    and r.outcome != withdrawn]` — **strict `>`** is the no-leakage boundary.
  - `observed = bool(post)`. If not observed → `hired=None, outcome=None,
    event_at=None, lag_days=None` (right-censored), but still compute
    `coding_best_percentile` from post-cut coding rounds.
  - Terminal-best `outcome` = the max-ranked outcome across `post`; `event_at` =
    the **earliest** `interviewed_at` among records carrying that outcome;
    `lag_days = (event_at − as_of).total_seconds() / 86400`.
  - `hired = outcome in {hired, offer}`.
  - `coding_best_percentile = max(percentile for c in coding_rounds if
    as_utc(c.taken_at) > as_utc(as_of) and c.percentile is not None)` or `None`.
  - `withheld=False`.

  Timezone: `as_of` (from the stored vector) is aware-UTC; `interviewed_at` /
  `taken_at` come back aware-UTC from the ledger converters. `as_utc` on both
  sides keeps the strict comparison total and tz-safe.

### 4.3 Orchestrator — `app/features/training.py` (store-touching part)

- **`build_training_example(mv, *, interview_records, coding_rounds) ->
  TrainingExample`** — combine one `MaterializedVector` with the candidate's
  already-fetched ledger rows: read consent from `mv.consent_state.get("allowed")`,
  call `build_label(as_of=mv.vector.as_of, …)`, wrap in a `TrainingExample`.
- **`build_training_set(mvs, *, ledger_store, audit=True) ->
  list[TrainingExample]`** — for each `MaterializedVector`:
  1. `allowed = bool(mv.consent_state.get("allowed"))`.
  2. If `allowed`: `irs = ledger_store.records_for_candidate(cid)`;
     `crs = ledger_store.coding_rounds_for_candidate(cid)` (raw reads). Else
     `irs, crs = [], []` (**no ledger read for a withheld candidate**).
  3. If `audit`: `ledger_store.audit_training_label(cid, allowed=allowed,
     as_of=mv.vector.as_of)`.
  4. `examples.append(build_training_example(mv, interview_records=irs,
     coding_rounds=crs))`.

  Purity split mirrors `materialize.py`: `build_label` is the pure core;
  `build_training_set` is the thin I/O + audit orchestrator.

### 4.4 New store method — `LedgerStore.audit_training_label`

`audit_training_label(self, candidate_id, *, allowed: bool, as_of: datetime) ->
None`. Writes one `audit_log` row in its own transaction: `actor_type="system"`,
`actor_id="platform"`, `action="training.label"`, `entity_type="candidate"`,
`entity_id=candidate_id`, `candidate_id=candidate_id`, `details={"allowed":
allowed, "as_of": as_utc(as_of).isoformat()}`. It **audits a reused decision** —
it does not recompute consent (that was decided and audited at S4.2
materialization; reusing the stored flag is the single source of truth, D3). The
candidate-linked audit row CASCADE-deletes on DPDP erasure like every other. It
never raises for a withheld candidate (records the withhold).

### 4.5 Export refactor + training export — `app/features/export.py`

Extract two small **public** helpers so the S4.2 exporters and the new training
exporters share one pivot (a targeted cleanup of code we're extending, not a
rewrite):

- `feature_columns(view) -> list[str]` — the `[name for name, _ in view.members]`
  feature-column order (currently inline in `_columns`).
- `vector_cells(vector, view, null_token) -> list` — the fixed + feature cells for
  one `FeatureVector` (today's `_row_cells` reads only `mv.vector`; retarget it to
  take the `FeatureVector`). Existing `export_view_csv/parquet` keep working via
  these helpers — behavior unchanged, proven by the existing S4.2 export tests.

Then add, in `export.py`:

- **`_LABEL_COLUMNS`** = `("label_hired", "label_outcome",
  "label_coding_best_percentile", "label_event_at", "label_lag_days",
  "label_observed", "label_withheld")` — fixed order, appended **after** the
  feature columns.
- **`export_training_csv(examples, *, view, path, null_token="")`** — header =
  `feature_columns(view)`-based fixed+feature columns **+** `_LABEL_COLUMNS`; one
  row per `TrainingExample` = `vector_cells(ex.vector, …)` **+** label cells
  (`event_at` → ISO string, bools → the writer's native rendering, `None` →
  `null_token`). Values are already consent-masked/withheld, so a file can't leak.
- **`export_training_parquet(examples, *, view, registry, path)`** — the guarded
  parquet variant (raises `ParquetUnavailable` when `pyarrow` is absent). Label
  column arrow types: `label_hired`/`label_observed`/`label_withheld` → `bool_`
  (nullable), `label_outcome` → `string`, `label_coding_best_percentile` /
  `label_lag_days` → `float64`, `label_event_at` → `string` (ISO).

## 5. Consent, point-in-time, DPDP

- **Consent:** the label inherits the S4.2 decision (D3). A withheld candidate's
  `ledger.*` features are already null in the row *and* its label is withheld and
  unread — the two stay consistent. No new gate, no new disclosure surface. Every
  label join (allowed or withheld) is audited `training.label`, so platform-side
  use of gated data stays observable (the S3.x "surveillance is itself
  observable" principle).
- **Point-in-time / no leakage:** features are the S4.2 point-in-time cut (`≤ T`);
  the label reads **only** ledger events strictly `> T`. A boundary test asserts a
  record at exactly `T` does not label. This is the whole reason PI-4 carried
  `as_of` as a first-class seam since S4.1.
- **DPDP:** no new candidate-linked table ⇒ no new erasure path. Vectors and
  ledger rows both already CASCADE on candidate erasure; the new `training.label`
  audit rows are candidate-linked and CASCADE too. An erased candidate simply
  produces no example.

## 6. Config

**None.** The view defaults to `settings.feat_default_view` (`core_v1`) at the
export-callsite/smoke; label horizon is unbounded-with-`lag_days` (no knob). No
numeric knobs — the terminal-outcome ordering and the hire-positive set are code
constants (a reviewed schema decision, like the ledger taxonomies), not tunables.

## 7. Testing (fully offline)

Unit — pure `build_label`:
- **No-leakage boundary:** a record at exactly `as_of` is excluded; one at
  `as_of + ε` is included. Asserted directly (the sprint's headline invariant).
- **Terminal-best selection:** ordering `hired>offer>advanced>rejected>no_show`;
  `withdrawn` excluded; `event_at` = earliest record carrying the winning outcome;
  `lag_days` math.
- **Hire-positive set:** `hired=True` for terminal `{hired, offer}`, `False` for
  `{advanced, rejected, no_show}`.
- **Censoring:** no post-cut record ⇒ `observed=False`, `hired=None`,
  `outcome=None`, `event_at=None` (not a false negative); all post-cut records
  `withdrawn` ⇒ `observed=False`.
- **Coding:** `coding_best_percentile` = max post-cut percentile; `None` when no
  post-cut round or none carries a percentile; independent of `observed`.
- **Consent-withheld:** `consent_allowed=False` ⇒ fully-null withheld label even
  when records are passed.

Unit — orchestrator + store:
- `build_training_set` over a mix (consented-with-outcome, consented-censored,
  withheld): correct labels; **no ledger read for the withheld candidate**;
  `audit_training_label` writes `training.label` (allowed for the first two,
  withheld for the third), rows CASCADE-swept on erasure.

Export:
- Labeled CSV header = fixed + feature (`view.members` order) + `_LABEL_COLUMNS`;
  a withheld/censored row renders null cells; `export_view_csv` regression stays
  green (helper extraction is behavior-preserving); guarded parquet
  (`ParquetUnavailable` when pyarrow absent, correct types when present).

Smoke — `scripts/smoke_s44.py` (uvicorn + HTTP populate → direct materialize →
build + export):
- **A (consented, labeled):** ingest + depth-eval, grant `ledger_read`, submit
  interview records **both ≤ T** (feed `ledger.*` features) **and > T** (a `hired`
  outcome) plus a **> T** coding round with a percentile. Materialize at `as_of=T`,
  build the training set: assert `hired=True`, `observed=True`, `lag_days>0`,
  `coding_best_percentile` set, and prove the ≤ T rows fed features but **did not**
  leak into the label (a ≤ T `hired` would still not label — only > T does).
- **B (consented, censored):** no post-cut outcome ⇒ `observed=False`,
  `hired=None`.
- **C (unconsented):** `withheld=True`, `ledger.*` features already null, and a
  `training.label` **withheld** audit row present.
- Export labeled CSV (assert header + a labeled row), guarded parquet (skipped
  when pyarrow absent). Exit 0. The run also exercises the live LLM ingestion path
  when a key is present (key-less deterministic floor otherwise).

Target: 564 → ~595 tests.

## 8. Deliverables

- `app/features/training_schema.py` (`TrainingLabel`, `TrainingExample`)
- `app/features/training.py` (`build_label` pure + `build_training_example` +
  `build_training_set` orchestrator; `_TERMINAL_ORDER`)
- `LedgerStore.audit_training_label(...)`
- `export.py` refactor (`feature_columns`, `vector_cells` public helpers) +
  `export_training_csv` / `export_training_parquet` + `_LABEL_COLUMNS`
- FEATURES.md S4.4 section
- Tests + `scripts/smoke_s44.py`

## 9. PI-4 close-out

S4.4 is the final PI-4 sprint. On merge, PI-4 (ML feature store & ranking) is
complete: registry (S4.1) → point-in-time materialization + export (S4.2) →
ranking/serve (S4.3) → leakage-free training-set export (S4.4). The next PI is
shaped in `docs/superpowers/specs/2026-07-26-veritas-vision-gap-analysis.md`
(PI-5 demand side); it never overrides the ROADMAP's "Next action".
