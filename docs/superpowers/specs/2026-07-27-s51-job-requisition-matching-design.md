# S5.1 — Job/requisition schema + role-conditioned match-ranking (design)

**Sprint:** PI-5 / S5.1 · **Date:** 2026-07-27 · **Status:** approved, pre-plan

Prereqs: PI-4 (S4.1 registry → S4.2 materialization / `ml_feature_vectors` /
`FeatureStore` → S4.3 pure ranking engine) merged; PI-3 ledger (orgs + org API
keys + `X-Org-Key` auth + `audit_log`) live. This is the **first demand-side
sprint**: it opens the org-facing matching surface that S4.3 deliberately left to
PI-5.

## 1. Goal

An org describes a role once as a **job requisition**; the platform compiles it
into a **role-conditioned ranking** over the already-materialized candidate pool
and returns an advisory, explainable shortlist. It **narrows and orders** — it
never auto-rejects, and a candidate is **never penalized for absent or
consent-withheld data** (a missing signal drops its term, not the candidate).

The whole matching computation reuses the S4.3 engine (`ranking.score`); S5.1's
only genuinely new math is one **job-relative skill-coverage** dimension, because
skills are a *set* (not a scalar feature) and coverage is defined only relative to
a specific requisition.

Non-goals (guardrails, YAGNI): **no comp-based matching** (S5.2 consumes the
stored band); no employer dashboard UI (S5.3); no semantic/embedding skill match
(needs the real vectorstore — PI-8); no candidate-facing "you were matched" notice
(PI-6 portal); no `max_years` over-qualification filter; no raw `FeatureFilter`
passthrough; no LLM.

## 2. Where it sits

```
JobRequisition (org-owned)                      ml_feature_vectors (S4.2, consent
   │  must/nice skills, min_years, min_degree,       already masked at materialize)
   │  max_notice, location, min_skill_coverage           │
   ▼                                                      ▼
compile ─▶ RankingSpec (soft terms) + one opt-in filter ─┐
   ▲                                                      ▼
candidate profiles (canonical skills,         ranking.score()  ─▶  MatchResult
   read point-in-time via profile_as_of)       (S4.3, reused)      (advisory)
   └──▶ skill_coverage + location_fit ──inject synthetic values──┘        │
                                                                          ▼
                                              audit_log: one match.surface row
                                              per returned candidate (CASCADE)
```

S4.3 already ranks a pool of `FeatureVector`s given `specs_by_name`. S5.1 sits one
layer up: it *builds* the `RankingSpec` from a requisition, *augments* each vector
with two job-relative synthetic values, then calls the same `score()`.

## 3. Design decisions (delegated to recommendation, user 2026-07-27)

- **D1 — Org plane (`X-Org-Key`).** Requisitions are org-owned; an org creates
  them and runs matches against the pool. This is the real "employers query"
  surface. Candidate-data disclosure to orgs is acceptable because the vectors are
  **already consent-masked at S4.2 materialization** (ledger/reputation features
  null without an active `ledger_read` grant), and every match is audited per
  surfaced candidate (D4). Requisition CRUD and match are org-scoped: an org only
  sees and matches from its own requisitions (cross-org → 404).
- **D2 — Compile-to-ranking + job-relative skill-coverage.** The requisition
  compiles into a `RankingSpec` of **soft terms** over existing scalar features
  plus a synthetic `match.skill_coverage` term computed from canonical skills.
  Reuse of `ranking.score()` gives coverage/renormalization/`Contribution`
  explainability for free — no new scoring math beyond coverage itself.
- **D3 — Comp band is metadata only.** `comp_band` is stored on the requisition
  as advisory structure and is **not a matching term** in S5.1 (matching on comp
  needs candidate comp expectations we do not collect; comp intelligence is S5.2).
  Carrying the field now locks the schema so S5.2 needs **no follow-up migration**
  — the S3.3 "considered field set" pattern.
- **D4 — Audit every match, no new consent gate.** A match writes one
  `match.surface` audit row per **returned** candidate (candidate-linked,
  CASCADE), mirroring the ledger's "audit every read attempt". No new
  `ConsentPurpose`: the pool is already consent-masked, and search/match over the
  pre-trusted pool is the product's core function; a per-candidate discoverability
  gate would break the "employers pull from a pool" premise and needs candidate
  consent capture (PI-6).

## 4. Components

New package `app/matching/` (demand side), layered like `app/ledger/`. Units 4.1
and 4.2 are **pure** (no I/O, no store, no wall clock — the
`fabrication/risk.py` / `features/ranking.py` pattern).

### 4.1 Contracts — `app/matching/schema.py`

Pydantic models + StrEnums, serializable, no callables:

- `RequisitionStatus` (StrEnum): `draft, open, closed`.
- `CompBand{ currency: str = "INR", ctc_min?: float, ctc_max?: float,
  variable_max?: float, notes?: str }` — advisory; validated `ctc_max >= ctc_min`
  when both present; **not consumed by matching in S5.1**.
- `MatchWeights{ skill_coverage?, years?, degree?, notice?, location? : float>0 }`
  — optional per-term overrides; each falls back to its `match_*` config default.
- `JobRequisition`:
  ```
  id, org_id, title: str, status: RequisitionStatus = open,
  must_have_skills: tuple[str,...]  = (),   # canonical keys (normalized at create)
  nice_to_have_skills: tuple[str,...] = (),
  min_years_experience?: float (ge 0),
  min_degree_level?: str  (in candidate.highest_degree_level categories),
  max_notice_days?: int (ge 0),
  location_tiers?: tuple[str,...],          # subset of {metro, tier_2}
  remote: bool = False,                     # remote ⇒ location term omitted
  min_skill_coverage?: float [0,1],         # the one opt-in hard gate
  comp_band?: CompBand,
  weights?: MatchWeights,
  created_at, updated_at
  ```
  Validated: at least one of `must_have_skills`/`nice_to_have_skills` non-empty;
  `min_degree_level` ∈ the ordinal's categories; `location_tiers` ⊆
  `{metro, tier_2}`.
- `SkillMatch{ matched: tuple[str,...], missing_must_have: tuple[str,...],
  matched_nice_to_have: tuple[str,...], coverage: float }` — per-candidate skill
  explanation.
- `MatchedCandidate{ candidate_id, score: float, coverage: float,
  skill: SkillMatch, contributions: tuple[Contribution,...], missing:
  tuple[str,...] }` — wraps the S4.3 `RankedCandidate` + the skill detail.
- `MatchResult{ advisory: bool = True, requisition_id, as_of?, view_name,
  view_version, pool_size: int, filtered_size: int,
  ranked: tuple[MatchedCandidate,...] }`.

Reuses `Contribution` from `app/features/ranking_schema.py` (no duplication).

### 4.2 Pure engine — `app/matching/match.py`

No I/O. Inputs are already-loaded: `FeatureVector`s, a
`profiles_by_candidate: dict[str, CandidateProfile]` (canonical skills), a
`specs_by_name`, and `Settings` (for default weights).

- **`_SYNTHETIC_SPECS`** — two module-level `FeatureSpec`s not in the global
  registry, passed into `specs_by_name` at match time:
  - `match.skill_coverage` — NUMERIC, source CANDIDATE, `valid_range=(0.0, 1.0)`.
  - `match.location_fit` — NUMERIC, source CANDIDATE, `valid_range=(0.0, 1.0)`.
  (`match.` is a legal namespace under the feature-name regex; CANDIDATE source ⇒
  `requires_consent=False`, satisfying `FeatureSpec.__post_init__`.)
- **`skill_coverage(requisition, canonical_skills: set[str], settings) ->
  SkillMatch`** — pure. `must_frac` = |have ∩ must| / |must| (1.0 if no
  must-haves); `nice_frac` = |have ∩ nice| / |nice| (0.0 if no nice-to-haves).
  `coverage = must_frac` when there are must-haves, blended with the nice-to-have
  signal by `match_nice_to_have_fraction` (e.g.
  `must_frac*(1-f) + nice_frac*f` when both sets exist; pure nice-to-have reqs use
  `nice_frac`). Returns the matched/missing lists for explainability. No profile
  ⇒ caller passes `None` ⇒ coverage term omitted for that candidate.
- **`location_fit(requisition, location_tier: str|None) -> float | None`** —
  `None` if the requisition is remote or sets no `location_tiers`, or the
  candidate tier is unknown/None (term drops, no penalty); else `1.0` if the
  candidate tier ∈ target tiers, `0.0` otherwise.
- **`compile_ranking(requisition, settings) -> RankingSpec`** — builds terms,
  each present only when its requisition field is set:
  | Term | Direction | Weight (default) | Gated on |
  |---|---|---|---|
  | `match.skill_coverage` | higher | `match_skill_weight` (dominant) | always |
  | `candidate.years_experience` | higher | `match_years_weight` | `min_years_experience` |
  | `candidate.highest_degree_level` | higher | `match_degree_weight` | `min_degree_level` |
  | `candidate.notice_period_days` | **lower** | `match_notice_weight` | `max_notice_days` |
  | `match.location_fit` | higher | `match_location_weight` | `location_tiers` & !remote |
  Per-term `weights` overrides win over the `match_*` defaults.
- **`compile_filters(requisition) -> list[FeatureFilter]`** — `[]` unless
  `min_skill_coverage` is set, in which case one `FeatureFilter("match.skill_coverage",
  gte, min_skill_coverage)`. This is the **only** hard gate; below-floor
  candidates are dropped from *this requisition's* shortlist (not rejected
  globally). `min_years_experience`/`min_degree_level`/`max_notice_days` stay
  **soft** in v0: they *select* which scalar dimensions enter the ranking (term
  inclusion), and within each, scoring is monotonic (more experience, higher
  degree, shorter notice = better). The threshold **value itself is not a cutoff**
  — no candidate is dropped for falling below it, and two requisitions differing
  only in `min_years` (2 vs 8) rank the same pool identically on the experience
  term. Per-value threshold-fit curves and hard experience floors are a
  documented v1 refinement.
- **`match(requisition, vectors, profiles_by_candidate, specs_by_name, settings)
  -> list[MatchedCandidate]`** — orchestration, still pure:
  1. per candidate: compute `SkillMatch` + `location_fit`; build an **augmented
     copy** of the vector with `match.skill_coverage` / `match.location_fit`
     injected into `values` (None when the term drops).
  2. `specs = {**specs_by_name, **_SYNTHETIC_SPECS}`.
  3. `apply_filters(augmented, compile_filters(req), specs)`.
  4. `ranked = score(filtered, compile_ranking(req, settings), specs)`.
  5. zip each `RankedCandidate` back with its `SkillMatch` → `MatchedCandidate`.

### 4.3 ORM + migration — `app/matching/models.py`, `0008_job_requisitions`

`JobRequisitionRow` (Postgres-shaped on SQLite):
```
id: str pk (uuid)
org_id: FK organizations.id  ondelete=CASCADE, index   # dies with its org
title: Text
status: String(16)                                      # RequisitionStatus
must_have_skills: JSON (list[str])                       # canonical
nice_to_have_skills: JSON (list[str])
min_years_experience: Float  nullable
min_degree_level: String(16) nullable
max_notice_days: Integer     nullable
location_tiers: JSON nullable
remote: Boolean default False
min_skill_coverage: Float nullable
comp_band: JSON nullable                                 # serialized CompBand
weights: JSON nullable
created_at, updated_at: DateTime(tz)
```
**Not candidate-linked** — a requisition is org data, so it **survives candidate
erasure** (correct) and CASCADEs only on its org. Migration `0008` mirrors the ORM
exactly; the metadata-wide **drift/index/FK-ondelete/nullability guards** are
extended to it (the S3.3/S4.2 pattern). Match disclosure reuses the existing
`audit_log` table — **no new audit table**.

### 4.4 Store — `app/matching/store.py` (`JobStore`)

Shares the candidates/ledger session factory (so `organizations`, `candidates`,
`ml_feature_vectors`, `audit_log` are one DB). Constructed via
`build_job_store(...)`; injected as `Services.jobs` the way `ledger`/`features`
are (import-cycle-safe: `TYPE_CHECKING` annotation + function-local build, per
S4.3).

- **`create_requisition(org_id, payload) -> JobRequisition`** — normalizes
  free-text `must/nice` skills to canonical keys via
  `app/candidates/normalize/skills.py`, persists, audits `requisition.create`
  (actor org, `candidate_id=None` — org-only, survives erasure).
- **`get_requisition(org_id, req_id)`** / **`list_requisitions(org_id)`** —
  org-scoped; foreign `req_id` ⇒ `None` (→ 404).
- **`update_requisition(org_id, req_id, patch)`** — status + editable fields
  (re-normalizes skills if changed); audits `requisition.update`.
- **`run_match(org_id, req_id, *, as_of=None, limit) -> MatchResult`** — the
  orchestrator that does the I/O the pure engine cannot:
  1. load the requisition (404 if not owned);
  2. resolve `specs_by_name` for the compiled terms' scalar features from the
     registry;
  3. `as_of = as_of or FeatureStore.latest_as_of(view)`; load
     `vectors_for_view(view, as_of)` (empty/None ⇒ 422 at the endpoint);
  4. for each pooled candidate, `CandidateStore.profile_as_of(cid, as_of)` →
     canonical skill set + location tier (**point-in-time**, consistent with the
     vector cut; missing profile ⇒ coverage/location drop, no penalty);
  5. call the pure `match(...)`, truncate to `limit`;
  6. write one `match.surface` `AuditLogRow` per **returned** candidate
     (`actor_type="org"`, `actor_id=org_id`, `action="match.surface"`,
     `entity_type="requisition"`, `entity_id=req_id`, `candidate_id=cid`,
     `details={rank, score}`) — bounded by `limit`, candidate-linked ⇒ CASCADE.

### 4.5 HTTP — org plane (`app/api/routes.py`, `org_router`)

Behind `X-Org-Key → org` (`require_org`, the S3.2 dependency):

- `POST /jobs` → `JobRequisition` (201). 422 on invalid payload (Pydantic).
- `GET /jobs` → org's requisitions.
- `GET /jobs/{id}` → 404 if not owned.
- `PATCH /jobs/{id}` → update status/fields; 404 if not owned.
- `POST /jobs/{id}/match` → `MatchResult{advisory=True}`. 404 if not owned; **422**
  if the pool is empty/unmaterialized for the requested `as_of`/view (nothing to
  rank); **400** on a malformed match request (e.g. bad `as_of`); **401** without a
  valid org key. The compiled ranking is never empty — `match.skill_coverage` is
  always a term and the schema forbids a no-skills requisition. Optional body:
  `{ as_of?, limit? }` (`limit` default `match_default_limit`).

## 5. Consent, point-in-time, DPDP

- **Consent:** not re-applied at match time. Consent-tagged features were masked to
  null at S4.2 materialization; a withheld feature is already absent and simply
  drops out of scoring (never a penalty). S5.1 adds **no new `ConsentPurpose`** and
  **no per-candidate match gate** (D4). Skills read from the profile are
  first-party candidate data (no consent tag), consistent with S4.3's admin read.
- **Point-in-time:** the match uses one `as_of` for *both* the vector cut and the
  profile read (`profile_as_of`), so skill coverage and scalar features describe
  the same instant — no leakage of later data into a match dated earlier.
- **DPDP:** `job_requisitions` is org-owned (not candidate-linked) ⇒ candidate
  erasure does not touch requisitions (correct); it CASCADEs on org deletion. The
  candidate-facing side effect — `match.surface` audit rows — is candidate-linked
  and CASCADEs on erasure. An erased candidate is absent from the vector pool, so
  a re-run simply omits them. No new candidate table ⇒ no new erasure path beyond
  the audit rows already covered by the candidate CASCADE.

## 6. Config

New `match_*` knobs in `config.yaml` + `Settings` (all `DEE_*`-overridable):

- `match_default_limit` (int, default `25`, `ge=1`).
- `match_skill_weight` (float, default `3.0`) — dominant term.
- `match_years_weight` / `match_degree_weight` / `match_notice_weight` /
  `match_location_weight` (float, default `1.0`).
- `match_nice_to_have_fraction` (float, default `0.3`, `0 <= x <= 1`) — nice-to-have
  share of skill coverage when both skill sets are present.

View selection reuses `feat_default_view` (no new view knob).

## 7. Testing (fully offline; no LLM in S5.1)

Unit — pure `match.py`:
- `skill_coverage`: full/partial/zero must-have coverage; nice-to-have blend at
  `match_nice_to_have_fraction`; pure-must and pure-nice requisitions; empty
  candidate skills ⇒ coverage 0; the matched/missing lists.
- `location_fit`: in-tier ⇒ 1.0, out-of-tier ⇒ 0.0, remote/no-tiers/unknown ⇒
  None (term drops).
- `compile_ranking`: only set fields yield terms; notice is `lower_better`;
  `weights` overrides beat defaults.
- `compile_filters`: `min_skill_coverage` ⇒ one `gte` filter, else `[]`.
- `match`: injection + reuse of `score`; a candidate missing skills/location is
  ranked (not dropped) and **not penalized** vs a present-but-neutral peer; the
  `min_skill_coverage` gate drops below-floor candidates; deterministic order.
- Contracts: requisition needs ≥1 skill; `min_degree_level` ∈ categories;
  `location_tiers` ⊆ {metro, tier_2}; `CompBand` ctc bounds.

Store — `JobStore`:
- requisition CRUD org-scoping (foreign `req_id` ⇒ None/404); skill normalization
  at create; `run_match` ranks a small pool by role fit; `match.surface` audit rows
  written **per returned candidate** and bounded by `limit`; DPDP erasure sweeps a
  matched candidate's `match.surface` rows; a requisition **survives** candidate
  erasure and dies with its org.
- Migration drift guard passes for `job_requisitions`.

Endpoint — org plane:
- `POST/GET/PATCH /jobs` happy paths; cross-org `GET/PATCH/match` ⇒ 404;
  `POST /jobs/{id}/match` ⇒ `MatchResult{advisory=True}` ranked with skill detail
  + contributions; empty/unmaterialized pool ⇒ 422; missing/invalid org key ⇒ 401;
  invalid payload ⇒ 422.

Smoke — `scripts/smoke_s51.py` (uvicorn + HTTP): create org + key → ingest ≥3
candidates spanning skills/experience/notice → materialize + persist the pool →
`POST /jobs` (must-have skills + `min_years` + `max_notice`) → `POST
/jobs/{id}/match`: assert the strong-fit candidate ranks first with visible skill
coverage and notice contribution, a weak-skill candidate ranks lower but still
appears (advisory), `min_skill_coverage` gates as expected; then DPDP-erase a
ranked candidate and re-match → they drop and their `match.surface` audit rows are
swept. Exit 0.

Target: 584 → ~625 tests.

## 8. Deliverables

- `app/matching/schema.py` (contracts) · `app/matching/match.py` (pure engine) ·
  `app/matching/models.py` (`JobRequisitionRow`) · `app/matching/store.py`
  (`JobStore` + `build_job_store`).
- Alembic `0008_job_requisitions` (+ drift/index/FK/nullability guards extended).
- `Services.jobs` wiring; `POST/GET/PATCH /jobs` + `POST /jobs/{id}/match` on
  `org_router`.
- `match_*` knobs in `config.yaml` + `Settings`.
- New `MATCHING.md` (peer of `LEDGER.md`/`FEATURES.md`/`FABRICATION.md`) — demand
  side, requisition schema, compile rules, disclosure-audit + DPDP posture.
- Tests + `scripts/smoke_s51.py`.

## 9. Seams to S5.2 / S5.3

- **S5.2 (comp intelligence):** consumes the stored `comp_band` (no migration) and
  the ledger's observed offers; may later add a comp-fit matching term — the
  `MatchWeights`/`compile_ranking` shape leaves room for one more term.
- **S5.3 (employer dashboard):** a thin read-only surface over `GET /jobs` +
  `POST /jobs/{id}/match` + linked `Report`s; S5.1 keeps the API the primary
  contract so the dashboard adds no new server logic.
