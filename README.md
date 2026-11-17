# veritas — talent intelligence platform (depth-eval engine core)

Current capabilities: [Feature status](FEATURE_STATUS.md). Current state:
[docs/PROGRESS.md](docs/PROGRESS.md).

Current feature contracts live in the linked guides. Superseded implementation
plans and prototype UI documents were retired from the working tree; their
[original versions remain in Git](https://github.com/RevanParimi/ResumeFilter/tree/54804988f3ead83d727754e4361266a4322655c4/docs/superpowers).


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
- **Ledger and consent** (PI-3) — member organisations, API keys and
  purpose-scoped, revocable, audited DPDP consent grants → [LEDGER.md](LEDGER.md)
- **ML feature store & ranking** (PI-4, done) — a versioned feature registry,
  point-in-time materialization and the ranking engine job matching uses →
  [FEATURES.md](FEATURES.md)
- **Demand side** — job requisitions, advisory role ranking and the role board →
  [MATCHING.md](MATCHING.md)
- **Candidate side** (PI-6, done) — a candidate auth plane + DPDP portal
  (access, transparency, consent control, erasure) → [PORTAL.md](PORTAL.md)
- **Verification & assessment depth** (PI-7) — a verification spine with
  consent-first identity: an assurance ladder behind a method-adapter seam,
  storing outcomes only (never documents or biometrics). Ships self-attestation,
  contact-control OTP, and operator manual review; government-ID is a declared,
  unimplemented adapter → [VERIFICATION.md](VERIFICATION.md)
- **AI interviews** (S7.3) — audio-first, advisory interviews that ask the depth
  report's *own* probes and score the answers deterministically (an optional LLM
  pass may only nudge, never grade). Audio is transcribed and discarded; the
  transcript is the candidate's to read and is never disclosed to an org.
  Proxy-risk signals read the identity assurance held when the session started —
  no voice biometrics → [INTERVIEWS.md](INTERVIEWS.md)

Ships with two evaluation domains (**GenAI engineering**, **Data
Engineering**). Adding more is one file. Docs map: [FLOW.md](FLOW.md)
(pipeline internals) · [CANDIDATES.md](CANDIDATES.md) ·
[FABRICATION.md](FABRICATION.md) · [LEDGER.md](LEDGER.md) ·
[FEATURES.md](FEATURES.md) · [MATCHING.md](MATCHING.md) · [COMP.md](COMP.md) ·
[DASHBOARD.md](DASHBOARD.md) · [PORTAL.md](PORTAL.md) ·
[VERIFICATION.md](VERIFICATION.md) · [INTERVIEWS.md](INTERVIEWS.md) ·
[MODELS.md](MODELS.md) (model choices) ·
[docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)
(original engine requirements).

---

## How it works

```
ingest → cross_field → claim_extraction → provenance
       → plausibility → probe_generation → scoring → report
```

| Node | Responsibility |
|------|----------------|
| `ingest` | Parse resume (PDF/text); capture first-party github/portfolio URLs. |
| `cross_field` | **Advisory** timeline forensics over the extracted profile (overlaps, gaps, education↔employment, seniority-vs-tenure). Pure date math, no LLM. |
| `claim_extraction` | LLM extracts atomic claims tagged `{domain, claim_type, specificity, anchor?}` + candidate context. Deterministic heuristic fallback when no API key. |
| `provenance` | Fetch GitHub signals for each claim's linked repo (or the candidate's shared repo). Evidence stays within the evaluation; repeated links share a local fetch cache. **First-party links only.** |
| `plausibility` ★ | **The core.** Hybrid of (a) the active domain's rule registry and (b) an LLM senior-engineer reasoning pass. Produces per-claim coherence + expected/missing signals + evidence. |
| `probe_generation` | Targeted follow-up questions a fabricator can't survive, scoped to suspicious claims. |
| `scoring` | Conservative calibration → per-claim status + confidence-weighted depth band. |
| `report` | Assemble the explainable report (verdict + evidence + probes + band); retain it through the SQL report store. |

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

### Two ways this refuses to start (S8.1)

Both are deliberate, and neither has a config knob:

| Refusal | Why |
|---|---|
| `DEE_API_AUTH_KEY` unset or blank | The admin plane is 27 endpoints including `POST /candidates/{id}/auth-key`, which mints any candidate's access key. An unset credential used to mean "auth disabled"; it now means "do not start". There is **no local-development exemption** — `env` defaults to `local`, so exempting it would make a safe deploy depend on remembering two variables instead of one. |
| `DEE_ENV=prod` with a SQLite `DEE_CANDIDATES_DB_URL` | Container disks are ephemeral: every row would be lost on the next redeploy, silently. SQLite also serializes writes across workers. |

Set the key once for local work:

```bash
echo "DEE_API_AUTH_KEY=$(openssl rand -hex 32)" >> .env
```

The app also runs `alembic upgrade head` **on boot** (`db_migrate_on_boot`, default
true), so a fresh container against an empty database migrates itself. On
Postgres it takes an advisory lock first, so concurrent workers cannot race the
same migration.

Or with Docker:

```bash
docker build -t depth-eval-engine .
docker run -p 8000:8000 --env-file .env -v dee_data:/srv/app/data depth-eval-engine
```

## Deploy

The image is **deploy-ready and not yet deployed**, on purpose: there are zero
customers, and the user decides when that changes. `railway.json` is committed
so the deploy itself is one command when it does.

**See [`DEPLOY.md`](DEPLOY.md)** — the go-live checklist. All eight boot
refusals with the variable that satisfies each, every `DEE_` variable, the
proxy setting that looks like an attack when it is wrong, and **the retention
cron, which nothing else schedules**.

The container migrates itself on boot; no separate migration step is needed.

It imports reports and outcomes into the main database, and reports-and-drops
any report whose candidate was already erased — those are orphans the old
two-database split could not prevent, and the new foreign key rejects them.
An absent file is a clean no-op, so it is safe to run anywhere.

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /evaluate` | Evaluate a resume (`resume_text` or `resume_pdf_b64`, optional `github_url`/`portfolio_url`, `domain`). Persists and returns a `Report`. |
| `POST /candidates` | Upload → extract profile → store (identity dedup, versioning) → resume-farm check → auto depth-eval (`evaluate: false` for bulk import). Returns ingest outcome + `resume_farm` + `Report`. |
| `GET /candidates/{id}` · `/resumes` · `/reports` | Candidate summary + newest profile (hashes only), resume versions, linked reports. |
| `DELETE /candidates/{id}` (and `/resumes/{rid}`) | DPDP hard erasure: resumes (raw text), extractions, fingerprints, linked reports. |
| `GET /report/{id}` | Fetch a persisted report (survives restarts; since S8.1 it lives in the main database beside its candidate). |
| `POST /report/{id}/outcome` | Record a human outcome (`verified_genuine` \| `verified_fabricated` \| `candidate_clarified` \| `inconclusive`), optionally per `claim_id`, in the erasable SQL outcome store. |
| `GET /report/{id}/outcomes` | List recorded outcomes for a report. |
| `GET /domains` | Registered domains + claim taxonomies. |
| `GET /healthz` | Liveness + effective mode (`version`, `env`, `llm_mode`, `domains`). |

Operational behavior: every response carries an `X-Request-ID` (propagated into
all structured log lines), oversize payloads are rejected via config-driven caps
(`max_resume_chars`, `max_pdf_b64_chars`), unknown domains 422 before the graph
runs, and unhandled errors return a generic 500 (details stay in the logs). Set
`DEE_API_AUTH_KEY` in `.env` to require an `X-API-Key` header on everything
except `/` and `/healthz`.

Beyond the core engine, further surfaces ship across three auth planes — admin
(`X-API-Key`), org (`X-Org-Key`) and candidate (`X-Candidate-Key`). Full detail
in the linked docs:

| Surface | Plane | Key endpoints | Doc |
|---------|-------|---------------|-----|
| Ledger | admin `X-API-Key` + org `X-Org-Key` | orgs + consent grant/revoke/status | [LEDGER.md](LEDGER.md) · [COMP.md](COMP.md) |
| Feature store | admin `X-API-Key` | `POST /features/materialize` — point-in-time feature vectors for matching | [FEATURES.md](FEATURES.md) |
| Candidate DPDP portal | candidate `X-Candidate-Key` (key minted admin-side) | `GET /portal/me` · `GET /portal/access-log` · `GET/POST /portal/consents` · `POST /portal/consents/{id}/revoke` · `DELETE /portal/me` | [PORTAL.md](PORTAL.md) |
| Demand side | org `X-Org-Key` | `POST/GET/PATCH /jobs` · `GET /jobs/{id}/board` (advisory shortlist) | [MATCHING.md](MATCHING.md) |
| Verification: identity | candidate `X-Candidate-Key` + org `X-Org-Key` + admin `X-API-Key` | `POST /portal/verifications` · `…/{id}/confirm` · `GET /portal/verifications` (assurance); `GET /verification/candidates/{id}/assurance` (consent-gated, every attempt audited allowed *and* denied); `POST /candidates/{id}/verifications/manual-review` | [VERIFICATION.md](VERIFICATION.md) |

Every one of these is **advisory** and **consent-aware**: consent-gated writes,
query-time consent enforcement on cross-company reads, de-identified comp
aggregation, and DPDP erasure that cascades every candidate-linked row. The
candidate plane is the exception that proves the rule — a data principal
reading or erasing their **own** data is gated by identity alone, never by a
consent object ([PORTAL.md](PORTAL.md)).

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
by tier in [app/services/llm.py](src/app/services/llm.py):

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

The evaluation pipeline core has **zero** domain-specific logic — all of it lives behind
the [`DomainModel`](src/app/domains/base.py) interface.
[app/domains/data_eng.py](src/app/domains/data_eng.py) is the proof: the second
domain landed as one module with zero graph changes. To add, say, a cloud-infra
domain:

1. Create `src/app/domains/cloud_infra.py`:

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

2. Register it by importing it from [app/domains/__init__.py](src/app/domains/__init__.py).

3. Call the API with `"domain": "cloud_infra"`. Nothing in the graph changes.

A rule is a small, deterministic coherence check. The shared
[`SignalRule`](src/app/domains/rules.py) lets you express one as "which expected
signals are present, and what's the domain-specific tell?" — see the seed rules
in [genai.py](src/app/domains/genai.py) (fine-tuning, RAG, multi-agent) and
[data_eng.py](src/app/domains/data_eng.py) (ETL, streaming, warehouse).

---

## Data & consent (DPDP)

Only **first-party** data is used: the candidate-provided resume and any
GitHub/portfolio URLs **they** share. The engine never scrapes third-party
profiles. Purpose-scoped consent grants are revocable and audited; every
candidate-linked row cascades on erasure ([LEDGER.md](LEDGER.md)).

Identity verification stores **outcomes only** — never a document, image, or
biometric. That posture is structural rather than procedural: no column on
either verification table can hold an artifact, and the sole evidence field is
a sha256 digest, so a future KYC adapter cannot persist one without a migration
a reviewer would see ([VERIFICATION.md](VERIFICATION.md)).

Candidates exercise their own DPDP rights first-party through the candidate
plane — access, an access log of who touched their data, consent grant/revoke,
and self-service erasure — gated by identity alone, never by a consent object
([PORTAL.md](PORTAL.md)). Retention windows are **surfaced** per data class;
the mechanical purge job is not built yet.

## Flywheel

Reports and human outcomes are retained in SQL. Candidate erasure cascades to
their reports/outcomes; standalone reports follow their own report deletion and
retention lifecycle. The optional [observer](src/app/services/flywheel.py) uses
`NullFlywheel` in production and an explicit in-memory observer in offline tests.
It no longer writes duplicate JSONL records outside SQL's deletion lifecycle.

`flywheel_path` / `DEE_FLYWHEEL_PATH` is a deprecated compatibility setting and
does not enable file retention. Existing JSONL files are left untouched and need
separate legacy cleanup (R1-S1-T2). Training/quality analysis uses SQL sources;
any external JSONL consumer must migrate rather than expect new appended rows.

---

## Project layout

```
src/app/
  main.py                create_app(): middleware, error handler, lifespan
  api/routes.py          remaining product handlers and ordered API assembly
  api/screening.py       employer intake · scoped reports/outcomes · batches/queue
  api/candidates.py      candidate intake/resumes · shared ingest DTOs
  api/reports.py         evaluate · operator reports/outcomes · shared outcome DTOs
  api/auth.py            email-OTP authentication and session lifecycle
  api/dependencies.py    shared principal resolution, CSRF and request helpers
  graph/
    state.py             EvaluationState (Pydantic)
    build.py             evaluation pipeline assembly + EvaluationEngine
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
    schema.py, models.py contracts + ORM (orgs, consent, audit)
    consent.py           pure purpose-scoped/expiring/revocable consent logic
    store.py             LedgerStore (consent-gated writes, audited reads)
  features/              PI-4 feature store & ranking → FEATURES.md
    registry.py, definitions/  @register_feature catalog (code-versioned)
    materialize.py, store.py   point-in-time vectors → ml_feature_vectors
    ranking.py                 composite-score ranking
  matching/              PI-5 demand side → MATCHING.md
    match.py, store.py   compile-to-ranking + skill coverage; JobStore
  portal/                PI-6 candidate DPDP portal → PORTAL.md
    schema.py, retention.py  read-shapes + pure retention posture
    service.py           PortalService (composition; owns no tables)
  verification/          PI-7 verification spine → VERIFICATION.md
    schema.py            assurance ladder + Verification/IdentityAssurance
    assurance.py, otp.py pure folding w/ read-time expiry · pure OTP mechanics
    methods.py           method-adapter seam (govt-ID declared, unimplemented)
    models.py, store.py  outcomes + short-lived challenges; consent-gated reads
    service.py           VerificationService (third-party gate, destination binding)
  domains/
    base.py              DomainModel interface + rule registry
    rules.py             shared SignalRule machinery (all domains build on it)
    genai.py             GenAI domain (fine-tuning · RAG · multi-agent)
    data_eng.py          Data Engineering domain (ETL · streaming · warehouse)
  schemas/               claims.py, report.py, fabrication.py (Pydantic v2)
  services/              Services container (candidates · ledger · features · jobs
                         · portal
                         · verification; injected, never global) + llm (OpenRouter) ·
                         github (evaluation-local provenance) · flywheel · report_store
  core/                  config · calibration · logging · db (shared SQLAlchemy)
alembic/                 shared migrations 0001-0009 (candidate store, fingerprints,
                         ledger, consent/api-keys, coding rounds, reputation weight,
                         feature vectors and job requisitions)
tests/                   per-node + API + integration + adversarial fixtures,
                         fully offline (653 tests)
Dockerfile               non-root image with /healthz healthcheck
.github/workflows/ci.yml offline pytest on 3.11/3.12
```

## Roadmap (historical PI summary)

- **Engine M0/M1 (done):** 7-node pipeline, conservative calibration, SQLite
  report store + outcome loop, API hardening, two domains, Docker + CI.
- **PI-1 Candidate data backbone (done):** extraction schema + extractor,
  candidate store (SQLAlchemy/Alembic), API + engine wiring, India
  normalization.
- **PI-2 Fabrication defense (done):** AI-text signals · cross-field forensics ·
  resume-farm detection · fused advisory `fabrication_risk`.
- **PI-3 Evaluation ledger (done):** schema + DPDP consent · ledger APIs ·
  coding-round results · Bayesian cross-company reputation (records, coding
  rounds and reputation since removed).
- **PI-4 ML feature store & ranking (done):** feature registry ·
  point-in-time materialization · ranking engine.
- **PI-5 Demand side (in progress):** job requisitions, role-conditioned
  matching and role board; compensation intelligence has been removed.
- **PI-6 candidate side & intake · PI-7 verification & assessment depth ·
  PI-8 scale & learning** — shaped, not started.
