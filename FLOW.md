# depth-eval-engine — Execution Flow & Logic

How a request actually moves through the system, what each node computes, and the
exact math/decision rules. Source of truth is the code; file refs are clickable.

---

## Architecture (ASCII)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT (HTTP)                                    │
│            POST /evaluate {resume_text|pdf_b64, github_url?, domain}          │
│            GET  /report/{id}        GET /healthz                              │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                     │
┌───────────────────────────────────▼─────────────────────────────────────────┐
│  API LAYER          app/main.py  (FastAPI + lifespan)                        │
│                     app/api/routes.py  → validates, calls engine, advisory   │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                     │ EvaluationEngine.evaluate(...)
┌───────────────────────────────────▼─────────────────────────────────────────┐
│  ENGINE             app/graph/build.py                                       │
│   • build_graph(services) → compiled LangGraph (linear)                      │
│   • holds one Services bundle + the active domain registry                   │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                     │ ainvoke(EvaluationState)
                                     │
   EvaluationState (app/graph/state.py) ── threaded through every node ──┐
                                     │                                    │
┌────────────────────────────────────────────────────────────────────────┼────┐
│  LANGGRAPH PIPELINE  (app/graph/nodes/*)        each node returns a partial   │
│                                                  dict merged into the state    │
│                                                                                │
│  ① ingest ──► ② claim_extraction ──► ③ provenance ──► ④ plausibility ──►       │
│                                                          ⑤ probe_generation ──►│
│                                                          ⑥ scoring ──► ⑦ report│
│                                                                                │
│  ① parse PDF/text                              (LLM-free)                      │
│  ② atomic typed claims        ──uses──► LLM(parsing) + DomainModel guidance    │
│  ③ ground anchored claims     ──uses──► GitHub + VectorStore                   │
│  ④ THE CORE: rules ⊕ LLM      ──uses──► DomainModel.rules + LLM(reasoning)     │
│  ⑤ probes for suspicious      ──uses──► LLM(reasoning) + DomainModel           │
│  ⑥ calibrate → status+depth   ──uses──► core/calibration (thresholds)         │
│  ⑦ assemble Report + log      ──uses──► Flywheel                              │
└───────┬───────────────┬───────────────┬───────────────┬───────────────┬──────┘
        │               │               │               │               │
        ▼               ▼               ▼               ▼               ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌──────────────┐
│  DOMAINS      │ │  SERVICES     │ │  SERVICES     │ │  SERVICES     │ │  SERVICES    │
│ domains/base  │ │ services/llm  │ │ vectorstore   │ │ github        │ │ flywheel     │
│  DomainModel  │ │ OpenRouterLLM │ │ Chroma /      │ │ httpx GitHub  │ │ JSONL sink   │
│  + Rule + reg │ │  (OpenAI SDK) │ │ InMemory      │ │  API (1st-    │ │ (claim→probe │
│ domains/genai │ │ tiers→models  │ │ Hashing embed │ │  party only)  │ │  →verdict→   │
│  3 seed rules │ │ NullLLM(no key)│ │               │ │               │ │  outcome)    │
└───────┬───────┘ └───────┬───────┘ └───────────────┘ └───────────────┘ └──────────────┘
        │                 │
        │                 ▼  OpenRouter (https://openrouter.ai/api/v1)
        │            ┌──────────────────────────────────────────────┐
        │            │ reasoning      → qwen/qwen3.7-max             │
        │            │ reasoning_hard → qwen/qwen3.7-max (override)  │
        │            │ parsing (FAST) → qwen/qwen3.6-flash           │
        │            │ bulk           → qwen/qwen3.6-35b-a3b (unused)│
        │            └──────────────────────────────────────────────┘
        │
        ▼  registry lookup by state.domain (NEVER hardcoded in the graph)
   get_domain("genai") → rules_for(claim), extraction/plausibility/probe prompts

┌──────────────────────────────────────────────────────────────────────────────┐
│  CORE (cross-cutting)   app/core/                                             │
│   config.py      env-driven Settings (DEE_*): models, thresholds, paths       │
│   calibration.py classify() + aggregate_depth()  ← conservative decision math │
│   logging.py     structlog (JSON/console), routes stdlib deps                 │
└──────────────────────────────────────────────────────────────────────────────┘

OUTPUT: Report {verdicts[], depth_band, depth_score, confidence,
                flagged_ids, deferred_ids, advisory=True, human_review_required=True}
```

Notes: the 7 nodes run in sequence and fan *out* to services/domains — nodes never
call each other, they communicate only through `EvaluationState`. The graph layer
never imports `genai`; it resolves a `DomainModel` at runtime via `state.domain`.
No LLM key → `NullLLM` and every node falls back to deterministic logic.

---

## Project tree (annotated)

```
depth-eval-engine/
│
├── config.yaml                  ← non-sensitive config (committed): models, thresholds, paths
├── .env                         ← SECRETS ONLY (gitignored): OPENROUTER_API_KEY, GITHUB_TOKEN
├── pyproject.toml               ← deps + pytest config (uv/pip)
├── requirements.txt             ← pip install -r target
├── .gitignore                   ← ignores .env, .venv, caches, .chroma, flywheel.jsonl
├── README.md                    ← run + add-a-domain guide
├── FLOW.md                      ← architecture + node logic + decision factors
│
├── app/
│   │
│   ├── main.py                  ← FastAPI app + lifespan (builds EvaluationEngine once)
│   │
│   ├── api/
│   │   └── routes.py            ← POST /evaluate · GET /report/{id} · GET /healthz
│   │
│   ├── graph/                   ─────────────── ORCHESTRATION (domain-agnostic) ───────────
│   │   ├── build.py             ← wires LangGraph; EvaluationEngine.evaluate()
│   │   ├── state.py             ← EvaluationState (Pydantic) threaded through all nodes
│   │   └── nodes/               ← the 7-stage pipeline (linear)
│   │       ├── ingest.py            ① parse PDF/text                    (LLM-free)
│   │       ├── claim_extraction.py  ② atomic typed claims              → LLM(parsing) + domain
│   │       ├── provenance.py        ③ ground anchored claims           → GitHub + VectorStore
│   │       ├── plausibility.py      ④ THE CORE: rules ⊕ LLM coherence  → domain.rules + LLM(reasoning)
│   │       ├── probe_generation.py  ⑤ probes for suspicious claims     → LLM(reasoning) + domain
│   │       ├── scoring.py           ⑥ calibrate → status + depth band  → core/calibration
│   │       └── report.py            ⑦ assemble Report + log flywheel
│   │
│   ├── domains/                 ─────────────── DOMAIN KNOWLEDGE (pluggable) ──────────────
│   │   ├── base.py              ← DomainModel + Rule interfaces + registry (@register_domain)
│   │   └── genai.py             ← GenAI rules (fine_tuning · rag · multi_agent) + prompts
│   │
│   ├── schemas/                 ─────────────── DATA CONTRACTS ─────────────────────────────
│   │   ├── claims.py            ← Claim, ClaimSet, CandidateContext, Specificity
│   │   └── report.py            ← Report, CoherenceVerdict, Evidence, VerdictStatus, DepthBand
│   │
│   ├── services/               ─────────────── EXTERNAL I/O (injectable) ──────────────────
│   │   ├── llm.py               ← OpenRouterLLM (OpenAI SDK) · NullLLM fallback · tier→model
│   │   ├── vectorstore.py       ← ChromaVectorStore · InMemory · HashingEmbedding
│   │   ├── github.py            ← httpx GitHub API client (first-party repos only)
│   │   └── flywheel.py          ← JSONL sink (claim→probe→verdict→outcome)
│   │
│   └── core/                   ─────────────── CROSS-CUTTING ──────────────────────────────
│       ├── config.py            ← Settings: YAML source + env(DEE_*) + .env, precedence
│       ├── calibration.py       ← classify() + aggregate_depth()  (conservative decision math)
│       └── logging.py           ← structlog (JSON/console)
│
├── data/
│   └── flywheel.jsonl           ← runtime training-data sink (gitignored)
│
└── tests/
    ├── conftest.py              ← offline fixtures: NullLLM/FakeLLM, InMemory stores, FakeGitHub
    ├── fixtures/
    │   ├── genuine_genai_resume.txt
    │   └── fabricated_genai_resume.txt
    └── test_*.py                ← one per node + calibration + integration (20 tests)
```

Layering (top→bottom = request flow): `api` receives → `graph` orchestrates the 7
nodes → nodes reach *sideways* into `domains` (what to check) + `services` (how to
fetch/infer) → `core` supplies config, scoring math, logging. Two independence axes:
`graph/` never imports `genai`; `services/` are injected (real vs. fakes in tests).

---

## Data flow (input → output)

`EvaluationState` grows field-by-field. Legend: `+` field added · `~` field mutated
· `ext` external call · `side-effect` write-out.

```
INPUT  (POST /evaluate)
  { resume_text | resume_pdf_b64 (one required), github_url?, portfolio_url?, domain="genai" }
   │
   ▼
┌─ ① ingest ──────────────────────────────────────────────────────────────────┐
│  in : raw_resume_text | resume_pdf_b64                                        │
│  out: + resume_text  (normalized)   + errors[] (if PDF/empty)                │
└──────────────────────────────────────────────────────────────────────────────┘
   │ resume_text
   ▼
┌─ ② claim_extraction ────────────────────────────────────────────────────────┐
│  in : resume_text, github_url, portfolio_url                                 │
│  out: + claims[]  Claim{ text, claim_type, specificity, external_anchor? }   │
│       + candidate_context { role, employer_type, github_url, … }             │
└──────────────────────────────────────────────────────────────────────────────┘
   │ claims[]
   ▼
┌─ ③ provenance ──────────────────────────────────────────────────────────────┐
│  in : claims[].external_anchor, github_url                                   │
│  ext: GitHub API ─► repo signals ─► VectorStore.add ─► query per claim       │
│  out: + provenance{ claim_id -> [evidence strings] }                         │
└──────────────────────────────────────────────────────────────────────────────┘
   │ claims[] + provenance{}
   ▼
┌─ ④ plausibility (THE CORE) ─────────────────────────────────────────────────┐
│  in : per claim → domain.rules ⊕ LLM(reasoning) ⊕ provenance                 │
│       rule: coherence = 0.30 + 0.55·fraction (− penalties / ± 'tells')       │
│       llm : {coherence, confidence, missing_signals} (conf ≤ 0.85)           │
│       fuse: confidence-weighted blend → (coherence, confidence)              │
│  out: + verdicts[] CoherenceVerdict{ coherence_score, confidence, reasoning, │
│              evidence[], expected/missing_signals, probes(seed) } (no status)│
└──────────────────────────────────────────────────────────────────────────────┘
   │ verdicts[] (scored, unclassified)
   ▼
┌─ ⑤ probe_generation ────────────────────────────────────────────────────────┐
│  in : verdicts where coherence_score < 0.35                                  │
│  ext: LLM(reasoning) scoped to missing_signals                               │
│  out: ~ verdicts[].probes  (augmented; coherent claims untouched)            │
└──────────────────────────────────────────────────────────────────────────────┘
   │ verdicts[] (+ probes)
   ▼
┌─ ⑥ scoring (calibration) ───────────────────────────────────────────────────┐
│  classify(): coh<0.35 AND conf≥0.70 → INCOHERENT │ conf<0.50 → DEFER         │
│              coh≥0.35 → COHERENT │ no evidence → UNVERIFIED                   │
│  out: ~ verdicts[].status                                                    │
│       + depth_score, overall_confidence, depth_band                          │
│         (DEEP≥.80 SOLID≥.60 EMERGING≥.40 else SUPERFICIAL; conf<.50 → INSUFFICIENT)│
└──────────────────────────────────────────────────────────────────────────────┘
   │ verdicts[] (classified) + aggregates
   ▼
┌─ ⑦ report ──────────────────────────────────────────────────────────────────┐
│  side-effect: flywheel.log() one JSONL row/claim { …, outcome: null }        │
│  out: + report (Report)                                                      │
└──────────────────────────────────────────────────────────────────────────────┘
   │
   ▼
OUTPUT  (Report)
  { id, domain, verdicts[]{coherence_score, confidence, status, reasoning,
    evidence[], probes[]}, depth_score, depth_band, overall_confidence,
    flagged_claim_ids[] (INCOHERENT), deferred_claim_ids[] (DEFER),
    advisory=true, human_review_required=true, summary }
```

Status is assigned **only at ⑥** — plausibility produces scores without labels so
the conservative decision lives in exactly one place.

---

## 0. Entry

`POST /evaluate` → [routes.py](app/api/routes.py) builds an `EvaluationState`
([state.py](app/graph/state.py)) and calls `EvaluationEngine.evaluate()`
([build.py](app/graph/build.py)). The engine `ainvoke`s a compiled LangGraph.

The graph is a **linear chain** (no branches), wired in [build.py](app/graph/build.py#L34):

```
START → ingest → claim_extraction → provenance → plausibility
      → probe_generation → scoring → report → END
```

Each node returns a *partial dict*; LangGraph merges it into the single
`EvaluationState` threaded through the chain. Every field is written at most once,
so default LastValue channel semantics are correct (no reducers).

The whole pipeline runs **with or without an LLM key**. No key → `build_llm`
returns `NullLLM` (abstains, returns `""`/`{}`) and every node falls back to its
deterministic path. This is why the test suite is fully offline.

---

## 1. ingest — [ingest.py](app/graph/nodes/ingest.py)

**In:** `raw_resume_text` *or* `resume_pdf_b64`, plus optional `github_url` / `portfolio_url`.
**Logic:**
- If text present → use it. Else base64-decode the PDF and extract text with `pypdf`.
- PDF parse error → record `errors:["pdf_parse_failed: …"]`, return empty text (no crash).
- Empty after strip → `errors:["empty_resume"]`.

**Out:** `resume_text` (normalized). LLM-free, deterministic.

---

## 2. claim_extraction — [claim_extraction.py](app/graph/nodes/claim_extraction.py)

Turns prose into **atomic, typed, checkable claims**.

**Primary path (LLM, `parsing` tier = FAST model):** prompt = the active domain's
`extraction_guidance()`; expects JSON `{candidate_context, claims:[…]}`. Each claim →
`{text, claim_type, specificity, external_anchor?}`.

**Fallback path (heuristic, runs if LLM returns nothing):** [_heuristic_extract](app/graph/nodes/claim_extraction.py#L61)
- Split résumé into lines; drop lines < 12 chars.
- Strip URLs out of the prose *before* classifying (so `.../rag-bot` in a URL
  doesn't get mistaken for a RAG claim).
- `claim_type` = first keyword group matched in `_TYPE_HINTS` (fine_tuning, rag,
  multi_agent, deployment, evaluation, data_pipeline, prompt_engineering). No match → line skipped.
- `specificity`: SPECIFIC if a named entity (`_NAMED`: llama/gpt-/claude/a100/lora/f1/p95…)
  **and** a digit are present; MODERATE if one; VAGUE if neither.
- GitHub URLs in the line → parsed into an `external_anchor {owner, repo}`.

**Consent step:** candidate-shared `github_url` / `portfolio_url` are folded into
`candidate_context` (first-party only — DPDP constraint).

**Out:** `claims: list[Claim]`, `candidate_context`.

---

## 3. provenance — [provenance.py](app/graph/nodes/provenance.py)

Grounds **only anchored claims** against **first-party** GitHub repos (no scraping).

**Logic:**
- Per claim: if it has an `external_anchor.repo`, fetch repo evidence via
  `services.github.gather_repo_evidence(owner, repo)`. Else if the candidate shared a
  top-level `github_url`, use that as soft grounding for the claim. Results cached per `(owner,repo)`.
- Fetched evidence strings are embedded into ChromaDB (`vectorstore.add`), then for
  each claim `vectorstore.query(claim.text, n_results=3)` retrieves the most relevant
  lines and merges them into that claim's grounding.
- Vector store failure is swallowed (`log.warning`) — grounding is best-effort.

**Out:** `provenance: {claim_id → [evidence strings]}`. Empty for claims with no anchor.

---

## 4. plausibility — THE CORE — [plausibility.py](app/graph/nodes/plausibility.py)

For **each claim**, fuse two independent signals into one `(coherence, confidence)`.

### (a) Rule registry — deterministic ([genai.py `_SignalRule.evaluate`](app/domains/genai.py#L65))
For each rule whose `claim_types` match the claim:
- Build a haystack = claim text + excerpt + context notes + provenance.
- Each expected **signal category** (e.g. for fine_tuning: `dataset_source_and_size`,
  `eval_metrics`, `compute`, `method`) is `present` or `missing` by keyword match.
- `fraction = present / total_categories`
- **`coherence = 0.30 + 0.55 * fraction`** → range 0.30 (nothing) … 0.85 (all signals).
- VAGUE specificity → `coherence -= 0.12`.
- **Contradiction override ('tell')** via a detector, e.g.
  [_finetune_contradiction](app/domains/genai.py#L140):
  - Claims fine-tuning a **closed model** (gpt-4/claude/gemini) with no open model named →
    `coherence -= 0.35`, force a high-confidence flag.
  - Employer is `services_firm`/`unknown` **and** no compute named (gpu/a100/lora/cluster) →
    `coherence -= 0.18`.
- `decisiveness = |fraction − 0.5| * 2`; **`confidence = 0.45 + 0.40 * decisiveness`**
  (i.e. all-present or all-absent ⇒ more confident than half-and-half). A fired
  contradiction pins `confidence ≥ 0.85`.
- Emits a `RuleFinding` with reasoning, present/missing signals, and suggested probes.

### (b) LLM domain-expert pass (`reasoning` tier = REASONING model)
- System prompt = domain's `plausibility_system_prompt(context)` (senior-engineer persona
  primed with employer type / role / likely infra access).
- Returns JSON `{coherence, confidence, reasoning, expected_signals, missing_signals}`.
- `confidence` is **capped at 0.85** (`_LLM_MAX_CONFIDENCE`) so one model pass can't dominate.
- Any error / no key → returns `None` (contributes nothing; rules still drive).

### Fusion — [_fuse](app/graph/nodes/plausibility.py#L27)
Confidence-weighted across all `(coherence, confidence)` pairs (rules + LLM):

```
coherence  = Σ(coh·conf) / Σ(conf)          # weighted by each source's confidence
confidence = Σ(conf) / n_sources            # avg confidence, capped at 1.0
```

No signals at all → `(0.5, 0.0)` (neutral, zero confidence). GitHub provenance lines
are attached as supporting/contradicting `Evidence` (weight 0.4; "does not exist" → CONTRADICTS).

**Out:** one `CoherenceVerdict` per claim with `coherence_score`, `confidence`,
`reasoning`, `expected/missing_signals`, full `evidence[]`, seed `probes`.
**Status is NOT decided here** — that's calibration's job.

---

## 5. probe_generation — [probe_generation.py](app/graph/nodes/probe_generation.py)

Only claims with **`coherence_score < flag_coherence_threshold` (default 0.35)** get
LLM-crafted probes (`reasoning` tier), scoped to that claim's `missing_signals`.
Returns 1–3 questions; merged with rule-seeded probes, de-duped, capped at 5.
Coherent claims are skipped (no wasted calls). LLM error → keep the rule-seeded probes.

**Out:** verdicts with probes attached.

---

## 6. scoring — [scoring.py](app/graph/nodes/scoring.py) → [calibration.py](app/core/calibration.py)

No new judgment — applies the **conservative classifier** to each verdict.

### Per-claim status — [classify](app/core/calibration.py#L17)
In order:
1. no evidence → **UNVERIFIED**
2. `confidence < defer_confidence_threshold` (0.50) → **DEFER** (not sure enough to say anything)
3. `coherence < flag_coherence_threshold` (0.35) **AND** `confidence ≥ flag_min_confidence` (0.70) → **INCOHERENT** (the only path that flags)
4. `coherence ≥ 0.35` → **COHERENT**
5. otherwise (low coherence, mid confidence) → **DEFER**

> A claim is flagged **only** when it's clearly incoherent *and* we're confident.
> Every uncertain case defers to a human. False positives are the existential risk.

### Aggregate — [aggregate_depth](app/core/calibration.py#L43)
- `depth_score` = confidence-weighted mean of per-claim coherence.
- `overall_confidence` = mean confidence.
- If `overall_confidence < 0.50` → band = **INSUFFICIENT_SIGNAL** (don't pretend to rate).
- Else band by depth: ≥0.80 **DEEP**, ≥0.60 **SOLID**, ≥0.40 **EMERGING**, else **SUPERFICIAL**.

**Out:** finalized `verdicts`, `depth_score`, `overall_confidence`, `depth_band`.

---

## 7. report — [report.py](app/graph/nodes/report.py)

Assembles the advisory `Report` and feeds the flywheel.

- `flagged_claim_ids` = verdicts with status INCOHERENT; `deferred_claim_ids` = DEFER.
- **Always sets `advisory=True` and `human_review_required=True`** — never auto-rejects (hard constraint #3).
- Human-readable `summary` with counts, depth band, and the advisory disclaimer.
- **Flywheel:** one JSONL record per claim →
  `{evaluation_id, report_id, claim_id, claim_text, claim_type, coherence_score,
  confidence, status, probes, evidence_count, outcome:null}`.
  `outcome` is left open, closed later by a human/hiring signal — the training loop (constraint #6).

**Out:** `report: Report` → returned by the API.

---

## Cross-cutting

- **Domain-agnostic core:** no node imports `genai`. They call `get_domain(state.domain)`
  ([base.py](app/domains/base.py)) for rules + prompt fragments. New domain = one module
  + `@register_domain`, zero graph changes (constraint #1).
- **Tiered LLM** ([llm.py](app/services/llm.py)): `parsing`→FAST, `reasoning`→REASONING,
  `reasoning_hard`→override, `bulk`→BULK. All via OpenRouter (OpenAI-wire-compatible).
  Resolution is config-driven in [config.py `model_for_tier`](app/core/config.py).
- **Explainability:** every verdict carries `evidence[]` + `reasoning` + `missing_signals`
  + `probes`. No bare "fake/real" label exists in the schema (constraint #2).
- **Calibration knobs** are all in `config.yaml` (`flag_*`, `defer_*`) — tune without code.

---

## Configuration & Decision Factors

Two layers ([config.py](app/core/config.py)):
- **`config.yaml`** — all non-sensitive tunables (models, thresholds, paths).
  Committed to git, reviewable, keys = field names (no prefix).
- **`.env`** — secrets ONLY (API keys/tokens), `DEE_`-prefixed, never committed.

Precedence (highest first): `constructor args > env (DEE_*) > .env > config.yaml > defaults`.
So any YAML value can be overridden per-deploy by setting the matching `DEE_*` env var,
and secrets never appear in YAML.

### A. What YOU fill in `.env` (secrets only)

| Variable | Required? | What to set | Default if blank |
|---|---|---|---|
| `DEE_OPENROUTER_API_KEY` | **Required for live LLM** | Your OpenRouter key `sk-or-…` | none → runs rule-only (`NullLLM`) |
| `DEE_GITHUB_TOKEN` | Optional | Read-only GitHub PAT | unauth (works, rate-limited) |

That's it for "must touch." Everything below has a working default — change only
to tune cost/quality/behavior.

### B. Tunables in `config.yaml` (override only to tune)

YAML key (env override = `DEE_<KEY>`):

| `config.yaml` key | Default | Why this default |
|---|---|---|
| `openrouter_base_url` | `https://openrouter.ai/api/v1` | OpenRouter's OpenAI-compatible endpoint |
| `openrouter_app_url` / `_title` | `""` / `depth-eval-engine` | Optional OpenRouter attribution headers |
| `model_reasoning` | `qwen/qwen3.7-max` | Flagship reasoning for claim extraction + plausibility |
| `model_reasoning_hard` | `qwen/qwen3.7-max` | Override slot; point at a stronger model for the hardest cases |
| `model_fast` | `qwen/qwen3.6-flash` | Cheap structural parsing (the `parsing` tier) |
| `model_bulk` | `qwen/qwen3.6-35b-a3b` | Cheapest open-weight; future batch work (unused at M0) |
| `llm_max_tokens` | `4096` | Per-call output cap |
| `llm_timeout_seconds` | `60` | Per-call timeout |
| `github_api_base` | `https://api.github.com` | GitHub REST base (the *token* is a secret in `.env`) |
| `chroma_persist_dir` | `./.chroma` | Vector store on disk |
| `chroma_collection` | `depth-eval-evidence` | Collection name |
| `flywheel_path` | `./data/flywheel.jsonl` | Training-data sink |
| `flag_coherence_threshold` | `0.35` | Below this = potentially incoherent |
| `flag_min_confidence` | `0.70` | Need ≥ this confidence to flag at all |
| `defer_confidence_threshold` | `0.50` | Below this = defer to human, never assert |
| `log_level` | `INFO` | Log verbosity |
| `log_json` | `true` | `true`=JSON (prod), `false`=console (dev) |
| `env` | `local` | `local` \| `staging` \| `prod` |

### C. Key decisions & the rationale (why it's built this way)

| Decision | Choice | Why |
|---|---|---|
| **LLM provider** | OpenRouter via the `openai` SDK | Vendor-neutral + economical; one wire-format reaches many models. Swapping a model = one `config.yaml` line, no code change. |
| **Reasoning model** | `qwen/qwen3.7-max` | Strongest current Qwen; the plausibility verdict quality matters most here. Override `_HARD` to e.g. `anthropic/claude-opus-4-8` through the same client for the hardest claims. |
| **Parsing model** | `qwen/qwen3.6-flash` | Claim extraction is structural, not deep — cheapest fast tier is right. |
| **Bulk model** | `qwen/qwen3.6-35b-a3b` | Cheapest ($0.14/$1.00), open-weight (self-hostable later), MoE-efficient. Heavy models are wrong for high-volume work. |
| **Conservative thresholds** | flag at coherence<0.35 **AND** confidence≥0.70; defer<0.50 | False positives (flagging a real person) are the existential risk. We only assert INCOHERENT when clearly incoherent *and* confident; every uncertain case defers to a human. |
| **Rule ⊕ LLM fusion** | confidence-weighted blend; LLM confidence capped at 0.85 | Deterministic rules give a defensible floor; the LLM adds nuance but can't single-handedly dominate a verdict. |
| **Always advisory** | `advisory=True`, `human_review_required=True`, no auto-reject | Hiring decisions stay human; the engine only surfaces evidence + probes. |
| **Consent-clean** | first-party GitHub/portfolio links only, no scraping | DPDP compliance — only candidate-shared data. |
| **Domain-agnostic core** | graph resolves `DomainModel` by `state.domain` | New domain = one file + `@register_domain`, zero graph changes. |
| **Embeddings** | local `HashingEmbedding` stand-in at M0 | Keeps M0 offline/reproducible. Swap for a real embedding model (separate from the chat tiers) for production retrieval quality. |

### D. Scoring constants (in code, not env — change deliberately)

| Constant | Value | Location |
|---|---|---|
| Rule coherence base / slope | `0.30 + 0.55·fraction` | [genai.py](app/domains/genai.py#L85) |
| Vague-specificity penalty | `−0.12` | [genai.py](app/domains/genai.py#L87) |
| Rule confidence | `0.45 + 0.40·decisiveness` | [genai.py](app/domains/genai.py#L108) |
| Closed-model 'tell' penalty | `−0.35` (confidence pinned ≥0.85) | [genai.py](app/domains/genai.py#L146) |
| LLM confidence cap | `0.85` | [plausibility.py](app/graph/nodes/plausibility.py#L24) |
| Depth bands | DEEP≥0.80, SOLID≥0.60, EMERGING≥0.40, else SUPERFICIAL | [calibration.py](app/core/calibration.py#L63) |

---

## End-to-end example (fabricated résumé, offline)

1. ingest: text in.
2. claim_extraction (heuristic): line *"Fine-tuned GPT-4 to improve accuracy"* →
   `claim_type=fine_tuning`, `specificity=VAGUE` (named model, no digit → actually MODERATE if a number appears).
3. provenance: no anchor → no grounding.
4. plausibility: fine_tuning rule → few signal categories present (`fraction` low →
   `coherence ≈ 0.30–0.41`), **closed-model contradiction fires** → `coherence −0.35`,
   `confidence` pinned ≥ 0.85.
5. probe_generation: coherence < 0.35 → probes like *"Which base model + method (LoRA/QLoRA),
   and on what GPU hardware?"*.
6. scoring: `coherence < 0.35` & `confidence ≥ 0.70` → **INCOHERENT**.
7. report: claim in `flagged_claim_ids`, full evidence + probes, `human_review_required=True`.

This is exactly what [tests/test_integration.py](tests/test_integration.py) asserts:
fabricated → flagged **with evidence**; genuine → **not** flagged.
