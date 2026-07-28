# veritas — talent intelligence platform (depth-eval engine core)

An Indian-market talent intelligence platform growing around a
**domain-agnostic** engine that evaluates a candidate's resume for both
**authenticity** and **technical depth** — the way a senior engineer would. It
does **not** keyword-match. For each claim it reasons about whether the claim
*coheres* with the infrastructure, data, and access the candidate would actually
have needed.

> **Advisory only.** Every result is flagged for human review. The system never
> auto-rejects a candidate. False positives (flagging a real person) are treated
> as the existential risk, so the calibration is conservative: when unsure, it
> **defers** instead of flagging.

Around that engine, the platform currently ships:

- **Candidate data backbone** (PI-1, done) — production extraction into a
  versioned, deduplicated, India-normalized candidate store with DPDP delete
  paths → [CANDIDATES.md](CANDIDATES.md)
- **Fabrication defense 2.0** (PI-2, done) — advisory AI-generated-text signals,
  cross-field timeline forensics, resume-farm near-duplicate detection, and a
  fused advisory `fabrication_risk` score → [FABRICATION.md](FABRICATION.md)
- **Evaluation ledger** (PI-3, done) — consent-first cross-company interview and
  coding-round records with purpose-scoped, revocable, audited DPDP consent, plus
  advisory Bayesian cross-company reputation → [LEDGER.md](LEDGER.md)
- **ML feature store & ranking** (PI-4, done) — a versioned feature registry,
  point-in-time materialization + CSV/parquet export, an admin talent-search /
  ranking API, and leakage-free training-set export → [FEATURES.md](FEATURES.md)
- **Demand side** (PI-5, in progress) — job requisitions + advisory
  role-conditioned match-ranking, and advisory comp intelligence (static bands
  blended with consent-gated ledger-observed offers) →
  [MATCHING.md](MATCHING.md) · [COMP.md](COMP.md)

Ships with two evaluation domains (**GenAI engineering**, **Data
Engineering**). Adding more is one file. Docs map: [FLOW.md](FLOW.md)
(pipeline internals) · [CANDIDATES.md](CANDIDATES.md) ·
[FABRICATION.md](FABRICATION.md) · [LEDGER.md](LEDGER.md) ·
[FEATURES.md](FEATURES.md) · [MATCHING.md](MATCHING.md) · [COMP.md](COMP.md) ·
[MODELS.md](MODELS.md) (model choices) · [docs/ROADMAP.md](docs/ROADMAP.md)
(live sprint status) · [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)
(original engine requirements).

---

## How it works

```
ingest → ai_signals → cross_field → claim_extraction → provenance
       → plausibility → probe_generation → scoring → report
```

| Node | Responsibility |
|------|----------------|
| `ingest` | Parse resume (PDF/text); capture first-party github/portfolio URLs. |
| `ai_signals` | **Advisory** AI-generated-text band: 4 deterministic stylometry detectors ⊕ optional capped LLM pass. Never touches scores ([FABRICATION.md](FABRICATION.md)). |
| `cross_field` | **Advisory** timeline forensics over the extracted profile (overlaps, gaps, education↔employment, seniority-vs-tenure). Pure date math, no LLM. |
| `claim_extraction` | LLM extracts atomic claims tagged `{domain, claim_type, specificity, anchor?}` + candidate context. Deterministic heuristic fallback when no API key. |
| `provenance` | For anchored claims, fetch GitHub signals (repo/commits/languages/recency), embed in ChromaDB, retrieve grounding. **First-party links only.** |
| `plausibility` ★ | **The core.** Hybrid of (a) the active domain's rule registry and (b) an LLM senior-engineer reasoning pass. Produces per-claim coherence + expected/missing signals + evidence. |
| `probe_generation` | Targeted follow-up questions a fabricator can't survive, scoped to suspicious claims. |
| `scoring` | Conservative calibration → per-claim status + confidence-weighted depth band. |
| `report` | Assemble the explainable report (verdict + evidence + probes + band); log every claim to the flywheel. |

**Explainability is mandatory:** there is no bare "fake"/"real" label anywhere.
Each verdict carries a coherence score, confidence, an evidence trail, reasoning,
and probe questions.

### The conservative gate (calibration)

```
confidence < defer_threshold            → DEFER       (never assert)
low coherence AND high confidence        → INCOHERENT  (flag for review)
coherence >= flag_threshold              → COHERENT
no evidence at all                       → UNVERIFIED
```

Thresholds are config-driven (`DEE_FLAG_COHERENCE_THRESHOLD`,
`DEE_FLAG_MIN_CONFIDENCE`, `DEE_DEFER_CONFIDENCE_THRESHOLD`).

---

## Run it

Requires Python 3.11+.

```bash
cd depth-eval-engine
python -m venv .venv
.venv\Scripts\activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Secrets go in .env (DEE_OPENROUTER_API_KEY for live LLM); all other
# config (models, thresholds, paths) lives in config.yaml.

# Run the tests
pytest -q

# Create/upgrade the candidate-store schema (SQLite by default; the
# Postgres migration is the same command on a different candidates_db_url)
alembic upgrade head

# Serve the API
uvicorn app.main:app --reload
```

> Without an API key the engine still runs: it falls back to the deterministic
> rule registry (`NullLLM`), which is exactly how the test suite stays offline.

Or with Docker:

```bash
docker build -t depth-eval-engine .
docker run -p 8000:8000 --env-file .env -v dee_data:/srv/app/data depth-eval-engine
```

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /evaluate` | Evaluate a resume (`resume_text` or `resume_pdf_b64`, optional `github_url`/`portfolio_url`, `domain`). Persists and returns a `Report`. |
| `POST /candidates` | Upload → extract profile → store (identity dedup, versioning) → resume-farm check → auto depth-eval (`evaluate: false` for bulk import). Returns ingest outcome + `resume_farm` + `Report`. |
| `GET /candidates/{id}` · `/resumes` · `/reports` | Candidate summary + newest profile (hashes only), resume versions, linked reports. |
| `DELETE /candidates/{id}` (and `/resumes/{rid}`) | DPDP hard erasure: resumes (raw text), extractions, fingerprints, linked reports. |
| `GET /report/{id}` | Fetch a persisted report (survives restarts — SQLite store). |
| `POST /report/{id}/outcome` | Record a human outcome (`verified_genuine` \| `verified_fabricated` \| `candidate_clarified` \| `inconclusive`), optionally per `claim_id`. Also appended to the flywheel — this closes the training loop. |
| `GET /report/{id}/outcomes` | List recorded outcomes for a report. |
| `GET /domains` | Registered domains + claim taxonomies. |
| `GET /healthz` | Liveness + effective mode (`version`, `env`, `llm_mode`, `domains`). |

Operational behavior: every response carries an `X-Request-ID` (propagated into
all structured log lines), oversize payloads are rejected via config-driven caps
(`max_resume_chars`, `max_pdf_b64_chars`), unknown domains 422 before the graph
runs, and unhandled errors return a generic 500 (details stay in the logs). Set
`DEE_API_AUTH_KEY` in `.env` to require an `X-API-Key` header on everything
except `/` and `/healthz`.

Beyond the core engine, three further planes ship (auth in parentheses; full
detail in the linked docs):

| Surface | Plane | Key endpoints | Doc |
|---------|-------|---------------|-----|
| Evaluation ledger | admin `X-API-Key` + org `X-Org-Key` | orgs + consent grant/revoke/status; `POST /ledger/records` · `/coding-rounds` · `/offers`; `GET …/records` · `…/coding-rounds` · `…/reputation` (query-time consent, every access audited) | [LEDGER.md](LEDGER.md) · [COMP.md](COMP.md) |
| Talent search / feature store | admin `X-API-Key` | `POST /talent/search` — filter + composite-score ranking over materialized feature vectors (advisory) | [FEATURES.md](FEATURES.md) |
| Demand side | org `X-Org-Key` | `POST/GET/PATCH /jobs` · `POST /jobs/{id}/match` (role-conditioned shortlist) · `POST /comp/estimate` · `GET /jobs/{id}/comp` (advisory comp band + benchmark) | [MATCHING.md](MATCHING.md) · [COMP.md](COMP.md) |

Every one of these is **advisory** and **consent-aware**: consent-gated writes,
query-time consent enforcement on cross-company reads, de-identified comp
aggregation, and DPDP erasure that cascades every candidate-linked row.

### Example request

```bash
curl -s localhost:8000/evaluate -H 'content-type: application/json' -d '{
  "resume_text": "- Fine-tuned GPT-4 to improve accuracy.\n- Built production RAG at scale.",
  "github_url": "https://github.com/me/my-rag-bot",
  "domain": "genai"
}' | jq '{depth_band, flagged_claim_ids, human_review_required, advisory}'
```

The response is a `Report`: per-claim `CoherenceVerdict`s (score, confidence,
status, evidence, probes), an aggregate `depth_band`, the always-on
`advisory` / `human_review_required` flags, and four optional **advisory**
fabrication assessments — `ai_generation`, `cross_field`, `resume_farm`, and the
fused `fabrication_risk` (bands + explained signals; never a rejection signal —
see [FABRICATION.md](FABRICATION.md)).

---

## Tiered LLM usage

Inference runs through **OpenRouter** (OpenAI-compatible API), so any model it
fronts is reachable by id. Models are config-driven (never hardcoded) and chosen
by tier in [app/services/llm.py](app/services/llm.py):

| Tier | Used by | Default model |
|------|---------|---------------|
| `parsing` | claim_extraction (cheap structural work) | `qwen/qwen3.6-flash` |
| `reasoning` | plausibility, probe_generation | `qwen/qwen3.7-max` |
| `reasoning_hard` | override for the hardest reasoning | `qwen/qwen3.7-max` |
| `bulk` | high-volume gen/classification (future; unused at M0) | `qwen/qwen3.6-35b-a3b` |

Defaults live in `config.yaml` (`model_reasoning`, `model_fast`, …); override any
of them there, or per-deploy via the matching `DEE_MODEL_*` env var (e.g. point
`reasoning_hard` at `anthropic/claude-opus-4-8` through the same OpenRouter client).

---

## Adding a new domain (the M2 path)

The LangGraph core has **zero** domain-specific logic — all of it lives behind
the [`DomainModel`](app/domains/base.py) interface.
[app/domains/data_eng.py](app/domains/data_eng.py) is the proof: the second
domain landed as one module with zero graph changes. To add, say, a cloud-infra
domain:

1. Create `app/domains/cloud_infra.py`:

   ```python
   from app.domains.base import DomainModel, Rule, register_domain
   from app.domains.rules import SignalRule

   @register_domain
   class CloudInfraDomain(DomainModel):
       key = "cloud_infra"
       display_name = "Cloud Infrastructure"

       @property
       def rules(self) -> list[Rule]: ...        # your coherence rules (SignalRule)
       @property
       def claim_types(self) -> list[str]: ...   # your claim vocabulary
       def heuristic_type_hints(self): ...       # keywords for the LLM-free fallback
       def extraction_guidance(self) -> str: ...
       def plausibility_system_prompt(self, ctx) -> str: ...
       def probe_guidance(self) -> str: ...
   ```

2. Register it by importing it from [app/domains/__init__.py](app/domains/__init__.py).

3. Call the API with `"domain": "cloud_infra"`. Nothing in the graph changes.

A rule is a small, deterministic coherence check. The shared
[`SignalRule`](app/domains/rules.py) lets you express one as "which expected
signals are present, and what's the domain-specific tell?" — see the seed rules
in [genai.py](app/domains/genai.py) (fine-tuning, RAG, multi-agent) and
[data_eng.py](app/domains/data_eng.py) (ETL, streaming, warehouse).

---

## Data & consent (DPDP)

Only **first-party** data is used: the candidate-provided resume and any
GitHub/portfolio URLs **they** share. The engine never scrapes third-party
profiles. Cross-company signals in the ledger (interview outcomes, coding
rounds, offers) are an organization's record of **its own** interaction with a
candidate, ingested only under a purpose-scoped, revocable, audited consent
grant — and every candidate-linked row cascades on DPDP erasure. Comp
aggregation reads only de-identified, k-anonymized offer data
([LEDGER.md](LEDGER.md) · [COMP.md](COMP.md)).

## Flywheel

Every `(claim → probe → verdict → outcome?)` record is appended to a pluggable
store ([app/services/flywheel.py](app/services/flywheel.py), JSONL by default)
with an open `outcome` field. Human reviewers close the loop through
`POST /report/{id}/outcome`; each judgment lands in both the report store and
the flywheel (`record_type: "outcome"`), so one stream joins evaluations to
ground truth for future calibration/training.

---

## Project layout

```
app/
  main.py                create_app(): middleware, error handler, lifespan
  api/routes.py          evaluate · candidates (upload/read/DPDP-delete)
                         · report · outcomes · domains · healthz
  graph/
    state.py             EvaluationState (Pydantic)
    build.py             LangGraph assembly + EvaluationEngine
    nodes/               one module per pipeline node (9 stages)
  candidates/            PI-1 backbone → CANDIDATES.md
    schema.py            CandidateProfile (confidence + SourceSpan provenance)
    extractor.py         LLM extraction + deterministic fallback
    hashing.py, dates.py salted contact hashes · date parsing
    normalize/           India normalization (skills/degrees/orgs/location)
    models.py, store.py  ORM rows + CandidateStore (identity, fingerprints)
  fabrication/           PI-2 signals → FABRICATION.md
    ai_text.py           S2.1 AI-text detectors + fusion/banding
    cross_field.py       S2.2 interval math + timeline/coherence checks
    similarity.py        S2.3 MinHash fingerprints + farm banding
    risk.py              S2.4 fused advisory fabrication_risk
  ledger/                PI-3 evaluation ledger → LEDGER.md
    schema.py, models.py contracts + ORM (orgs, consent, records, offers, audit)
    consent.py           pure purpose-scoped/expiring/revocable consent logic
    reputation.py        S3.4 Bayesian cross-company reputation (advisory)
    store.py             LedgerStore (consent-gated writes, audited reads)
  features/              PI-4 feature store & ranking → FEATURES.md
    registry.py, definitions/  @register_feature catalog (code-versioned)
    materialize.py, store.py   point-in-time vectors → ml_feature_vectors
    ranking.py, export.py      composite-score ranking · CSV/parquet · training set
  matching/              PI-5 demand side → MATCHING.md
    match.py, store.py   compile-to-ranking + skill coverage; JobStore
  comp/                  PI-5 comp intelligence → COMP.md
    bands.py, estimate.py  static prior + observed-offer blend (advisory)
    service.py           CompService (reads ledger-observed offers)
  domains/
    base.py              DomainModel interface + rule registry
    rules.py             shared SignalRule machinery (all domains build on it)
    genai.py             GenAI domain (fine-tuning · RAG · multi-agent)
    data_eng.py          Data Engineering domain (ETL · streaming · warehouse)
  schemas/               claims.py, report.py, fabrication.py (Pydantic v2)
  services/              Services container (candidates · ledger · features · jobs
                         · comp; injected, never global) + llm (OpenRouter) ·
                         vectorstore (Chroma) · github · flywheel · report_store
  core/                  config · calibration · logging · db (shared SQLAlchemy)
alembic/                 shared migrations 0001-0009 (candidate store, fingerprints,
                         ledger, consent/api-keys, coding rounds, reputation weight,
                         feature vectors, job requisitions, observed offers)
tests/                   per-node + API + integration + adversarial fixtures,
                         fully offline (653 tests)
docs/ROADMAP.md          live PI/sprint status (start here each session)
Dockerfile               non-root image with /healthz healthcheck
.github/workflows/ci.yml offline pytest on 3.11/3.12
```

## Roadmap (veritas PIs — live status in [docs/ROADMAP.md](docs/ROADMAP.md))

- **Engine M0/M1 (done):** 7-node pipeline, conservative calibration, SQLite
  report store + outcome loop, API hardening, two domains, Docker + CI.
- **PI-1 Candidate data backbone (done):** extraction schema + extractor,
  candidate store (SQLAlchemy/Alembic), API + engine wiring, India
  normalization.
- **PI-2 Fabrication defense (done):** AI-text signals · cross-field forensics ·
  resume-farm detection · fused advisory `fabrication_risk`.
- **PI-3 Evaluation ledger (done):** schema + DPDP consent · ledger APIs ·
  coding-round results · Bayesian cross-company reputation.
- **PI-4 ML feature store & ranking (done):** feature registry ·
  point-in-time materialization + export · talent search/ranking API ·
  training-set export.
- **PI-5 Demand side (in progress):** S5.1 job requisitions + role-conditioned
  matching ✓ · S5.2 comp intelligence v0 ✓ · S5.3 thin employer dashboard (next).
- **PI-6 candidate side & intake · PI-7 verification & assessment depth ·
  PI-8 scale & learning** — shaped, not started.
