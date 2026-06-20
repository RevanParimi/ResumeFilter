# depth-eval-engine

A **domain-agnostic** agent that evaluates a candidate's resume for both
**authenticity** and **technical depth** — the way a senior engineer would. It
does **not** keyword-match. For each claim it reasons about whether the claim
*coheres* with the infrastructure, data, and access the candidate would actually
have needed.

> **Advisory only.** Every result is flagged for human review. The system never
> auto-rejects a candidate. False positives (flagging a real person) are treated
> as the existential risk, so the calibration is conservative: when unsure, it
> **defers** instead of flagging.

M0 ships a single domain (**GenAI engineering**). Adding more domains is one file.

---

## How it works

```
ingest → claim_extraction → provenance → plausibility → probe_generation → scoring → report
```

| Node | Responsibility |
|------|----------------|
| `ingest` | Parse resume (PDF/text); capture first-party github/portfolio URLs. |
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

# Edit .env and set DEE_OPENROUTER_API_KEY for live LLM reasoning.

# Run the tests
pytest -q

# Serve the API
uvicorn app.main:app --reload
# → POST /evaluate, GET /report/{id}, GET /healthz, GET /docs
```

> Without an API key the engine still runs: it falls back to the deterministic
> rule registry (`NullLLM`), which is exactly how the test suite stays offline.

### Example request

```bash
curl -s localhost:8000/evaluate -H 'content-type: application/json' -d '{
  "resume_text": "- Fine-tuned GPT-4 to improve accuracy.\n- Built production RAG at scale.",
  "github_url": "https://github.com/me/my-rag-bot",
  "domain": "genai"
}' | jq '{depth_band, flagged_claim_ids, human_review_required, advisory}'
```

The response is a `Report`: per-claim `CoherenceVerdict`s (score, confidence,
status, evidence, probes), an aggregate `depth_band`, and the always-on
`advisory` / `human_review_required` flags.

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

Override any of them via `DEE_MODEL_*` env vars (e.g. point `reasoning_hard` at
`anthropic/claude-opus-4-8` through the same OpenRouter client when you want it).

---

## Adding a new domain (the M2 path)

The LangGraph core has **zero** domain-specific logic — all of it lives behind
the [`DomainModel`](app/domains/base.py) interface. To add, say, a data-eng domain:

1. Create `app/domains/data_eng.py`:

   ```python
   from app.domains.base import DomainModel, Rule, register_domain

   @register_domain
   class DataEngDomain(DomainModel):
       key = "data_eng"
       display_name = "Data Engineering"

       @property
       def rules(self) -> list[Rule]: ...        # your coherence rules
       @property
       def claim_types(self) -> list[str]: ...   # your claim vocabulary
       def extraction_guidance(self) -> str: ...
       def plausibility_system_prompt(self, ctx) -> str: ...
       def probe_guidance(self) -> str: ...
   ```

2. Register it by importing it from [app/domains/__init__.py](app/domains/__init__.py).

3. Call the API with `"domain": "data_eng"`. Nothing in the graph changes.

A rule is a small, deterministic coherence check — see the three seed rules in
[app/domains/genai.py](app/domains/genai.py) (fine-tuning, production RAG,
multi-agent). The reusable `_SignalRule` lets you express a rule as "which
expected signals are present, and what's the domain-specific tell?".

---

## Data & consent (DPDP)

Only **first-party** data is used: the candidate-provided resume and any
GitHub/portfolio URLs **they** share. The engine never scrapes third-party
profiles.

## Flywheel

Every `(claim → probe → verdict → outcome?)` record is appended to a pluggable
store ([app/services/flywheel.py](app/services/flywheel.py), JSONL by default)
with an open `outcome` field, ready to be closed later by human/hiring feedback
and used for future model training.

---

## Project layout

```
app/
  main.py                FastAPI entrypoint
  api/routes.py          POST /evaluate, GET /report/{id}
  graph/
    state.py             EvaluationState (Pydantic)
    build.py             LangGraph assembly + EvaluationEngine
    nodes/               one module per pipeline node
  domains/
    base.py              DomainModel interface + rule registry
    genai.py             GenAI rules + plausibility prompts (3 seed rules)
  schemas/               claims.py, report.py  (Pydantic v2 contracts)
  services/              llm (OpenRouter) · vectorstore (Chroma) · github · flywheel
  core/                  config · calibration · logging
tests/                   per-node + integration, with genuine & fabricated fixtures
```

## Roadmap

- **M1–M9 (done):** contracts → domain layer → services → calibration → nodes →
  graph → API → tests → docs.
- **Next:** more domains (data-eng, cloud, backend), real embedding model for
  retrieval, persistent report store, LLM-path integration tests with recorded
  fixtures, and closing the flywheel loop with hiring outcomes.
