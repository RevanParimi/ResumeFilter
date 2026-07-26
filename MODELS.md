# MODELS.md — model slots, config knobs & live-verified pricing (2026-07-26)

Decision record for the model slots current and future PIs need. All slots are
**config knobs** in `config.yaml` (env-overridable via `DEE_*`) so model choices
flip with business needs, not code changes. Researched via web + the **live
OpenRouter catalog/API** on 2026-07-26; re-verify pricing at each slot's spec
time. Standing stance: cheapest model that holds quality; every LLM step keeps
a deterministic fallback; all outputs advisory + human-reviewed.

**Language scope (user decision 2026-07-26): English-first.** Launch vertical is
IT jobs (English resumes/interviews, Indian accents). Hinglish/code-switch and
regional languages are a deferred phase — revisit with media/entertainment
verticals. Accented-English ASR is an easier, cheaper target than code-switch.

## Active text tiers (config keys: `model_*`) — LIVE-VERIFIED 2026-07-26

| Tier (key) | Model | OpenRouter $/1M in/out | Rationale |
|---|---|---|---|
| `model_reasoning` | **deepseek/deepseek-v3.2** | $0.269 / $0.400 | 2026 value king; ~5x/11x cheaper than qwen3.7-max on the common decisive path. Swapped in + live-pinged OK 2026-07-26; full live pipeline smoke result in the verification log below |
| `model_reasoning_hard` | qwen/qwen3.7-max | $1.475 / $4.425 | Retained as the hard-escalation hatch only |
| `model_fast` (parsing) | qwen/qwen3.6-flash | $0.188 / $1.125 | Unchanged; non-decisive passes |
| `model_bulk` | qwen/qwen3.6-35b-a3b | $0.140 / $1.000 | Unchanged; unused until flywheel re-scoring |
| watch | moonshotai/kimi-k3 | $3.000 / $15.000 | Flagship; open weights 2026-07-27 — re-check for cheaper third-party hosting ~2 weeks after before considering for decisive calls |

## Future slots (inert until their sprint; keys live in config.yaml today)

| Slot (key) | Needed by | Default | Alternates | Notes |
|---|---|---|---|---|
| `model_scoring` | S7.3 interview scoring | **deepseek/deepseek-v3.2** | kimi-k3 if quality demands | Long transcripts → value tier is right; advisory + human-reviewed |
| `speech_provider` | S7.3 | **openrouter** | sarvam · local | **Key finding: OpenRouter serves audio models on the EXISTING account — no new signup for v0.** Sarvam (₹30/hr ASR) is the *India data-residency* option for production DPDP posture, not a dev necessity. `local` = self-host GPU at PI-8 scale |
| `asr_model` | S7.3 | **mistralai/voxtral-small-24b-2507** ($0.10/$0.30 + audio; open-weights → same model self-hostable later; **live-pinged OK**) | google/gemini-2.5-flash-lite (≈$0.03–0.10/hr audio, cheapest hosted); nemotron-3-nano-omni **:free** for dev; local: Qwen3-ASR 1.7B (Apache 2.0); Sarvam "saarika"; deferred Hinglish: Srota fine-tune | Evaluate on Indian-accented English samples, not just benchmarks |
| `tts_model` | S7.3 | **kokoro-82m** (local, near-free, Indian-English preset) | Orpheus-3B (richer, ~200ms); hosted: Sarvam "bulbul" ₹15–30/10K chars | OpenRouter has **no TTS** — TTS is local-first |
| `embedding_model` | PI-8 (helps PI-4/5) | **qwen/qwen3-embedding-0.6b** | 8B variant (quality); BGE-M3 | Top open family on MTEB v2; NOT on OpenRouter — self-host or provider TBD at S8.1 |
| `reranker_model` | PI-5/8 search | **qwen/qwen3-reranker-0.6b** | — | Adopt only if ranking quality demands |

## Verification log

- 2026-07-26: OpenRouter `/models` catalog pulled live (345 models; 24
  audio-capable). `deepseek/deepseek-v3.2` and `voxtral-small-24b-2507`
  round-trip pinged through the project key: both LIVE. Offline suite 442 green
  after the tier swap. Full live pipeline smoke (`scripts/smoke_s24.py`) on the
  new reasoning model: **10/10 OK, exit 0** — claim extraction → plausibility
  (4 verdicts) → scoring (depth 0.759/0.779, band solid) → fabrication fusion
  all clean on deepseek-v3.2; genuine resume fused `low`; `/evaluate` intact.
  Windows note: config.yaml comments must stay ASCII-safe — the YAML source
  reads in cp1252 and bytes like 0x90 (in a left-arrow char) crash Settings load.

**User actions still open:** none mandatory for v0 (OpenRouter covers speech).
Optional: Sarvam account only when production data-residency becomes real;
re-check kimi-k3 pricing ~2026-08-10.

**Sources:** OpenRouter live API (2026-07-26) · MarkTechPost open-ASR 2026 ·
QwenLM/Qwen3-ASR · HF Srota Hinglish fine-tune · BentoML open-TTS/embeddings
2026 guides · Milvus embedding comparison · VentureBeat/Interconnects Kimi K3 ·
OpenRouter kimi-k3 page · Sarvam api-pricing.
