# veritas — Fabrication Defense 2.0 (PI-2: S2.1 + S2.2 + S2.3 + S2.4)

How the platform detects signs of resume fabrication *around* the depth-eval
pipeline: AI-generated text, internally contradictory timelines, and
resume-farm near-duplicates. This documents the *fabrication* subsystem;
the depth-eval pipeline it decorates is in [FLOW.md](FLOW.md), the candidate
store it reads in [CANDIDATES.md](CANDIDATES.md). Source of truth is the
code; file refs are clickable.

---

## Design principles (non-negotiable)

1. **Advisory only, always.** No fabrication signal changes a claim's
   `VerdictStatus`, the `depth_score`, or the `depth_band`. Every assessment
   carries `advisory: true` and reviewer-facing copy that says "never a
   rejection signal". Fusion into calibration is S2.4 — and even then stays
   advisory.
2. **Conservative by construction.** False positives are the existential
   risk. Each subsystem has a structural safeguard that makes it *under*-fire:
   AI banding needs multiple independent tells, date math rounds against the
   finding, farm matching masks identity churn but demands high content
   overlap.
3. **Deterministic first, LLM optional.** Every signal has a pure,
   offline-computable core. The only LLM involvement anywhere in PI-2 is the
   S2.1 stylometry pass — cheap tier, confidence-capped, and never able to
   drive a band on its own. S2.2 and S2.3 use **no LLM at all**.
4. **Everything feeds the flywheel.** Each assessment logs one training
   record with an open `outcome` field, so future calibration can learn
   which signals actually predicted fabrication.

## Where each signal is computed

```
POST /evaluate                     POST /candidates
      │                                  │ extract → ingest (store)
      │                                  │ fingerprint → compare corpus   ← S2.3 (API layer)
      ▼                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│ LANGGRAPH PIPELINE                                                  │
│  ingest ─► ai_signals ─► cross_field ─► claim_extraction ─► …       │
│              ▲ S2.1        ▲ S2.2                                   │
│              │             │                                        │
│   stylometry over raw     date/structure math over the extracted    │
│   resume text             CandidateProfile (explicit or heuristic)  │
│                                                                     │
│  … ─► scoring ─► report ── attaches all three assessments to the    │
│                            Report + logs flywheel records           │
└────────────────────────────────────────────────────────────────────┘
```

Why S2.3 is **not** a graph node: cross-candidate comparison must exclude
the uploader's *own* other resumes (re-uploads and new versions are
legitimate), which requires knowing the uploader's `candidate_id` — and the
graph is deliberately candidate-blind (see [FLOW.md](FLOW.md)). So POST
/candidates computes the assessment in the API layer and passes it into
`engine.evaluate(resume_farm=...)` as an input, exactly like it passes the
extracted `candidate_profile`. POST /evaluate has no identity and no store,
so its reports carry `resume_farm: null`.

---

## S2.1 — AI-generated-resume signals (`ai_signals` node)

[app/fabrication/ai_text.py](app/fabrication/ai_text.py) ·
[app/graph/nodes/ai_signals.py](app/graph/nodes/ai_signals.py) ·
contracts in [app/schemas/fabrication.py](app/schemas/fabrication.py)

AI-assisted resume *writing* is common and legitimate — the band is
stylistic context for a reviewer, not an accusation. Four deterministic
detectors each measure one tell; each is gated on having enough text to
measure honestly:

| Detector | Fires when | Score |
|---|---|---|
| `template_phrases` | ≥ 3 hits from a stock-phrase list ("spearheaded", "results-driven", …) in ≥ 60 words | `min(1, density_per_100_words / 3)` |
| `uniform_bullets` | ≥ 6 bullets with length CV < 0.22 **and** ≥ 85% opening with a past-tense verb | blend of shape uniformity + verb fraction |
| `metric_saturation` | ≥ 70% of bullets carry a %/x metric | fraction × (0.7 + 0.3 · share of %s divisible by 5) |
| `symmetric_structure` | ≥ 3 experience entries with *identical* bullet counts (≥ 3 each) | `0.55 + 0.10 · entries` |

The deterministic pass averages the scores of every detector that *could*
run (non-fired ones count 0.0) and derives confidence from coverage:
`min(0.9, 0.30 + 0.15 · evaluated)`.

**LLM stylometry (optional):** one call on the `parsing` (FAST) tier over a
6 000-char excerpt. Its confidence is **capped at 0.75**, and it degrades to
nothing on no key / garbage output. Deterministic and LLM pairs are fused
confidence-weighted (same math as plausibility's `_fuse`).

**Banding** ([band_for](app/fabrication/ai_text.py)) is where the
conservatism is structural:

```
confidence < ai_min_confidence (0.50)      → INSUFFICIENT_TEXT
likelihood ≥ ai_likely_threshold (0.65)    → LIKELY  only if ≥ 2 deterministic
                                             tells fired; else POSSIBLE
likelihood ≥ ai_possible_threshold (0.40)  → POSSIBLE
else                                        → UNLIKELY
```

**The LLM alone can never produce LIKELY.** Output:
`AIGenerationAssessment {likelihood, confidence, band, signals[], reasoning,
advisory=true}` → `Report.ai_generation`; summary note only on
POSSIBLE/LIKELY.

Config: `ai_likely_threshold`, `ai_possible_threshold`, `ai_min_confidence`,
`ai_llm_excerpt_chars` ([config.yaml](config.yaml)).

---

## S2.2 — Cross-field forensics (`cross_field` node)

[app/fabrication/cross_field.py](app/fabrication/cross_field.py) ·
[app/graph/nodes/cross_field.py](app/graph/nodes/cross_field.py)

Checks the extracted `CandidateProfile` against *itself* — pure date and
structure math, **no LLM by design**. The node uses the profile POST
/candidates already extracted (`state.candidate_profile`); on POST /evaluate
it derives one deterministically via
`normalize_profile(heuristic_profile(text))`.

**Conservative interval math** is the core safeguard. A year-only date like
`2018` is ambiguous, so it is resolved *against* the finding:

- `narrow_interval` — months a range *certainly* covers (year-only start →
  December, year-only end → January). Used for overlaps ⇒ every flagged
  overlap is a **lower bound**. Two year-only ranges like 2020–2022 vs
  2021–2023 can never false-positive.
- `wide_interval` — widest plausible cover (start → January, end →
  December). Used for career span ⇒ span is an **upper bound**, so
  seniority findings under-fire.
- `month_precise_interval` — only when both endpoints carry a month. Used
  for gaps: year precision can't measure a gap honestly, so it never flags.

Four checks over primary employment (internship / part-time / freelance /
contract entries are exempt where overlap is legitimate):

| Check | Threshold (config) | Severity |
|---|---|---|
| `timeline_overlap` — concurrent primary roles | ≥ `xf_overlap_months_min` (3) | minor; **major** ≥ 12 months |
| `timeline_gap` — between merged month-precise roles | ≥ `xf_gap_months_min` (12) | **always minor** — career breaks are legitimate; copy says so |
| `education_employment_overlap` — primary work inside a *bachelor's* (part-time/executive master's are common in India — never flagged) | ≥ `xf_edu_overlap_months_min` (12) | minor; **major** ≥ 24 months |
| `seniority_vs_tenure` — lead/principal/head+ title vs total career span (needs ≥ 2 dated entries, so a truncated resume never fires) | span < `xf_lead_min_months` (48); "senior" < `xf_senior_min_months` (24) | lead-level **major**; senior minor (title inflation is common) |

Confidence follows coverage (same shape as S2.1):
`min(0.9, 0.30 + 0.15 · evaluated_checks)`; banding never asserts below
`xf_min_confidence` (0.50), and MAJOR_ISSUES requires at least one major
finding. Output: `CrossFieldAssessment {score, confidence, band, findings[],
reasoning, advisory=true}` → `Report.cross_field`; summary note only on
`major_issues`.

---

## S2.3 — Resume-farm detection (API layer, MinHash)

[app/fabrication/similarity.py](app/fabrication/similarity.py) ·
[app/candidates/store.py](app/candidates/store.py) (`save_fingerprint`,
`similar_resumes`) · migration
[0002_resume_fingerprints](alembic/versions/0002_resume_fingerprints.py)

Resume farms mass-produce applications from one template: same bullets,
different name/contact. Detection therefore compares **content** across
candidates — deterministically, with no embeddings and no LLM.

### The similarity math

```
resume text
  │  normalize_for_shingles: lowercase; mask emails, URLs, phone-like digit
  │  runs (the phone regex deliberately also swallows bare year ranges —
  │  farms stagger dates, so removing them helps detection)
  ▼
word 3-shingles  (rf_shingle_words=3; < rf_min_shingles=40 ⇒ don't fingerprint)
  │
  ▼
MinHash signature — 128 affine permutations (a·h + b) mod 2^61−1 over stable
  blake2b 64-bit shingle hashes; fixed seed ⇒ fully deterministic
  │
  ▼
estimate_similarity(a, b) = fraction of agreeing components ≈ Jaccard
  similarity of the shingle sets (stderr ≈ 1/√128 ≈ 0.04)
```

Masking makes an email/phone-only swap **invisible** (identical signature);
a name+city swap still lands ≈ 0.93 on the adversarial fixture pair —
comfortably above the 0.80 near-duplicate threshold. Signatures are only
comparable within one **algo id** (`"minhash-v1:128x3"` = family : perms ×
shingle size); changing config bumps the id and old fingerprints simply
stop participating until re-fingerprinted.

### Storage & query

Every POST /candidates ingest persists one row in `resume_fingerprints`
(unique per `(resume_id, algo)`, FKs CASCADE — DPDP deletes erase
fingerprints with the resume/candidate; see the ER diagram in
[CANDIDATES.md](CANDIDATES.md)). The query is a linear scan over stored
signatures of **other** candidates, same algo only:

```
similar_resumes(fp, exclude_candidate_id, threshold=rf_similar_threshold,
                limit=rf_max_matches)  →  (matches best-first, corpus_size)
```

Linear scan is deliberate at SQLite scale (signatures are small int lists);
LSH banding is the flagged optimization if the corpus ever outgrows it.

### Banding ([assess_resume_farm](app/fabrication/similarity.py))

```
text too short to fingerprint                        → INSUFFICIENT_DATA
any match ≥ rf_near_dup_threshold (0.80)             → NEAR_DUPLICATE
matches from ≥ rf_cluster_candidates_min (3)         → NEAR_DUPLICATE
  DISTINCT other candidates                            (farm-cluster escalation:
                                                       a farm rarely makes one
                                                       perfect copy — it makes
                                                       MANY near copies)
any match ≥ rf_similar_threshold (0.60)              → SIMILAR
else                                                  → UNIQUE
```

Two resumes from *one* other candidate is not a cluster (distinct-candidate
count). Confidence reflects how much corpus the claim is based on:
`min(0.9, 0.6 + 0.05 · min(corpus_size, 6))` — "unique among nothing" is a
weak claim. Output: `ResumeFarmAssessment {score=max similarity, confidence,
band, matches[], corpus_size, reasoning, advisory=true}` →
`Report.resume_farm` **and** the `CandidateCreateResponse` itself, so bulk
imports with `evaluate=false` (exactly the farm scenario) still see the
signal. Summary note only on `near_duplicate`, and it reminds the reviewer
that shared templates (coaching institutes, resume builders) are common and
legitimate.

### Accepted residuals (known, deliberate)

- Resumes ingested before S2.3 have no fingerprints and sit outside the
  corpus; `corpus_size` makes that visible. Backfill utility deferred.
- `save_fingerprint` is check-then-insert; the unique constraint is the
  backstop under concurrent writers. Revisit at the Postgres migration.
- A farm that heavily rewords every copy can sink below the 0.60 similarity
  floor — the conservative trade is intentional.

---

## S2.4 — Unified fabrication_risk (calibration stage)

[app/fabrication/risk.py](app/fabrication/risk.py) ·
[app/graph/nodes/scoring.py](app/graph/nodes/scoring.py) ·
contracts in [app/schemas/fabrication.py](app/schemas/fabrication.py)

Fuses `ai_generation ⊕ cross_field ⊕ resume_farm` into one advisory
`fabrication_risk` — a single number and band for a reviewer who doesn't
want to cross-reference three separate assessments. Still advisory, still
never auto-reject: fusion happens **inside the scoring node**, because
scoring is the calibration stage, but it only ever *adds* a field to the
returned state — it never reads or rewrites `verdicts`, `depth_score`, or
`depth_band`.

Each subsystem's band maps to a component risk; INSUFFICIENT_* bands are
excluded from fusion entirely (absence of signal is not evidence of risk):

| Component | Low band → risk | Mid band → risk | High band → risk |
|---|---|---|---|
| `ai_generation` | unlikely → 0.10 | possible → 0.45 | likely → 0.75 |
| `cross_field` | consistent → 0.10 | minor_issues → 0.40 | major_issues → 0.75 |
| `resume_farm` | unique → 0.10 | similar → 0.45 | near_duplicate → 0.80 |

Only assessed (non-insufficient) subsystems produce a `RiskComponent`, each
carrying its own `weight = fr_weight_<subsystem> · confidence` and a
`flagged` bit set at that subsystem's top band (LIKELY / MAJOR_ISSUES /
NEAR_DUPLICATE).

**Score** blends a confidence-weighted mean across components with the max
component risk, 70/30:

```
score = 0.7 · (Σ risk·weight / Σ weight) + 0.3 · max(risk)
```

A pure mean would let clean subsystems dilute one strong signal; a pure max
would ignore corroboration. The 70/30 blend keeps a single strong signal
visible (it can still reach MODERATE) while ELEVATED separately requires
corroboration — see the gate below.

**Confidence** follows coverage, the same shape as S2.1/S2.2:
`min(0.9, 0.30 + 0.15 · evaluated)`. One assessed subsystem → confidence
0.45, which sits *below* `fr_min_confidence` (0.50) — **fusion over a
single subsystem can never assert; it always lands INSUFFICIENT_DATA.**
That is deliberate: a unified score is only meaningful once it is actually
uniting more than one signal.

**Banding** ([band_for_risk](app/fabrication/risk.py)):

```
confidence < fr_min_confidence (0.50)                    → INSUFFICIENT_DATA
score ≥ fr_elevated_threshold (0.60) AND ≥ 2 components
  flagged at their top band                               → ELEVATED
score ≥ fr_moderate_threshold (0.30)                      → MODERATE
else                                                       → LOW
```

The `≥ 2 flags` gate mirrors S2.1's "LIKELY needs ≥ 2 deterministic tells":
one strong signal (e.g. a lone `near_duplicate` sitting inside the MinHash
stderr's false-positive tail — see S2.3's residuals) can drive the score
into MODERATE but is capped there; ELEVATED needs corroborating evidence
from a second subsystem. Output: `FabricationRiskAssessment {score,
confidence, band, components[], reasoning, advisory=true}` →
`Report.fabrication_risk`; summary note fires on **MODERATE and ELEVATED**
(deliberately — three soft signals converging on MODERATE is exactly the
case where fusion adds information no single per-component note carries),
and its copy reiterates: never changes the depth evaluation, never a
rejection signal. Every assessment also logs a `fabrication_risk` flywheel
record with the per-component bands, `outcome: null`.

Config: `fr_moderate_threshold`, `fr_elevated_threshold`, `fr_min_confidence`,
`fr_weight_ai`, `fr_weight_cross_field`, `fr_weight_farm`
([config.yaml](config.yaml)).

---

## What lands on the Report and in the flywheel

| Sprint | Report field | Band values | Summary note fires on | Flywheel `record_type` |
|---|---|---|---|---|
| S2.1 | `ai_generation` | insufficient_text / unlikely / possible / likely | possible, likely | `ai_signals` |
| S2.2 | `cross_field` | insufficient_data / consistent / minor_issues / major_issues | major_issues | `cross_field` |
| S2.3 | `resume_farm` | insufficient_data / unique / similar / near_duplicate | near_duplicate | `resume_farm` |
| S2.4 | `fabrication_risk` | insufficient_data / low / moderate / elevated | moderate, elevated | `fabrication_risk` |

All four fields are `Optional` — pre-existing stored reports (and, for
`resume_farm`, all POST /evaluate reports) validate unchanged with `null`.
Every flywheel record carries `outcome: null`, closed later by human
judgment via `POST /report/{id}/outcome`.

## Config quick reference ([config.yaml](config.yaml), env override `DEE_*`)

```
S2.1  ai_likely_threshold 0.65 · ai_possible_threshold 0.40
      ai_min_confidence 0.50   · ai_llm_excerpt_chars 6000
S2.2  xf_min_confidence 0.50   · xf_overlap_months_min 3 · xf_gap_months_min 12
      xf_edu_overlap_months_min 12 · xf_senior_min_months 24 · xf_lead_min_months 48
S2.3  rf_shingle_words 3 · rf_num_permutations 128 · rf_min_shingles 40
      rf_similar_threshold 0.60 · rf_near_dup_threshold 0.80
      rf_cluster_candidates_min 3 · rf_max_matches 10
S2.4  fr_moderate_threshold 0.30 · fr_elevated_threshold 0.60
      fr_min_confidence 0.50 · fr_weight_ai 1.0 · fr_weight_cross_field 1.0
      fr_weight_farm 1.0
```

Severity-escalation constants (overlap major at 12 months, edu-overlap major
at 24) are code, not config — change deliberately.

## Testing & smokes

```
tests/
├── test_fabrication_schema.py, test_ai_text.py, test_ai_signals_node.py,
│   test_report_ai_signals.py, test_ai_integration.py            S2.1
├── test_cross_field_{schema,timeline,coherence,assess,node}.py,
│   test_report_cross_field.py, test_cross_field_integration.py  S2.2
├── test_resume_farm_{schema,assess,api}.py, test_similarity.py,
│   test_fingerprint_store.py, test_report_resume_farm.py        S2.3
├── test_fabrication_risk_schema.py, test_fabrication_risk.py,
│   test_scoring_fabrication_risk.py, test_report_fabrication_risk.py,
│   test_fabrication_risk_integration.py                         S2.4
└── fixtures/  ai_generated · inconsistent · farm_a/farm_b (adversarial)
```

All offline (NullLLM ⇒ deterministic floors). Each sprint's end-to-end
smoke boots uvicorn on a scratch Alembic-migrated DB and passes key-less
AND live: [scripts/smoke_s21.py](scripts/smoke_s21.py) ·
[scripts/smoke_s22.py](scripts/smoke_s22.py) ·
[scripts/smoke_s23.py](scripts/smoke_s23.py) ·
[scripts/smoke_s24.py](scripts/smoke_s24.py).
