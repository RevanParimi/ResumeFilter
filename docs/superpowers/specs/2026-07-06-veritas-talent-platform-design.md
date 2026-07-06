# Veritas — Talent Intelligence Platform (design spec)

**Date:** 2026-07-06
**Status:** Approved by user (scope + PI ordering + continuity mechanism)
**Supersedes nothing** — builds on the M1-hardened depth-eval-engine.

## What we are building

An Indian-market talent intelligence platform (Mercor-inspired, codename
**veritas**) built by growing this repo into a modular monolith. The existing
depth-eval pipeline becomes the *vetting* subsystem; new peer subsystems are
added beside it:

1. **Candidate data backbone** — production-grade resume extraction into a
   versioned candidate database (India-normalized).
2. **Fabrication defense 2.0** — AI-generated-resume detection, cross-field
   forensics, resume-farm detection, unified fabrication risk score.
3. **Cross-company evaluation ledger** — interview outcomes (and later coding
   round results) shared across member companies with DPDP consent as a
   first-class design object.
4. **ML feature store** — versioned feature registry + point-in-time-correct
   materialization into a wide `ml_features` table with CSV/parquet export,
   joinable to ground-truth outcomes.

**Explicitly out of scope** (PI-5 backlog at most): matching UI, payments,
company dashboards, AI interview delivery, Postgres migration.

## Decisions taken (with user)

| Decision | Choice | Rationale |
|---|---|---|
| Product slice | Talent Intelligence Platform (vetting + records + ledger + features) | Where the repo has a moat; marketplace CRUD deferred |
| Database | SQLite now, Postgres-shaped (SQLAlchemy + Alembic; UUIDs, JSONB-compatible columns, FKs) | Zero local setup, offline tests; PG switch = connection string |
| Architecture | Modular monolith in this repo | Repo layering (`graph/domains/services/core`) already clean; no network plumbing between co-developed parts |
| Ordering | Backbone → Fabrication → Ledger → Features | Ledger value depends on trusting records underneath |
| Consent | DPDP consent model is a core schema object (purpose-scoped, revocable, audited), not a patch | Cross-company sharing is legally radioactive otherwise; also the differentiator |
| Coding rounds | Schema + ingest API only in PI-3 | User's "far point" — data model ready, no scoring logic |
| ML fields | Feature registry + point-in-time materialization, not ad-hoc wide columns | Prevents label leakage in exported training data |

## Architecture

```
app/
├── graph/ + domains/            (existing: vetting subsystem, unchanged role)
├── candidates/                  PI-1: extraction schema, store, normalizers
├── ledger/                      PI-3: orgs, evaluations, consent, coding rounds
├── features/                    PI-4: registry, materialization, ranking
├── services/ + core/            shared (db session, config, logging)
└── api/                         routes grow per subsystem
```

Conventions carried forward from M0/M1 (non-negotiable):

- **TDD, fully offline tests** — NullLLM/fakes pattern; `pytest -q` green before merge.
- **LLM with deterministic fallback** — every LLM-assisted step must degrade to
  a rule/heuristic path (no API key ⇒ still functional).
- **Advisory only** — no auto-reject anywhere; conservative calibration gate stays.
- **Consent-clean** — first-party data only; DPDP delete paths for every new table.
- **Config split** — tunables in `config.yaml`, secrets in `.env` (`DEE_*`).
- Each sprint ends with a **local smoke run**: `uvicorn` + scripted HTTP calls
  against fixture resumes, so changes are verified end-to-end, not just by unit tests.

## PI / Sprint roadmap

See `docs/ROADMAP.md` (living document, status tracked there). Summary:

- **PI-1 Candidate Data Backbone**: S1.1 extraction schema+extractor · S1.2
  candidate store (SQLAlchemy/Alembic) · S1.3 API + engine wiring · S1.4 India
  normalization (skills taxonomy, degrees/CGPA, institutions, employers).
- **PI-2 Fabrication Defense 2.0**: S2.1 AI-text signals node · S2.2
  cross-field forensics · S2.3 resume-farm detection · S2.4 unified
  fabrication_risk in calibration + Report.
- **PI-3 Evaluation Ledger**: S3.1 schema + DPDP consent model · S3.2 ledger
  APIs (consent enforced at query time, org API keys, audit trail) · S3.3
  coding-round schema+ingest · S3.4 Bayesian cross-company reputation.
- **PI-4 ML Feature Store & Ranking**: S4.1 feature registry · S4.2
  materialization + export · S4.3 talent search/ranking API · S4.4 training-set
  export (features ⋈ outcomes).
- **PI-5 backlog** (not designed): AI interview delivery, matching, dashboard,
  Postgres migration, real embeddings.

## Key data contracts (shape, refined per-sprint)

- **CandidateProfile** (S1.1): identity, contact (hashed for dedup), education[]
  (degree, institution, CGPA-normalized, dates), experience[] (employer,
  title→seniority, dates, employment_type), skills[], projects[],
  certifications[], links[]; **per-field extraction confidence + source-span
  provenance** back to resume text.
- **Ledger** (S3.1): organizations, interview_records (stage taxonomy:
  screen/tech/coding/HM), evaluation_events, consent_grants (purpose, scope,
  expiry, revocation), audit_log.
- **ml_features** (S4.2): one row per candidate per snapshot time; features
  computed only from data visible at snapshot (point-in-time correctness);
  label columns joined from flywheel + ledger outcomes at export, never stored.

## Testing strategy

Unit tests per module (offline), integration test per subsystem, one
end-to-end smoke per PI (fixture resume → API → DB → report → export).
Fabrication-defense sprints add adversarial fixtures (AI-generated resumes,
timeline-contradiction resumes, near-duplicate pairs).

## Continuity mechanism (cross-chat)

- `docs/ROADMAP.md` — living status (current sprint + next action), updated at
  end of every working session.
- `CLAUDE.md` (repo root) — auto-loaded each session; points to ROADMAP first.
- Auto-memory pointer entry in Claude's project memory.
- Per-sprint specs/plans live in `docs/superpowers/specs|plans/`.
