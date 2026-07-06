# Veritas Roadmap — living plan (update every session)

> **New chat? Start here.** Read this file top to bottom, then open the spec:
> `docs/superpowers/specs/2026-07-06-veritas-talent-platform-design.md`.
> Work happens sprint by sprint: each sprint gets a spec/plan under
> `docs/superpowers/`, is built TDD-offline, and ends with `pytest -q` green
> plus a local smoke run. Update the status board + "Current state" section
> below before ending any session.

## ▶ Current state

- **Current sprint:** S1.1 — Prod-grade extraction schema + extractor
- **Next action:** Write implementation plan for S1.1 (superpowers:writing-plans),
  then build `app/candidates/schema.py` (CandidateProfile) test-first.
- **Last session (2026-07-06):** Product designed and approved. Spec, roadmap,
  CLAUDE.md, memory pointer committed. No implementation code yet.

## Status board

Legend: `[ ]` not started · `[~]` in progress · `[x]` done

```
VERITAS — TALENT INTELLIGENCE PLATFORM  (Indian-market Mercor, trust layer first)
│
├── PI-1  CANDIDATE DATA BACKBONE
│   ├── [~] S1.1  Prod-grade extraction schema + extractor
│   │            CandidateProfile: identity, contact(hashed), education[],
│   │            experience[], skills[], projects[], certifications[], links[];
│   │            per-field confidence + source-span provenance;
│   │            LLM extraction + deterministic fallback
│   ├── [ ] S1.2  Candidate store — SQLAlchemy + Alembic on SQLite (PG-shaped);
│   │            candidates / resumes(versioned) / extractions;
│   │            identity resolution via email+phone hash dedup
│   ├── [ ] S1.3  API + engine wiring — POST /candidates (upload → extract →
│   │            store → auto depth-eval); reports linked to candidate_id
│   └── [ ] S1.4  India normalization — skill taxonomy, degree/CGPA normalizer,
│                institution + employer canonicalization, city/notice-period
│
├── PI-2  FABRICATION DEFENSE 2.0
│   ├── [ ] S2.1  AI-generated-resume signals (new pipeline node; deterministic
│   │            first, LLM-assisted second; conservative gate stays)
│   ├── [ ] S2.2  Cross-field forensics — timeline overlaps/gaps,
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
