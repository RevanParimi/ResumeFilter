# MATCHING.md — demand side: job requisitions + role-conditioned matching (PI-5)

The demand-side subsystem (`app/matching/`). An organization describes a role as
a **job requisition**; the platform compiles it into a **role-conditioned
ranking** over the already-materialized candidate pool (PI-4 `ml_feature_vectors`)
and returns an advisory, explainable shortlist. Peer of `LEDGER.md` /
`FEATURES.md` / `FABRICATION.md`.

**Advisory, always.** Matching narrows and orders — it never auto-rejects, and a
missing or consent-withheld value **drops its term, never the candidate**.

## S5.1 — job requisition schema + match-ranking

### Layering (mirrors `app/ledger/`)

| Unit | File | Role |
|---|---|---|
| Contracts | `app/matching/schema.py` | Pydantic models + StrEnums (pure) |
| Pure engine | `app/matching/match.py` | compile + skill/location + `match` (no I/O, no clock) |
| ORM | `app/matching/models.py` | `JobRequisitionRow` |
| Store | `app/matching/store.py` | `JobStore`: CRUD + `run_match` orchestrator |
| HTTP | `app/api/routes.py` (`org_router`) | `POST/GET/PATCH /jobs`, `POST /jobs/{id}/match` |

### The requisition (`JobRequisitionInput` → stored `JobRequisition`)

`title`, `status` (`draft|open|closed`), and role criteria — all optional except
that **at least one skill** (must-have or nice-to-have) is required:

- `must_have_skills` / `nice_to_have_skills` — free-text at the API, **normalized
  to canonical S1.4 taxonomy keys at create time** (`normalize_skill`; unknown
  skills fall back to `norm_key` so the ask is recorded even if unmatched).
- `min_years_experience`, `min_degree_level` (an ordinal degree level),
  `max_notice_days`, `location_tiers` (⊆ `{metro, tier_2}`) + `remote`.
- `min_skill_coverage` ∈ [0,1] — the **one opt-in hard gate**.
- `comp_band` — **advisory metadata only, not matched on** (S5.2 consumes it;
  carried now so S5.2 needs no migration — the S3.3 "considered field set" pattern).
- `weights` — optional per-term overrides of the `match_*` defaults.

### Compile rules (`compile_ranking` / `compile_filters`)

A requisition compiles into an S4.3 `RankingSpec` of **soft terms**; the engine
computes two **job-relative synthetic values** (`match.skill_coverage`,
`match.location_fit`), injects them into a copy of each `FeatureVector`, and
reuses `app/features/ranking.py`'s `score()` — so renormalization, `coverage`,
and per-feature `Contribution` explainability come for free.

| Term | Direction | Default weight | Present when |
|---|---|---|---|
| `match.skill_coverage` (dominant) | higher | `match_skill_weight` (3.0) | always |
| `candidate.years_experience` | higher | `match_years_weight` (1.0) | `min_years_experience` set |
| `candidate.highest_degree_level` | higher | `match_degree_weight` (1.0) | `min_degree_level` set |
| `candidate.notice_period_days` | **lower** | `match_notice_weight` (1.0) | `max_notice_days` set |
| `match.location_fit` | higher | `match_location_weight` (1.0) | `location_tiers` set & not remote |

**Skill coverage** = fraction of must-haves the candidate has, blended with the
nice-to-have fraction by `match_nice_to_have_fraction` (0.3) when both sets exist;
computed from the candidate's canonical skills read **point-in-time**
(`profile_as_of`) at the match `as_of`. **Location fit** = 1.0 in-tier / 0.0
out-of-tier / `None` (term drops) when remote, no target tiers, or unknown tier.

**The `min_*`/`max_notice` fields are soft in v0:** they *select* which scalar
dimensions enter the ranking; within each, scoring is monotonic (more experience,
higher degree, shorter notice = better). The threshold **value is not a cutoff** —
no candidate is dropped for falling below it. The **only** hard gate is
`min_skill_coverage`, which compiles to one `FeatureFilter` on
`match.skill_coverage`. (Per-value threshold curves + hard experience floors are a
v1 refinement.)

### Plane, consent, DPDP

- **Org plane (`X-Org-Key`).** Requisitions are org-owned; CRUD and match are
  org-scoped (cross-org access → 404). This is the "employers query" surface.
- **No new consent gate.** The pool's consent-tagged (`ledger.*`/`reputation.*`)
  features were **masked to null at S4.2 materialization**; a withheld feature is
  already absent and simply drops out of scoring. Skills read from the profile are
  first-party candidate data. `ConsentPurpose` is unchanged.
- **Disclosure audit.** Each **returned** candidate is audited as one
  `match.surface` row in the shared `audit_log` (`actor=org`, candidate-linked,
  CASCADE) — bounded by the shortlist limit; mirrors the ledger's "audit every
  read attempt".
- **DPDP.** `job_requisitions` is org-owned (CASCADE on `org_id`), **not
  candidate-linked** — a requisition **survives candidate erasure** (correct) and
  dies with its org. The candidate-facing side effect (`match.surface` audit rows)
  is candidate-linked and CASCADEs on erasure; an erased candidate is absent from
  the vector pool, so a re-run simply omits them.
- **Point-in-time.** One `as_of` drives both the vector cut and the profile read,
  so skill coverage and scalar features describe the same instant — no leakage.

### Config (`match_*`)

`match_default_limit` (25), `match_skill_weight` (3.0, dominant),
`match_years_weight` / `match_degree_weight` / `match_notice_weight` /
`match_location_weight` (1.0 each), `match_nice_to_have_fraction` (0.3). View
selection reuses `feat_default_view` (`core_v1`).

### HTTP

`POST /jobs` (create) · `GET /jobs` (list) · `GET /jobs/{id}` · `PATCH /jobs/{id}`
(status and/or full spec replace) · `POST /jobs/{id}/match` →
`MatchResult{advisory=True}`. Cross-org → 404; empty/unmaterialized pool → 422;
malformed match request → 400; missing/invalid `X-Org-Key` → 401.

### Seams

- **S5.2 (comp intelligence):** consumes the stored `comp_band` (no migration) +
  ledger-observed offers; may add a comp-fit term — `MatchWeights`/
  `compile_ranking` leave room.
- **S5.3 (employer dashboard):** a thin read-only surface over `GET /jobs` +
  `POST /jobs/{id}/match` + linked `Report`s; the API stays the primary contract.
