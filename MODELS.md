# MODELS.md — model slots & shortlist (researched 2026-07-26)

Decision record for the model slots future PIs need. Researched live (web) on
2026-07-26 at the user's request; **re-verify pricing/latest versions at each
slot's spec time** — this file records direction, not frozen versions.
Standing stance: OpenRouter + Qwen tiers for text (fast tier for non-decisive
passes); every LLM step keeps a deterministic fallback.

**Language scope (user decision 2026-07-26): English-first.** The launch
vertical is IT jobs, where interviews and resumes are English (Indian-accented).
Hinglish/code-switch and regional languages are a **deferred phase** — revisit
when expanding to verticals like media/entertainment. Practical upside: accented
English ASR is an easier, cheaper target than code-switching.

| Slot | Needed by | Primary | Runner-up / hosted alt | Notes |
|---|---|---|---|---|
| P1 ASR (speech→text, Indian-accented **English**) | S7.3 AI interviews | **Qwen3-ASR 1.7B** (Jan 2026, Apache 2.0; streaming+offline in one model, strong accent robustness, 52 langs) | AI4Bharat indic-conformer-600m; hosted: **Sarvam ASR ₹30/hr** (India-hosted, DPDP-friendly). *Deferred phase:* **Srota** — Hinglish fine-tune of Qwen3-ASR-0.6B (15.85% WER conversational Hinglish) when code-switch support lands | Self-host needs a small GPU (PI-7/8 infra); Sarvam hosted avoids that for v0. Evaluate on Indian-accented English samples, not just benchmarks |
| P2 TTS (interviewer voice, Indian **English**) | S7.3 | **Kokoro-82M** — has an Indian-English voice, low latency, near-free self-host | Orpheus-3B (~200ms streaming, richer); hosted: **Sarvam Bulbul ₹15–30/10K chars** (also covers the deferred multilingual phase) | Audio-first interviews per vision doc |
| P3 Text LLM (scoring/decisive) | S7.3 (+ general) | **Keep Qwen fast tier** for parsing/non-decisive (unchanged). **Kimi K3** (rel. 2026-07-16, 2.8T MoE, 1M ctx; OpenRouter `moonshotai/kimi-k3` @ $3/$15 per M, cached-in $0.30) is the decisive-call candidate | — | K3 open weights due 2026-07-27 → third-party hosting should cut price sharply; **re-check ~2 weeks after** before adopting |
| P4 Embeddings | PI-8 (helps PI-4/5) | **Qwen3-Embedding** — 0.6B (cost) / 8B (quality); top open on MTEB v2, 100+ langs, Apache 2.0 | BGE-M3 (568M, 100+ langs) | Replaces the memory vectorstore fakes at S8.1 |
| P5 Reranker (optional) | PI-5/PI-8 search | **Qwen3-Reranker** (pairs with P4) | — | Adopt only if ranking quality demands it |

**User actions taken/planned (2026-07-26):** create Sarvam account (free
credits) as the DPDP-friendly hosted speech fallback; bookmark Qwen3-ASR /
Srota / Kokoro / Qwen3-Embedding; defer Kimi K3 adoption until post-weights
pricing settles. No OpenRouter config changes through PI-4.

**Sources (retrieved 2026-07-26):** MarkTechPost open-ASR 2026 comparison;
QwenLM/Qwen3-ASR (GitHub); HF forums Srota Hinglish fine-tune; BentoML +
SiliconFlow open-TTS 2026 guides; BentoML/Milvus open-embedding 2026 guides;
VentureBeat + Interconnects Kimi K3 coverage; OpenRouter kimi-k3 pricing page;
Sarvam AI api-pricing.
