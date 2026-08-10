# depth-eval-engine — End-to-End Requirements

Architect's requirements catalog for taking the engine from the working M0
prototype to a production-grade service. FLOW.md documents *how the current
code works*; this document defines *what the product must do* and the milestone
path to get there.

---

## 1. Vision & problem statement

Recruiters and hiring managers cannot reliably distinguish a candidate who has
*done* GenAI/data engineering work from one who has *read about it*. Keyword
screens reward vocabulary, not depth. The engine evaluates each resume claim
the way a senior engineer would — does the claim **cohere** with the
infrastructure, data, and access the candidate would actually have needed? —
and produces an **advisory, explainable** report with targeted probe questions
for the interview.

**Product stance (invariants — these never change):**

| # | Invariant | Enforcement |
|---|-----------|-------------|
| I1 | Advisory only — never auto-reject | `Report.advisory=True`, `human_review_required=True`, hardcoded |
| I2 | Explainability mandatory — no bare fake/real label | Schema has no such field; every verdict carries score + confidence + evidence + reasoning + probes |
| I3 | Conservative calibration — false positives are the existential risk | Flag only when coherence low AND confidence high; uncertain → DEFER |
| I4 | Consent-clean (DPDP) — first-party data only | Only candidate-shared resume + URLs; no third-party scraping |
| I5 | Domain-agnostic core | Graph never imports a domain; registry lookup by `state.domain` |
| I6 | Flywheel — every evaluation is future training data | Claim→probe→verdict→outcome records, outcome closable later |
| I7 | Degrades gracefully without an LLM key | `NullLLM` + deterministic rule path; test suite fully offline |

## 2. Users & primary flows

- **Recruiter / hiring platform (API consumer)** — submits a resume (+ optional
  first-party GitHub/portfolio URLs), receives a `Report`, shows the human
  reviewer the flagged/deferred claims, evidence, and probe questions.
- **Human reviewer** — reads the report, asks the probes in a screen, then
  **closes the loop** by recording an outcome per claim (genuine / fabricated /
  clarified / inconclusive).
- **Domain author (internal engineer)** — adds a new evaluation domain as one
  Python module implementing `DomainModel`, zero graph changes.
- **ML engineer (future)** — consumes the flywheel dataset to calibrate
  thresholds and train better plausibility models.

## 3. Functional requirements

### 3.1 Evaluation pipeline (M0 — done, kept as regression surface)

- **FR-1** `POST /evaluate` accepts `resume_text` or `resume_pdf_b64` (at least
  one), optional `github_url`, `portfolio_url`, and `domain` (default `genai`);
  returns a persisted `Report`.
- **FR-2** Pipeline stages: ingest → claim_extraction → provenance →
  plausibility → probe_generation → scoring → report, communicating only
  through `EvaluationState`.
- **FR-3** Per-claim verdict: `coherence_score`, `confidence`,
  `status ∈ {COHERENT, INCOHERENT, DEFER, UNVERIFIED}`, reasoning,
  expected/missing signals, evidence trail, probe questions. Status assigned
  only in scoring (calibration in exactly one place).
- **FR-4** Aggregate: confidence-weighted `depth_score`, `overall_confidence`,
  `depth_band` (INSUFFICIENT_SIGNAL when confidence < 0.50).
- **FR-5** Provenance grounds only anchored claims against first-party GitHub
  repos; failures are non-fatal (best-effort grounding).

### 3.2 Persistence & the outcome loop (M1)

- **FR-6** Reports are persisted to a durable store (SQLite at M1; the store is
  a `Protocol` so Postgres is a drop-in later). `GET /report/{id}` survives a
  process restart.
- **FR-7** `POST /report/{report_id}/outcome` records a human outcome
  `{outcome, claim_id?, notes?}` where
  `outcome ∈ {verified_genuine, verified_fabricated, candidate_clarified, inconclusive}`.
  - With `claim_id`: outcome applies to that claim (404/422 if unknown).
  - Without: outcome applies to the whole report.
  - Each outcome is persisted AND appended to the flywheel
    (`record_type="outcome"`), closing the I6 loop. Since S8.5 the flywheel
    record carries the label and its provenance but **not** `notes` — that sink
    has no erasure path.
  - `notes` is bounded by `max_outcome_notes_chars` (S8.5), on this route and
    its org-plane twin alike.
- **FR-8** `GET /report/{report_id}/outcomes` lists recorded outcomes.
- **FR-7a / FR-8a** (S8.5) `POST /screening/reports/{report_id}/outcome` and
  `GET /screening/reports/{report_id}/outcomes` are the **org-plane** twins:
  same body and same refusals, scoped to reports the calling organisation
  commissioned (404 — never 403 — otherwise), and the GET returns that
  organisation's own judgments only. Every outcome records `recorded_by`
  (`operator | organization`), `org_id` and `recorded_by_org_user_id`.

### 3.3 API surface & operability (M1)

- **FR-9** `GET /domains` lists registered domains (key + display name +
  claim types).
- **FR-10** `GET /healthz` reports `{status, version, env, llm_mode
  (live|null), domains[]}` — enough for a load balancer AND a human to see the
  service's effective mode.
- **FR-11** Input caps (config-driven): `max_resume_chars` (default 200k),
  `max_pdf_b64_chars` (default ~14M ≈ 10 MB PDF). Oversize → 422, never OOM.
- **FR-12** Unknown domain → 422 **before** the graph runs, with the list of
  registered domains in the error.
- **FR-13** Every response carries an `X-Request-ID` (generated or propagated
  from the request); the ID is bound into every structlog line for that
  request; one access-log line per request with latency.
- **FR-14** Unhandled errors return a generic JSON 500 (no stack trace / no
  internals on the wire); the full exception is logged with the request ID.
- **FR-15** Optional shared-secret auth: when `DEE_API_AUTH_KEY` is set, all
  endpoints except `/healthz` and `/` require a matching `X-API-Key` header
  (401 otherwise). Unset (default) = open, for local/dev.

### 3.4 Domain plug-ins (M1 proves it, M2 scales it)

- **FR-16** The reusable signal-rule machinery (`SignalRule`, keyword presence
  scoring, contradiction 'tells') lives in the domain layer's shared module —
  NOT inside `genai.py` — so every domain builds on it.
- **FR-17** Heuristic (LLM-free) claim-type hints are provided **by the
  domain** (`DomainModel.heuristic_type_hints()`), not hardcoded in the graph
  layer. This removes the current genai leak in `claim_extraction.py` and
  makes the offline fallback work for every domain.
- **FR-18** A second domain, `data_eng` (Data Engineering), ships with ≥3
  signal rules (ETL/batch pipelines, streaming, warehouse/modeling), its own
  claim taxonomy, prompts, and a contradiction 'tell' — proving I5 end to end.
- **FR-19 (M2)** Additional domains: cloud/infra, backend. Same one-file
  recipe.

### 3.5 LLM usage (M1 hardening, M2 quality)

- **FR-20** All inference via OpenRouter (OpenAI-wire), tier-resolved from
  config (`parsing`/`reasoning`/`reasoning_hard`/`bulk`); a model swap is a
  config change only.
- **FR-21** Client-level resilience: configured retries (`llm_max_retries`,
  default 2) and per-call timeout; any LLM failure degrades that node to its
  deterministic path (never a 500 caused by a provider blip).
- **FR-22 (M2)** Real embedding model for retrieval (dedicated embedder, never
  a chat tier), config-switchable from the M0 `HashingEmbedding`.
- **FR-23 (M2)** Recorded-fixture tests for the LLM JSON paths (extraction +
  plausibility), so prompt/parse regressions are caught offline.

### 3.6 Flywheel & learning loop (M2/M3)

- **FR-24 (M2)** Flywheel export tooling: join evaluation records with outcome
  records into a training table.
- **FR-25 (M3)** Threshold calibration job: given labeled outcomes, recompute
  `flag_*` / `defer_*` thresholds to hold false-positive rate under a target.

## 4. Non-functional requirements

- **NFR-1 Reliability:** no single claim/node failure kills an evaluation;
  partial results with `errors[]` beat a 500. LLM/provider outage → rule-only
  mode (I7).
- **NFR-2 Performance:** offline (rule-only) evaluation p95 < 2s for a 5-page
  resume; LLM path bounded by `llm_timeout_seconds × sequential LLM nodes`.
  (Per-claim LLM concurrency is an M2 optimization.)
- **NFR-3 Security:** secrets only via env/.env (never YAML/code/logs);
  optional API-key gate (FR-15); no PII in log lines beyond report/claim IDs;
  generic 500s (FR-14).
- **NFR-4 Privacy (DPDP):** first-party data only (I4); resume text is NOT
  persisted in the report store — only claims/verdicts derived from it; the
  store supports delete-by-report-id for erasure requests.
- **NFR-5 Observability:** structured JSON logs (prod) with request IDs;
  per-request access log with status + latency; startup log states effective
  mode (llm live/null, store paths).
- **NFR-6 Testability:** entire suite runs offline and hermetic (fakes for
  LLM/GitHub/stores; `DEE_CONFIG_FILE` isolation); every new endpoint and
  service has tests; CI runs on every push.
- **NFR-7 Portability:** runs identically via `uvicorn` locally and in the
  provided Docker image; config identical across (YAML + env overrides).
- **NFR-8 Extensibility:** new domain = 1 file + registration import; new
  report store / flywheel sink = implement the Protocol; new model = config.

## 5. Milestones

| Milestone | Contents | Status |
|-----------|----------|--------|
| **M0** | 7-node pipeline, genai domain, conservative calibration, offline tests | ✅ done |
| **M1 — production hardening** | FR-6..FR-18, FR-20..21, NFR-1/3/5/6/7: persistent store, outcome loop, API hardening, request-ID observability, shared rule machinery, `data_eng` domain, Docker + CI | ← this iteration |
| **M2 — quality & scale** | more domains, real embeddings, recorded LLM fixtures, per-claim LLM concurrency, flywheel export | next |
| **M3 — learning loop** | threshold calibration from outcomes, model fine-tuning on flywheel data | later |
| **M4 — platform** | Postgres store, rate limiting, multi-tenant auth, dashboard | later |

## 6. Acceptance criteria (M1)

1. `pytest -q` green, fully offline, including new tests for: report store
   round-trip + restart survival (new store instance, same file), outcome
   endpoint (report-level, claim-level, unknown-claim 422, unknown-report
   404), input caps (413/422 on oversize), unknown domain 422, auth
   (401 without key when configured, open when not), `data_eng` evaluation
   producing typed claims + rule verdicts offline, request-ID header present.
2. Live local smoke test (no API key): server starts, `POST /evaluate` →
   report persisted; process restart → `GET /report/{id}` still returns it;
   outcome POST → flywheel JSONL contains the outcome record.
3. `docker build` succeeds (verified where Docker is available; CI otherwise).
4. FLOW.md / README.md updated to match the shipped behavior.

## 7. Out of scope (explicitly)

- Auto-reject or any automated hiring decision (violates I1 — never).
- Scraping LinkedIn/third-party profiles (violates I4 — never).
- A UI (API-first; dashboard is M4).
- Queue/worker architecture — synchronous evaluation is fine at current scale;
  revisit when p95 or volume demands it.
