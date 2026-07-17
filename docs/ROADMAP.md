# Veritas Roadmap — living plan (update every session)

> **New chat? Start here.** Read this file top to bottom, then open the spec:
> `docs/superpowers/specs/2026-07-06-veritas-talent-platform-design.md`.
> Work happens sprint by sprint: each sprint gets a spec/plan under
> `docs/superpowers/`, is built TDD-offline, and ends with `pytest -q` green
> plus a local smoke run. Update the status board + "Current state" section
> below before ending any session.

## ▶ Current state

- **Current sprint:** S2.2 — Cross-field forensics
- **Next action:** Write the S2.2 plan (timeline overlaps/gaps,
  education↔experience coherence, seniority-vs-claims).
- **Last session (2026-07-17):** S2.1 done on branch `s21-ai-signals`:
  `app/fabrication/ai_text.py` (4 deterministic detectors + fusion +
  conservative banding), `ai_signals` node after ingest (LLM stylometry
  capped at 0.75 confidence; LIKELY needs ≥2 deterministic tells),
  advisory `Report.ai_generation` + flywheel record, adversarial fixture.
  225 tests green; smoke `scripts/smoke_s21.py` 6/6 OK key-less AND live.

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
│   ├── [~] S2.2  Cross-field forensics — timeline overlaps/gaps,
│   │            education↔experience coherence, seniority-vs-claims
│   ├── [ ] S2.3  Resume-farm detection — near-duplicates across candidates
│   │            (minhash/embeddings)
│   └── [ ] S2.4  Unified fabrication_risk score fused into calibration +
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
