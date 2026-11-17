# Veritas factual review context

Timeline and structure findings plus content overlap form an advisory factual
review index. It never establishes fabricated experience or changes claim
verdicts or depth scores. Polished or AI-assisted writing is not evidence of
fabricated experience. Review the candidate's work and first-party evidence.

## Where checks run

The `cross_field` evaluation step checks the supplied or heuristically extracted
profile. Candidate intake compares fingerprints with other stored candidates
before evaluation and passes `resume_farm` into the engine. Ad-hoc `/evaluate`
has no corpus assessment. The scoring step combines the assessable factual
components and the report step retains the result through the SQL report store.
Production uses `NullFlywheel`; test observers remain available.

## Historical writing-style data

New resume evaluations do not compute writing-style assessments. The optional
`Report.ai_generation` contract remains so stored reports load unchanged; the
report screen shows writing-style observations only when that field is present.
`fabrication/ai_text.py` and `AIGenerationAssessment` remain in use by the
interview cheating check. Style patterns cannot establish authorship or dishonesty.

## S2.2 — Cross-field forensics (`cross_field` node)

[app/fabrication/cross_field.py](src/app/fabrication/cross_field.py) ·
[app/graph/nodes/cross_field.py](src/app/graph/nodes/cross_field.py)

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

[app/fabrication/similarity.py](src/app/fabrication/similarity.py) ·
[app/candidates/store.py](src/app/candidates/store.py) (`save_fingerprint`,
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

### Banding ([assess_resume_farm](src/app/fabrication/similarity.py))

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

## Advisory factual review index (`fabrication_risk`, scorer version 2)

`fabrication/risk.py` combines only assessable timeline/structure and content
overlap components. Each configured weight is multiplied by component confidence.
Missing components contribute neither value nor coverage. The default score is
`0.70 * weighted_mean + 0.30 * maximum`; confidence is
`min(0.90, 0.30 + 0.15 * usable_components)`.

The default confidence floor is 0.50. One component alone therefore returns
insufficient data. Moderate requires a score at least 0.30 and either one high
component or two non-low components. Elevated requires at least 0.60 and two
high components. These are heuristic review thresholds, not fraud probabilities.
Depth and claim verdicts remain separate and human review is required.

Historical unversioned/v1 assessments retain their original style-inclusive
score and explanation. Reads do not recompute them. `fr_weight_ai` remains an
ignored compatibility setting for v2. See [FEATURES.md](FEATURES.md) for versioned
risk features and the current `core_v1` view (version 4).

## What lands on the Report and in the flywheel

The flywheel column below describes optional test-observer events. Production
uses `NullFlywheel`; only SQL reports/outcomes retain these assessments.
`flywheel_path` is deprecated and ignored for writes. Legacy files are separate
cleanup work, not erased automatically.

| Sprint | Report field | Band values | Summary note fires on | Flywheel `record_type` |
|---|---|---|---|---|
| S2.2 | `cross_field` | insufficient_data / consistent / minor_issues / major_issues | major_issues | `cross_field` |
| S2.3 | `resume_farm` | insufficient_data / unique / similar / near_duplicate | near_duplicate | `resume_farm` |
| S2.4 | `fabrication_risk` | insufficient_data / low / moderate / elevated | moderate, elevated | `fabrication_risk` |

All four fields are `Optional` — pre-existing stored reports (and, for
`resume_farm`, all POST /evaluate reports) validate unchanged with `null`.
Every flywheel record carries `outcome: null`, closed later by human
judgment via `POST /report/{id}/outcome` — or, since S8.5, by the customer
themselves via `POST /screening/reports/{id}/outcome`. That distinction is
recorded on the row (`recorded_by`) and matters here specifically: a
calibration harness that could not tell a customer's judgment from our own
operator's would be measuring these thresholds against their own author.

## Config quick reference ([config.yaml](config.yaml), env override `DEE_*`)

```
Interview style helper: ai_likely_threshold 0.65 · ai_possible_threshold 0.40
      ai_min_confidence 0.50
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
├── test_fabrication_schema.py, test_ai_text_assess.py, test_ai_integration.py
├── test_cross_field_{schema,timeline,coherence,assess,node}.py,
│   test_report_cross_field.py, test_cross_field_integration.py  S2.2
├── test_resume_farm_{schema,assess,api}.py, test_similarity.py,
│   test_fingerprint_store.py, test_report_resume_farm.py        S2.3
├── test_fabrication_risk_schema.py, test_fabrication_risk.py,
│   test_scoring_fabrication_risk.py, test_report_fabrication_risk.py,
│   test_fabrication_risk_integration.py                         S2.4
└── fixtures/  ai_generated · inconsistent · farm_a/farm_b (adversarial)
```

All offline (NullLLM ⇒ deterministic floors).
