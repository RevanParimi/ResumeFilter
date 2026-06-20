"""GenAI domain model — M0's single domain.

Encodes how a senior GenAI engineer reasons about whether a claim COHERES with
the infrastructure, data, and access the candidate would actually have needed.
Three seed rules (fine-tuning, production RAG, multi-agent), written to be
extended: add a ``_SignalRule(...)`` to ``RULES`` or append a new rule class.

This is the ONLY file that knows GenAI specifics. The core never imports it
directly — it arrives through the registry.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.domains.base import DomainModel, Rule, RuleFinding, register_domain
from app.schemas.claims import CandidateContext, Claim, Specificity
from app.schemas.report import Polarity

# Claim-type vocabulary owned by this domain.
CLAIM_TYPES = [
    "fine_tuning",
    "rag",
    "multi_agent",
    "deployment",
    "evaluation",
    "data_pipeline",
    "prompt_engineering",
    "generic",
]


def _present(haystack: str, keywords: tuple[str, ...]) -> bool:
    h = haystack.lower()
    return any(k in h for k in keywords)


class _SignalRule(Rule):
    """A coherence rule expressed as 'which expected signals are present?'.

    Coherence rises with the fraction of expected signal categories evidenced in
    the claim text/excerpt/provenance, falls for vague phrasing, and is
    overridden by domain-specific contradictions (a 'tell').
    """

    def __init__(
        self,
        *,
        id: str,
        claim_types: tuple[str, ...],
        description: str,
        categories: dict[str, tuple[str, ...]],
        probes: dict[str, str],
        contradiction: Optional[
            Callable[[str, CandidateContext], Optional[tuple[float, str, list[str]]]]
        ] = None,
    ) -> None:
        self.id = id
        self.claim_types = claim_types
        self.description = description
        self._categories = categories  # display_name -> keywords
        self._probes = probes          # display_name -> probe question
        self._contradiction = contradiction

    def evaluate(
        self,
        claim: Claim,
        context: CandidateContext,
        provenance: Optional[list[str]] = None,
    ) -> Optional[RuleFinding]:
        if not self.handles(claim):
            return None

        hay = " ".join(
            filter(None, [claim.text, claim.source_excerpt, context.notes, *(provenance or [])])
        )

        present: list[str] = []
        missing: list[str] = []
        for name, kws in self._categories.items():
            (present if _present(hay, kws) else missing).append(name)

        n = len(self._categories)
        fraction = len(present) / n if n else 0.0
        coherence = 0.30 + 0.55 * fraction
        if claim.specificity == Specificity.VAGUE:
            coherence -= 0.12

        reasoning_bits = [
            f"Expected signals present: {present or 'none'}.",
            f"Missing: {missing or 'none'}.",
        ]
        probes = [self._probes[m] for m in missing if m in self._probes]

        # Domain-specific 'tell' override (e.g. fine-tuning a closed model).
        if self._contradiction is not None:
            hit = self._contradiction(hay, context)
            if hit is not None:
                delta, why, extra_probes = hit
                coherence += delta
                reasoning_bits.append(why)
                missing = [*missing, "coherence_contradiction"]
                probes = [*extra_probes, *probes]

        coherence = max(0.0, min(1.0, coherence))

        decisiveness = abs(fraction - 0.5) * 2  # extreme present/absent => decisive
        confidence = 0.45 + 0.40 * decisiveness
        if "coherence_contradiction" in missing:
            confidence = max(confidence, 0.85)
        confidence = max(0.0, min(1.0, confidence))

        if coherence < 0.40:
            polarity = Polarity.CONTRADICTS
        elif coherence > 0.65:
            polarity = Polarity.SUPPORTS
        else:
            polarity = Polarity.NEUTRAL

        return RuleFinding(
            rule_id=self.id,
            polarity=polarity,
            coherence=coherence,
            confidence=confidence,
            reasoning=" ".join(reasoning_bits),
            expected_signals=list(self._categories.keys()),
            missing_signals=missing,
            suggested_probes=probes[:4],
        )


# --- contradiction detectors --------------------------------------------------
_CLOSED_NONFT = ("gpt-4", "gpt-4o", "claude", "gemini", "gpt-3.5")
_OPEN_MODELS = (
    "llama", "mistral", "mixtral", "qwen", "gemma", "falcon", "phi-",
    "bert", "t5", "gpt-2", "gpt-neo", "open-source", "open source",
)


def _finetune_contradiction(
    hay: str, ctx: CandidateContext
) -> Optional[tuple[float, str, list[str]]]:
    closed = _present(hay, _CLOSED_NONFT)
    open_ = _present(hay, _OPEN_MODELS)
    if closed and not open_:
        return (
            -0.35,
            "Claims fine-tuning a closed/hosted model that doesn't expose base "
            "weight fine-tuning — a strong fabrication tell.",
            ["Which exact model + method (full FT / LoRA / QLoRA) did you fine-tune, "
             "and on what hardware?"],
        )
    # Tier-3 services / unknown employer claiming FT with no infra signal.
    if ctx.employer_type in {"services_firm", "unknown", None} and not _present(
        hay, ("gpu", "a100", "h100", "lora", "qlora", "cluster", "deepspeed")
    ):
        return (
            -0.18,
            f"Employer type '{ctx.employer_type}' rarely has sustained GPU access and "
            "no compute is named — fine-tuning is weakly supported here.",
            ["What GPU setup (count/type/duration) did you have access to for this?"],
        )
    return None


# --- the three seed rules -----------------------------------------------------
RULES: list[Rule] = [
    _SignalRule(
        id="genai.fine_tuning.coherence",
        claim_types=("fine_tuning",),
        description="Fine-tuning implies dataset + eval harness + sustained GPU on a "
        "tunable model.",
        categories={
            "dataset_source_and_size": (
                "dataset", "examples", "rows", "samples", "tokens", "labeled",
                "annotat", "curated", "k-example", "instances",
            ),
            "eval_metrics_vs_baseline": (
                "eval", "validation", "baseline", "f1", "accuracy", "bleu",
                "rouge", "held-out", "test set", "benchmark", "perplexity",
            ),
            "sustained_gpu_access": (
                "gpu", "a100", "h100", "v100", "lora", "qlora", "deepspeed",
                "fsdp", "cluster", "8x", "4x",
            ),
            "tunable_open_model": _OPEN_MODELS,
        },
        probes={
            "dataset_source_and_size": "Where did the training data come from and how "
            "many examples after cleaning?",
            "eval_metrics_vs_baseline": "What metric moved, by how much, against which "
            "baseline, on what held-out split?",
            "sustained_gpu_access": "What hardware and wall-clock time did a training "
            "run take?",
            "tunable_open_model": "Which base model and fine-tuning method did you use?",
        },
        contradiction=_finetune_contradiction,
    ),
    _SignalRule(
        id="genai.rag.coherence",
        claim_types=("rag",),
        description="Production RAG implies a named embedding model, chunking, "
        "retrieval eval, and latency/cost handling.",
        categories={
            "named_embedding_model": (
                "embedding", "text-embedding", "ada-002", "e5", "bge", "minilm",
                "sentence-transformers", "voyage", "cohere embed", "gte",
            ),
            "chunking_strategy": (
                "chunk", "splitter", "overlap", "token window", "recursive",
                "semantic split", "passage",
            ),
            "retrieval_eval": (
                "recall@", "precision@", "mrr", "ndcg", "hit rate", "retrieval eval",
                "rerank", "rerankers", "ground truth",
            ),
            "latency_cost_handling": (
                "latency", "p95", "p99", "throughput", "qps", "cache", "cost",
                "token budget", "ms",
            ),
        },
        probes={
            "named_embedding_model": "Which embedding model and dimensionality, and why "
            "that one?",
            "chunking_strategy": "What chunk size/overlap and how did you choose it?",
            "retrieval_eval": "How did you measure retrieval quality (recall@k / MRR) "
            "and what did you get?",
            "latency_cost_handling": "What was end-to-end p95 latency and per-query cost "
            "at scale?",
        },
    ),
    _SignalRule(
        id="genai.multi_agent.coherence",
        claim_types=("multi_agent",),
        description="A multi-agent system in prod implies orchestration, state "
        "management, tool calls, and failure handling.",
        categories={
            "orchestration": (
                "orchestrat", "langgraph", "autogen", "crewai", "supervisor",
                "router", "planner", "state machine", "graph",
            ),
            "state_management": (
                "state", "memory", "checkpoint", "blackboard", "shared context",
                "persistence", "thread",
            ),
            "tool_calls": (
                "tool", "function call", "function-calling", "api call", "retriever",
                "actuator", "tool use",
            ),
            "failure_handling": (
                "retry", "fallback", "timeout", "guardrail", "circuit breaker",
                "error handling", "validation", "human-in-the-loop",
            ),
        },
        probes={
            "orchestration": "What orchestrated the agents and how was control flow "
            "decided at runtime?",
            "state_management": "How was shared state passed and persisted between "
            "agents?",
            "tool_calls": "Which tools did agents call and how were results validated?",
            "failure_handling": "What happened when an agent failed, looped, or timed "
            "out in production?",
        },
    ),
]


@register_domain
class GenAIDomain(DomainModel):
    key = "genai"
    display_name = "Generative AI Engineering"

    @property
    def rules(self) -> list[Rule]:
        return RULES

    @property
    def claim_types(self) -> list[str]:
        return list(CLAIM_TYPES)

    def extraction_guidance(self) -> str:
        return (
            "You are extracting atomic, checkable GenAI engineering claims from a "
            "resume. For each claim, classify claim_type as one of: "
            f"{', '.join(CLAIM_TYPES)}. Set specificity to 'vague' (no concrete "
            "numbers/names), 'moderate', or 'specific' (named models, dataset sizes, "
            "metrics). If a claim points to a GitHub repo or portfolio URL the "
            "candidate shared, attach it as external_anchor. Also infer "
            "candidate_context: role_title, seniority, years_experience, and "
            "employer_type (tier1_ai_lab | product_company | services_firm | startup | "
            "academia | unknown). Do NOT invent facts not present in the resume."
        )

    def plausibility_system_prompt(self, context: CandidateContext) -> str:
        return (
            "You are a senior GenAI engineer assessing whether a resume claim COHERES "
            "with the infrastructure, data, and access the candidate would actually "
            "have needed. You do NOT keyword-match. You reason about whether the claim "
            "hangs together.\n\n"
            "Candidate context:\n"
            f"  role: {context.role_title or 'unknown'} ({context.seniority or '?'})\n"
            f"  experience: {context.years_experience or '?'} yrs\n"
            f"  employer: {context.employer_name or '?'} "
            f"[{context.employer_type or 'unknown'}]\n\n"
            "For the given claim, decide: what would a genuine version exhibit "
            "(expected_signals)? Which of those are absent (missing_signals)? Is there "
            "a contradiction with the candidate's likely access (e.g. a Tier-3 services "
            "role claiming sustained GPU fine-tuning)? Output a coherence score 0..1, a "
            "confidence 0..1, and concise reasoning. Be CONSERVATIVE: when evidence is "
            "thin, lower confidence rather than asserting fabrication. This is advisory "
            "input for a human reviewer, never an automated rejection."
        )

    def probe_guidance(self) -> str:
        return (
            "Write 1-3 targeted follow-up questions that a genuine practitioner answers "
            "instantly but a fabricator cannot survive. Anchor each question to a "
            "specific missing signal (dataset provenance, eval methodology, hardware, "
            "orchestration, failure modes). Avoid yes/no questions and avoid anything "
            "answerable by restating the resume."
        )
