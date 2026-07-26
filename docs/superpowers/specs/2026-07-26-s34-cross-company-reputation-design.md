# S3.4 — Cross-company reputation design

**Date:** 2026-07-26
**Sprint:** S3.4 (PI-3 Evaluation Ledger — final sprint)
**Status:** Approved direction (user, 2026-07-26): negative-signal stance =
**one corroboration-gated band** (recommended option); user delegated the
remaining technical choices.
**Builds on:** S3.1 (ledger schema + DPDP consent), S3.2 (ledger HTTP APIs, org
API keys, query-time read enforcement + audit), S3.3 (coding-round results).

## What we are building

The payoff of the whole ledger: an **advisory cross-company reputation signal**
computed on demand for a member org about a consenting candidate, by
aggregating that candidate's already-flowing `interview_records` **and**
`coding_round_results` into a single interpretable band + score.

Three properties the roadmap mandates, all delivered here:

1. **Bayesian aggregation with shrinkage toward a prior** — few data points
   never produce an extreme score; the estimate starts neutral and only moves
   as consented evidence accumulates.
2. **Recency decay** — older outcomes count less (configurable half-life).
3. **Per-org reliability weight** — each contributing org's evidence is scaled
   by a reliability multiplier (default neutral; the mechanism ships now, the
   calibrated values are a PI-8 concern).

Like everything in this repo it is **advisory only**: the reputation band is
context for a human reviewer. It never changes a verdict, a depth score, or a
depth band; it is **never a rejection signal**; nothing auto-rejects. There is
**no new record type** — reputation is a *derived read* over the two record
types already in the ledger.

## Where reputation lives (and where it does not)

Reputation is a **cross-company, candidate-level, consent-gated read** — the
same shape as S3.2's `query_records_for_org` and S3.3's
`query_coding_rounds_for_org`. It therefore lives beside them, **not** in the
depth-evaluation graph:

- The graph is deliberately identity-blind and per-resume; it has neither the
  candidate's cross-org history nor the org identity + read consent that
  reputation requires. Putting reputation in the graph would break that
  boundary. (This mirrors S2.3's decision to compute resume-farm detection at
  the API layer, not in the graph.)
- Reputation is **not** on the `Report`. The `Report` is candidate/resume-facing
  depth-eval output; reputation is org-facing and only exists under a specific
  org's `ledger_read` grant. Keeping them separate is correct and avoids leaking
  a consent-gated cross-company signal into an ungated report.

So reputation is: a pure aggregation module + a consent-gated store read + one
org-plane endpoint. No graph node, no `Report` field, no flywheel record (it is
a read, already audited in the ledger's own `audit_log`).

## Decisions taken

| Decision | Choice | Rationale |
|---|---|---|
| Negative-signal stance | **One corroboration-gated band** (`GUARDED`, needs ≥2 distinct orgs) | User-approved. Surfaces genuine cross-company negatives (e.g. no-shows across companies) while a single org can never brand a candidate. Mirrors S2.4's "ELEVATED needs ≥2 flags" gate. |
| New record type? | **No** — derived read over `interview_records` + `coding_round_results` | Roadmap constraint; the data already flows. |
| Consent purpose | **Reuse `ledger_read`** | Reputation is a strictly-less-granular read of the same underlying records; no taxonomy fragmentation (consistent with S3.3). |
| Aggregation model | **Beta-Binomial posterior mean**, shrunk toward a neutral prior | Standard, interpretable shrinkage; no-data ⇒ prior; lots of consistent data ⇒ observed weighted mean. |
| Evidence pooling | **One pooled posterior**, per-type weight multipliers, per-type components exposed | One number with a transparent breakdown (parallels S2.4 `RiskComponent`). |
| Coding-round normalization | `percentile/100`; else `score/max_score` (clamped); else **excluded** | A bare `score` has no cross-platform meaning — excluding it is the honest, conservative choice (S3.3 deliberately stored `max_score`/`percentile` for exactly this). |
| Outcome→value map | Code constants (like `_AI_RISK`), **not config** | Changing outcome polarity is a reviewed schema decision, never a deploy tunable. |
| Reliability persistence | Nullable `reliability_weight` column on `organizations` (default 1.0) + minimal admin setter | It is an org attribute (like `status`, `api_key_hash`); neutral default ⇒ no behavior change until deliberately set. |
| Report / graph / flywheel | **Untouched** | Reputation is an org-plane consent-gated read, audited in `audit_log`. |
| LLM | **None** | Pure deterministic math, like the fabrication subsystems. |

## The model (pure `app/ledger/reputation.py`)

Pure functions, no I/O, no LLM — the `app/fabrication/risk.py` pattern. Entry
point:

```
assess_reputation(
    records: list[InterviewRecord],
    coding_rounds: list[CodingRoundResult],
    *,
    now: datetime,
    reliability_by_org: dict[str, float] | None = None,
    settings: Settings | None = None,
) -> ReputationAssessment
```

`now` is required and injected (deterministic tests freeze it). Missing org in
`reliability_by_org` ⇒ reliability 1.0.

### 1. Observations

Each contributing row becomes one observation `(value v ∈ [0,1], time t, org o,
type_weight)`:

**Interview records** — `value = _OUTCOME_VALUE[outcome]`, `t = interviewed_at`,
`type_weight = rep_interview_weight`. Outcome map (code constants):

| Outcome | value | note |
|---|---|---|
| `HIRED` | 1.00 | strongest positive |
| `OFFER` | 0.90 | |
| `ADVANCED` | 0.65 | passed a stage |
| `REJECTED` | 0.15 | negative |
| `NO_SHOW` | 0.10 | behavioral negative |
| `WITHDRAWN` | — | **excluded** (candidate-initiated; not an evaluation of the candidate) |

Stage is *not* used in the v0 math (the outcome already carries most of the
signal); noted as a future lever, kept out for YAGNI.

**Coding rounds** — normalize to `value`:
- `percentile` present ⇒ `value = percentile / 100` (already a normalized rank —
  best signal);
- else `max_score` present and `> 0` ⇒ `value = clamp(score / max_score, 0, 1)`;
- else **excluded** (a bare score is uninterpretable across platforms).

`t = taken_at`, `type_weight = rep_coding_weight`.

Excluded rows (`WITHDRAWN`, un-normalizable coding) are counted into
`excluded_observations` for transparency and otherwise ignored.

### 2. Per-observation weight

```
age_days   = max(0, (now - t) in days)                      # future-dated ⇒ 0
recency    = 0.5 ** (age_days / rep_recency_halflife_days)  # half-life decay
reliability= reliability_by_org.get(o, 1.0)
w          = type_weight * recency * reliability             # ≥ 0
```

### 3. Bayesian posterior (Beta shrinkage toward the prior)

```
α0 = rep_prior_mean * rep_prior_strength
β0 = (1 - rep_prior_mean) * rep_prior_strength
score = (α0 + Σ wᵢ·vᵢ) / (rep_prior_strength + Σ wᵢ)   ∈ [0,1]
```

No observations ⇒ `score = rep_prior_mean` (0.5, neutral). Heavy consistent
evidence ⇒ `score → Σwv/Σw`. A single strong outlier is shrunk by the prior.

### 4. Confidence (evidence mass, saturating)

```
mass       = Σ wᵢ                         # "effective_n"
confidence = min(rep_confidence_cap, round(mass / (mass + rep_confidence_k), 2))
```

`mass = rep_confidence_k` ⇒ 0.5. Below `rep_min_confidence` the band is
`INSUFFICIENT_DATA` (never assert on thin evidence). This is the *coverage*
axis; the *direction/corroboration* axis is `distinct_orgs`, kept separate
exactly as `risk.py` separates `confidence` from `flagged_count`.

### 5. Banding (conservative, corroboration-gated)

`distinct_orgs` = number of distinct `org_id`s among included observations.

```
if confidence < rep_min_confidence:                         INSUFFICIENT_DATA
elif score ≥ rep_strong_threshold   and distinct_orgs ≥ rep_corroboration_orgs: STRONG
elif score ≥ rep_favorable_threshold:                       FAVORABLE
elif score ≤ rep_guarded_threshold  and distinct_orgs ≥ rep_corroboration_orgs: GUARDED
else:                                                       MIXED
```

Consequences (the point of the design):
- **Single-source high** (score ≥ strong but 1 org) ⇒ FAVORABLE, not STRONG.
- **Single-source low** (score ≤ guarded but 1 org) ⇒ MIXED, not GUARDED — one
  company can never brand a candidate.
- `GUARDED` is the *only* negative-leaning band, always corroborated, always
  advisory. Its copy is diligence-framed ("warrants the usual diligence"), never
  "poor/reject".

### 6. Components + assessment

Per evidence type present, a `ReputationComponent`:
`id ∈ {"interview_records","coding_rounds"}`, `observations` (count),
`effective_weight` (Σw in type), `mean_value` (Σwv/Σw, or 0 if Σw=0).

`ReputationAssessment` carries: `score`, `confidence`, `band`, `components`,
`total_observations`, `distinct_orgs`, `evidence_mass`, `excluded_observations`,
`reasoning`, `advisory=True`. **No per-org identities** in the assessment (the
raw-records endpoint already exposes those under the same grant; the aggregate
deliberately does not re-leak "which competitor interviewed them").

## Contracts (`app/ledger/schema.py`)

Added alongside the existing ledger contracts:

- `ReputationBand(StrEnum)`: `INSUFFICIENT_DATA`, `GUARDED`, `MIXED`,
  `FAVORABLE`, `STRONG`. Code-constant taxonomy.
- `ReputationComponent(BaseModel)`: `id`, `observations: int`,
  `effective_weight: float ≥ 0`, `mean_value: float ∈ [0,1]`.
- `ReputationAssessment(BaseModel)`: fields above; `advisory: bool = True`.
- `Organization` grows `reliability_weight: float = 1.0` (admin-visible).

## Store (`app/ledger/store.py`)

- `reputation_for_org(*, org_id, candidate_id, at=None) -> ReputationAssessment`
  — **query-time `ledger_read` enforcement**, identical machinery to
  `query_records_for_org`:
  - org + candidate must exist ⇒ `LookupError` (API 404);
  - check active `ledger_read` grant at `at` (or now); on denial **audit the
    denied attempt** (`action="reputation.query"`, `details={allowed:false}`) in
    the same transaction, then raise `ConsentError` (API 403) — probing a
    candidate's reputation is itself observable;
  - on allow: read the candidate's interview records + coding rounds (raw,
    ungated internal reads), build `reliability_by_org` from the referenced org
    rows (missing ⇒ 1.0), call `assess_reputation(..., now=at or utcnow())`,
    **audit the allowed attempt** (`details={allowed:true, consent_id, band,
    total_observations, distinct_orgs}`), return the assessment.
  - An org with an active `ledger_read` grant sees the aggregate across **all**
    member orgs (reputation-network semantics — same as the raw reads).
- `set_org_reliability(org_id, weight) -> Organization` — admin path; validates
  org exists (`LookupError`), `weight ≥ 0`, audits `org.set_reliability`.
- `_org` converter reads `row.reliability_weight` (None ⇒ 1.0).

No new consent taxonomy, no changes to the write paths.

## API (`app/api/routes.py`)

- **Org plane** (`org_router`, `X-Org-Key` → `require_org`):
  `GET /ledger/candidates/{candidate_id}/reputation`
  → `ReputationAssessment`. `ConsentError` → **403**, `LookupError` → **404**,
  missing/invalid key → **401** (via `require_org`, unchanged).
- **Admin plane** (`router`, `X-API-Key`):
  `POST /ledger/orgs/{org_id}/reliability` body `{ "weight": float ≥ 0 }`
  → updated `Organization`. `LookupError` → **404**, invalid weight → **422**.
  (Mirrors the existing `/api-key` admin sub-resource on an org.)

## Migration `0006_org_reliability_weight`

- Down-revision `0005_coding_round_results`. `upgrade()` adds nullable
  `reliability_weight FLOAT` to `organizations` (SQLite batch alter, matching
  `0004_org_api_keys`'s column-add); `downgrade()` drops it.
- No other table touched. The metadata-wide drift guard (indexes / FK-ondelete /
  nullability, extended in S3.2) picks up the new column automatically.

## Config knobs (`config.yaml` + `app/core/config.py`, `DEE_*`-overridable)

| Knob | Default | Meaning |
|---|---|---|
| `rep_prior_mean` | 0.50 | Beta prior mean (neutral) |
| `rep_prior_strength` | 4.0 | prior pseudo-count (shrinkage strength) |
| `rep_recency_halflife_days` | 365 | age at which an outcome's weight halves |
| `rep_min_confidence` | 0.50 | below ⇒ `INSUFFICIENT_DATA` |
| `rep_confidence_k` | 4.0 | evidence-mass at which confidence = 0.5 |
| `rep_confidence_cap` | 0.90 | confidence ceiling (parallels risk.py) |
| `rep_corroboration_orgs` | 2 | distinct orgs required for `STRONG`/`GUARDED` |
| `rep_strong_threshold` | 0.75 | score ≥ (AND corroborated) ⇒ `STRONG` |
| `rep_favorable_threshold` | 0.60 | score ≥ ⇒ `FAVORABLE` |
| `rep_guarded_threshold` | 0.35 | score ≤ (AND corroborated) ⇒ `GUARDED` |
| `rep_interview_weight` | 1.0 | interview-record type weight |
| `rep_coding_weight` | 1.0 | coding-round type weight |

Bounds: means/thresholds `∈ [0,1]`; strengths/`k`/halflife `> 0`; weights `≥ 0`;
`rep_corroboration_orgs ≥ 1`.

## DPDP

- Reputation reads only candidate-linked rows that already CASCADE on erasure;
  after `CandidateStore.delete_candidate` the candidate is gone ⇒
  `reputation_for_org` raises `LookupError` (**404**), consistent with the other
  reads. No new candidate-linked table ⇒ no new erasure path.
- `reliability_weight` is org-level, not candidate data.
- First-party data only; the `ledger_read` consent object + delete path already
  exist. Every reputation query (allowed or denied) is audited.

## Testing strategy (TDD, fully offline)

- **Pure `reputation.py`:** no observations ⇒ score = prior, band
  `INSUFFICIENT_DATA`; outcome→value mapping incl. `WITHDRAWN` excluded;
  coding-round normalization (percentile ▸ max_score ▸ excluded); recency
  halves at the half-life; reliability scales a contribution; Bayesian shrinkage
  (single outlier pulled toward prior; mass of consistent evidence converges);
  confidence saturates + caps; **corroboration gates** (single-source high ⇒
  FAVORABLE not STRONG; single-source low ⇒ MIXED not GUARDED; ≥2 orgs unlock
  STRONG/GUARDED); `advisory` always True; determinism.
- **Contracts:** band values; component/assessment validation; `Organization`
  default `reliability_weight = 1.0`.
- **Migration/model:** drift guard green with the new column; targeted test the
  column exists + defaults.
- **Store:** `reputation_for_org` 403 without read consent (denied attempt
  audited); 200 with read consent (allowed attempt audited, band/counts in
  details); reads both record types; excludes `WITHDRAWN` + un-normalizable
  coding; honors `reliability_by_org`; unknown org/candidate ⇒ `LookupError`;
  DPDP-erased candidate ⇒ `LookupError`. `set_org_reliability` updates + audits;
  rejects negative weight; unknown org ⇒ `LookupError`.
- **API:** `GET .../reputation` 401 (no key) / 404 (unknown candidate) / 403 (no
  read consent, audited) / 200 (with consent). `POST .../reliability` 200 / 404 /
  422 (negative).
- **Smoke `scripts/smoke_s34.py`** (uvicorn + scripted HTTP, key-less-capable):
  admin creates **2 orgs** (A, B) + issues keys + ingests a candidate → grant
  `ledger_write` to each → A + B each submit a couple of favorable interview
  records and a coding round (enough evidence mass to clear the confidence
  floor comfortably, not sit on it) → reputation query **403** without read
  consent → grant `ledger_read` → query **200**: corroborated
  (`distinct_orgs=2`) ⇒ `FAVORABLE` or `STRONG` with score > prior → admin sets
  B's `reliability_weight` and
  re-query returns a coherent (shifted) score → DPDP-erase the candidate →
  reputation **404**. Mirrors `scripts/smoke_s33.py`.

Estimated ~35–45 new tests (442 → ~485).

## Explicitly out of scope (later PIs)

- Learning per-org reliability from outcomes (PI-8 calibration harness) — S3.4
  ships the mechanism + neutral default only.
- Stage-weighted interview evidence; per-role/skill-conditioned reputation
  (PI-4/PI-5).
- Any use of reputation in ranking/search (PI-4) or in the depth `Report`.
- Reputation on the graph; any LLM; any auto-reject. All remain non-goals.

## Sprint workflow

spec (this doc) → implementation plan (`docs/superpowers/plans/`) → TDD-offline
build → `pytest -q` green → local smoke → update `LEDGER.md` (S3.4 section) and
`docs/ROADMAP.md` (status board `[x]` — PI-3 COMPLETE, Current state, session
log).
