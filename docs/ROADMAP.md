# Veritas Roadmap — living plan (update every session)

> **New chat? Start here.** Read this file top to bottom, then open the spec:
> `docs/superpowers/specs/2026-07-06-veritas-talent-platform-design.md`.
> Work happens sprint by sprint: each sprint gets a spec/plan under
> `docs/superpowers/`, is built TDD-offline, and ends with `pytest -q` green
> plus a local smoke run. Update the status board + "Current state" section
> below before ending any session.

## ▶ Current state

- **Current sprint:** S3.1 — Ledger schema + DPDP consent model (PI-3 start)
- **Next action:** Execute the S3.1 plan
  (`docs/superpowers/plans/2026-07-19-s31-ledger-schema-consent.md`,
  branch `s31-ledger-consent`, 7 TDD tasks, 350→~395 tests).
- **Last session (2026-07-18):** S2.4 done on branch `s24-fabrication-risk`
  — PI-2 COMPLETE. Unified advisory fabrication_risk: pure fusion in
  `app/fabrication/risk.py` (band→risk code constants; 0.7·weighted-mean +
  0.3·max blend; coverage confidence so single-subsystem fusion never
  asserts; ELEVATED needs ≥2 flags, MODERATE needs a flag or ≥2 non-clean
  — the latter gate added mid-session after the live smoke caught a genuine
  resume banding moderate off one soft LLM signal), fused in the scoring
  node (depth/verdicts provably untouched), `Report.fabrication_risk` +
  moderate/elevated summary note + flywheel `record_type:
  "fabrication_risk"`, config `fr_*`. 350 tests green; smoke
  `scripts/smoke_s24.py` 10/10 key-less AND live.
- **Prior session (2026-07-17):** S2.3 done on branch `s23-resume-farm`:
  `app/fabrication/similarity.py` (contact-masked word shingles,
  deterministic MinHash 128 perms, algo id "minhash-v1:128x3",
  `assess_resume_farm` with cluster escalation), migration
  `0002_resume_fingerprints` (CASCADE FKs = DPDP deletes), store
  `save_fingerprint`/`similar_resumes`, API-layer detection in POST
  /candidates (self-exclusion by candidate_id — the graph never sees
  identity, so no new node), `Report.resume_farm` + near_duplicate-only
  summary note + flywheel `record_type: "resume_farm"`. Config knobs `rf_*`.
  312 tests green; smoke `scripts/smoke_s23.py` 11/11 OK key-less AND live.

## Status board

Legend: `[ ]` not started · `[~]` in progress · `[x]` done

```
VERITAS — TALENT INTELLIGENCE PLATFORM  (Indian-market Mercor, trust layer first)
│
├── PI-1  CANDIDATE DATA BACKBONE
│   ├── [x] S1.1  Prod-grade extraction schema + extractor
│   │            CandidateProfile: identity, contact(hashed), education[],
│   │            experience[], skills[], projects[], certifications[], links[];
│   │            per-field confidence + source-span provenance;
│   │            LLM extraction + deterministic fallback
│   ├── [x] S1.2  Candidate store — SQLAlchemy + Alembic on SQLite (PG-shaped);
│   │            candidates / resumes(versioned) / extractions;
│   │            identity resolution via email+phone hash dedup
│   ├── [x] S1.3  API + engine wiring — POST /candidates (upload → extract →
│   │            store → auto depth-eval); reports linked to candidate_id
│   └── [x] S1.4  India normalization — skill taxonomy, degree/CGPA normalizer,
│                institution + employer canonicalization, city/notice-period
│
├── PI-2  FABRICATION DEFENSE 2.0
│   ├── [x] S2.1  AI-generated-resume signals — ai_signals node after ingest
│   │            (deterministic stylometry ⊕ capped LLM), advisory band on Report
│   ├── [x] S2.2  Cross-field forensics — cross_field node (deterministic
│   │            timeline/coherence checks over the extracted profile),
│   │            advisory findings on Report
│   ├── [x] S2.3  Resume-farm detection — MinHash near-duplicates across
│   │            candidates (resume_fingerprints table, API-layer detection,
│   │            advisory Report.resume_farm)
│   └── [x] S2.4  Unified fabrication_risk score fused into calibration +
│                Report; still advisory, never auto-reject
│
├── PI-3  EVALUATION LEDGER (cross-company)
│   ├── [ ] S3.1  Ledger schema + DPDP consent model — organizations,
│   │            interview_records, evaluation_events, consent_grants
│   │            (purpose-scoped, revocable, audited)
│   ├── [ ] S3.2  Ledger APIs — submit/query with consent enforced at query
│   │            time; org-scoped API keys; audit trail
│   ├── [ ] S3.3  Coding-round results — schema + ingest ONLY (far point):
│   │            platform, problem tags, score, percentile
│   └── [ ] S3.4  Cross-company reputation — Bayesian aggregation with
│                recency decay + per-org reliability weight
│
├── PI-4  ML FEATURE STORE & RANKING
│   ├── [ ] S4.1  Feature registry (versioned definitions over candidate +
│   │            eval + ledger data)
│   ├── [ ] S4.2  Materialization → wide ml_features table + CSV/parquet
│   │            export; point-in-time correct (no label leakage)
│   ├── [ ] S4.3  Talent search/ranking API (filters + composite score)
│   └── [ ] S4.4  Training-set export — features ⋈ outcomes (flywheel+ledger)
│
└── PI-5  BACKLOG (not designed) — AI interview delivery, matching engine,
        company dashboard, Postgres migration, real embeddings
```

## Standing conventions (do not relitigate)

- TDD, fully offline tests (NullLLM/fakes); `pytest -q` green before merge.
- Every LLM step degrades to a deterministic fallback (works with no API key).
- Advisory only — no auto-reject anywhere; conservative calibration gate stays.
- DPDP: first-party data only; consent objects + delete paths for new tables.
- Config: tunables in `config.yaml`, secrets in `.env` (`DEE_*`).
- DB: SQLAlchemy + Alembic on SQLite, Postgres-shaped (UUIDs, FKs, JSON columns).
- Each sprint ends with a local smoke: uvicorn + scripted HTTP calls on fixtures.
- LLM provider: OpenRouter + Qwen tiers (see `config.yaml`).

## Session log

- **2026-07-06** — Brainstormed + approved product design (Talent Intelligence
  Platform slice of a Mercor-style marketplace; SQLite-now/PG-shaped; modular
  monolith). Created spec, roadmap, CLAUDE.md, memory pointer. Next: S1.1 plan.
- **2026-07-06 (2)** — S1.1 done, TDD-offline on branch `s11-extraction-schema`:
  `app/candidates/{schema,hashing,dates,extractor}.py` — CandidateProfile with
  per-field confidence + SourceSpan provenance, salted contact-dedup hashing
  (`contact_hash_salt` in config.yaml), deterministic date parser, section-based
  heuristic extractor + LLM path (`parsing` tier) with fallback. 26 new tests
  (88 green). Smoke `scripts/smoke_s11.py` green with live OpenRouter key AND
  key-less (heuristic floor). Next: S1.2 plan (candidate store).
- **2026-07-06 (3)** — S1.2 done, TDD-offline on branch `s12-candidate-store`:
  shared SQLAlchemy core (`app/core/db.py`: Base, engine w/ SQLite FK pragma +
  StaticPool, session factory; `candidates_db_url` setting), PG-shaped ORM rows
  (`app/candidates/models.py`: candidates / resumes versioned-unique /
  extractions JSON), Alembic env + `0001_candidate_store` (+ drift-guard test),
  `CandidateStore` (`app/candidates/store.py`: ingest with email→phone hash
  identity resolution + backfill, sha256 resume dedup, latest_profile,
  DPDP hard deletes, `build_candidate_store`). 25 new tests (113 green).
  Smoke `scripts/smoke_s12.py` green live (llm) AND key-less (heuristic).
  Next: S1.3 plan (API + engine wiring).
- **2026-07-06 (4)** — S1.3 implementation plan written:
  `docs/superpowers/plans/2026-07-06-s13-api-engine-wiring.md` (7 TDD tasks,
  branch `s13-api-wiring`, 113→137 tests). Scope: `Report.candidate_id` +
  `for_candidate`/`delete_for_candidate` on both report stores (guarded ALTER
  for legacy reports.db), shared `app/core/pdf.py` helper, `Services.candidates`
  via `build_candidate_store`, POST /candidates (extract → ingest → auto
  depth-eval, graph untouched), GET candidate/resumes/reports, DPDP DELETE
  endpoints (candidate erasure also deletes linked reports), uvicorn smoke
  `scripts/smoke_s13.py`. Next: execute the plan.
- **2026-07-06 (5)** — S1.3 done, TDD-offline on branch `s13-api-wiring`:
  `Report.candidate_id` + `for_candidate`/`delete_for_candidate` on both report
  stores (guarded ALTER on legacy reports.db), shared `app/core/pdf.py`,
  `Services.candidates` via `build_candidate_store`, POST /candidates
  (extract → ingest → auto depth-eval; report stamped with candidate_id;
  graph/`/evaluate` untouched), GET candidate/resumes/reports, DPDP DELETE
  resume + candidate (erasure also deletes linked reports). 24 new tests
  (137 green). Smoke `scripts/smoke_s13.py` green live (llm) AND key-less
  (heuristic) — 11/11 checks OK both runs. Final review fix: POST /candidates
  re-checks the candidate after saving the report and drops the report if the
  candidate was erased mid-eval (25 new tests, 138 green). Accepted residual:
  a milliseconds-wide erasure race between that re-check and a concurrent
  delete's report sweep — mop up via a future orphaned-reports sweep (reports
  whose candidate_id no longer resolves). Next: S1.4 plan (India
  normalization).
- **2026-07-09** — S1.4 implementation plan written:
  `docs/superpowers/plans/2026-07-09-s14-india-normalization.md` (7 TDD tasks,
  branch `s14-india-normalization`, 138→190 tests). Scope: pure deterministic
  `app/candidates/normalize/` package (no LLM, no migration, no new tables),
  Optional canonical sibling fields on the S1.1 schema, extractor wiring.
- **2026-07-16** — S1.4 done, TDD-offline on branch `s14-india-normalization`:
  `app/candidates/normalize/{text,skills,degrees,orgs,location}.py` + the
  `normalize_profile` orchestrator — norm_key alias indexing, ~85-skill
  taxonomy, Indian degree families + canonical CGPA/10 (cgpa_4×2.5, %÷9.5
  clamped), institution alias table + IIT/IIM/NIT/IIIT campus patterns with
  tiers, ~60-employer alias table with legal-suffix stripping, city gazetteer
  (metro/tier_2) + notice-period parser (both offset-preserving for
  provenance). Schema grew all-Optional canonical fields (legacy JSON still
  validates); `heuristic_profile` lifts location + notice period with spans;
  `extract_profile` normalizes both paths; prompt asks for `notice_period`.
  52 new tests (190 green). Smoke `scripts/smoke_s14.py` 8/8 OK key-less
  (heuristic floor) AND live (llm) after the user refreshed the expired
  OpenRouter key. PI-1 complete. Next: S2.1 plan.
- **2026-07-17** — S2.1 implementation plan written:
  `docs/superpowers/plans/2026-07-17-s21-ai-signals.md` (7 TDD tasks, branch
  `s21-ai-signals`, 190→~223 tests). Scope: pure `app/fabrication/ai_text.py`
  (4 deterministic detectors: template phrases, uniform bullets, metric
  saturation, symmetric structure; fusion + conservative banding), new
  `ai_signals` graph node after ingest (deterministic first, LLM stylometry
  second with confidence capped at 0.75; LIKELY requires ≥2 deterministic
  tells — LLM alone can never flag), `AIGenerationAssessment` surfaced as an
  advisory `Report.ai_generation` field + flywheel record, adversarial
  fixture, smoke `scripts/smoke_s21.py`. No migration; depth scoring
  untouched (fusion into calibration is S2.4). Next: execute the plan.
- **2026-07-17 (2)** — S2.1 done, TDD-offline on branch `s21-ai-signals`:
  `app/schemas/fabrication.py` (AISignal / AILikelihoodBand /
  AIGenerationAssessment, advisory always true), `app/fabrication/ai_text.py`
  (template-phrase density, uniform-bullet shape, round-% metric saturation,
  symmetric entry structure; detectors gated on word/bullet minimums,
  confidence grows with evaluable detectors; fuse_pairs + band_for with the
  LIKELY ⇒ ≥2 deterministic tells gate), `ai_signals` node wired
  ingest → ai_signals → claim_extraction (LLM stylometry via the `parsing`
  FAST tier — non-decisive by design, so no flagship spend; confidence
  capped 0.75, degrades to deterministic on no key/garbage),
  `Report.ai_generation` + summary advisory note + flywheel
  `record_type: "ai_signals"`. Config knobs `ai_*` in config.yaml/Settings.
  35 new tests (225 green). Smoke `scripts/smoke_s21.py` 6/6 OK key-less
  (deterministic floor) AND live (llm; read timeout raised to 600s — the
  12-bullet fixture pays one reasoning call per claim). Next: S2.2 plan.
- **2026-07-17 (3)** — S2.2 implementation plan written:
  `docs/superpowers/plans/2026-07-17-s22-cross-field-forensics.md` (8 TDD
  tasks, branch `s22-cross-field`, 225→~268 tests). Scope: pure
  `app/fabrication/cross_field.py` (conservative interval math: year-only
  dates shrink inward for overlaps / expand outward for tenure; 4 checks),
  `cross_field` node after ai_signals (explicit profile from POST
  /candidates, else deterministic heuristic fallback; NO LLM in S2.2),
  advisory `Report.cross_field` + flywheel record. Gaps always minor.
- **2026-07-17 (4)** — S2.2 done, TDD-offline on branch `s22-cross-field`:
  `app/schemas/fabrication.py` grew FindingSeverity / ConsistencyBand /
  CrossFieldFinding / CrossFieldAssessment; `app/fabrication/cross_field.py`
  (narrow/wide/month-precise intervals, timeline_overlap ≥3mo (major ≥12),
  timeline_gap ≥12mo (always minor, neutral copy), education_employment_overlap
  ≥12mo bachelor-only (major ≥24), seniority_vs_tenure with 24/48-month
  floors (senior=minor, lead+=major) needing ≥2 dated entries;
  band_for_findings + assess_cross_field with the S2.1 confidence formula),
  `cross_field` node wired ai_signals → cross_field → claim_extraction
  (uses `state.candidate_profile` when POST /candidates supplies it, else
  `normalize_profile(heuristic_profile(text))`), `EvaluationEngine.evaluate`
  + POST /candidates pass the extracted profile through,
  `Report.cross_field` + major-only summary note + flywheel
  `record_type: "cross_field"`. Config knobs `xf_*` in config.yaml/Settings.
  45 new tests (270 green). Smoke `scripts/smoke_s22.py` 9/9 OK key-less
  (NullLLM + heuristic extraction) AND live (LLM extraction; both profile
  paths land major_issues on the inconsistent fixture, genuine stays clean).
  Next: S2.3 plan.
- **2026-07-17 (5)** — S2.3 done, TDD-offline on branch `s23-resume-farm`:
  `app/fabrication/similarity.py` (contact-masking before shingling so
  identity swaps don't dodge detection, word shingles + deterministic
  MinHash over 128 permutations, algo id "minhash-v1:128x3",
  `assess_resume_farm` bands unique/near_duplicate/insufficient_data with
  escalation once a cluster of matches appears), migration
  `0002_resume_fingerprints` with CASCADE FKs so DPDP deletes cascade
  cleanly, store `save_fingerprint`/`similar_resumes`. Detection lives at
  the API layer inside POST /candidates rather than as a graph node — the
  comparison must self-exclude by candidate_id (re-uploads and new versions
  are legitimate), and the graph is deliberately kept identity-blind.
  `Report.resume_farm` + near_duplicate-only advisory summary note +
  flywheel `record_type: "resume_farm"`. Config knobs `rf_*` in
  config.yaml/Settings. 42 new tests (312 green). One review fix
  (commit f0ba555) tightened advisory framing on all reasoning paths.
  Smoke `scripts/smoke_s23.py` 11/11 OK key-less (NullLLM + heuristic
  extraction) AND live (LLM extraction): first upload of a farm template is
  unique, an identity-swapped copy from a different candidate lands
  near_duplicate at a measured estimated similarity of 0.9375 (near_duplicate
  threshold 0.80) pointing back at the original, the uploader's own
  re-upload dedupes and self-excludes cleanly while still correctly
  matching the other farm member, a genuine resume stays unique, and
  POST /evaluate carries no farm assessment (no identity, no comparison).
  The smoke script's original re-upload check asserted the wrong property
  (expected `unique`, ignoring that a genuine near-duplicate was already in
  the corpus) and was corrected mid-session to assert self-exclusion
  directly — a script bug, not a product bug. Next: S2.4 plan.
- **2026-07-18** — S2.4 implementation plan written:
  `docs/superpowers/plans/2026-07-18-s24-fabrication-risk.md` (7 TDD tasks,
  branch `s24-fabrication-risk`, 312→~345 tests). Scope: pure deterministic
  `app/fabrication/risk.py` (band→risk mapping as code constants; fused score
  = 0.7·confidence-weighted mean + 0.3·max component risk; coverage
  confidence `min(0.9, 0.30 + 0.15·evaluated)` so single-subsystem fusion
  never asserts; ELEVATED requires ≥2 components at their top band —
  mirrors S2.1's ≥2-tells gate), computed in the scoring node (the
  calibration stage) with depth/verdicts provably untouched,
  `Report.fabrication_risk` + summary note on moderate/elevated + flywheel
  `record_type: "fabrication_risk"`, config knobs `fr_*`, smoke
  `scripts/smoke_s24.py`. No LLM, no migration. Next: execute the plan.
- **2026-07-18 (2)** — S2.4 done on branch `s24-fabrication-risk` (subagent-
  driven: 7 tasks, each spec+quality reviewed; final whole-branch review
  clean). Delivered per plan: contracts (FabricationRiskBand / RiskComponent
  / FabricationRiskAssessment), `app/fabrication/risk.py` (build_components
  excludes absent/insufficient signals; fuse = 0.7·weighted-mean + 0.3·max;
  confidence min(0.9, 0.30+0.15·evaluated) — one subsystem ⇒ 0.45 ⇒ never
  asserts), scoring-node fusion (depth/verdicts untouched, tested at node,
  pipeline, and both API entry paths), Report field + moderate/elevated
  advisory note + flywheel record, `fr_*` knobs, FABRICATION.md S2.4 docs.
  ONE DELIBERATE PLAN DEVIATION: the live smoke (first run 9/10) caught a
  genuine resume fusing to moderate off a single soft signal (ai=possible
  0.45 + rf=unique 0.10, cross_field dropped out ⇒ score 0.318 ≥ 0.30), so
  `band_for_risk` grew a MODERATE corroboration gate (flagged ≥1 OR
  non-clean ≥2; commit d7c23f5) mirroring the ELEVATED ≥2-flags gate —
  strictly more conservative, live re-run 10/10. Also: fr_weight=0 does not
  fully mute a subsystem (documented, not changed); smoke scratch-dir leak
  is a pre-existing pattern across all smoke scripts. 350 tests green.
  PI-2 complete. Next: S3.1 plan.
- **2026-07-19** — S3.1 implementation plan written:
  `docs/superpowers/plans/2026-07-19-s31-ledger-schema-consent.md` (7 TDD
  tasks, branch `s31-ledger-consent`, 350→~395 tests). Scope: new
  `app/ledger/` package — Pydantic contracts + StrEnum taxonomies
  (stage screen/tech/coding/hm, outcome, purpose ledger_write/ledger_read),
  pure clock-free consent logic (`consent.py`: purpose/org scope, always-
  expiring, revocation as point-in-time boundary, naive-UTC coercion for
  SQLite), ORM rows on the shared Base (organizations, consent_grants,
  interview_records, evaluation_events, audit_log), migration
  `0003_evaluation_ledger` (candidate-linked rows CASCADE ⇒ existing DPDP
  erasure sweeps the ledger; orgs survive), `LedgerStore` with write-time
  ConsentError gate on record submission + audit row in the same
  transaction, config knob `ledger_consent_default_ttl_days: 365`,
  direct-store smoke `scripts/smoke_s31.py` (key-less; S3.1 is LLM-free),
  `LEDGER.md`. No HTTP APIs (S3.2), no LLM. Next: execute the plan.
