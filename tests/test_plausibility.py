from app.graph.nodes.plausibility import make_plausibility_node
from app.graph.state import EvaluationState
from app.schemas.claims import CandidateContext, Claim, Specificity


async def test_fabricated_finetune_is_incoherent_with_evidence(services, settings):
    claim = Claim(
        text="Fine-tuned GPT-4 to dramatically improve accuracy for our chatbot.",
        claim_type="fine_tuning",
        specificity=Specificity.SPECIFIC,
    )
    state = EvaluationState(
        domain="genai",
        claims=[claim],
        candidate_context=CandidateContext(employer_type="services_firm"),
    )
    v = (await make_plausibility_node(services)(state))["verdicts"][0]

    assert v.coherence_score < settings.flag_coherence_threshold
    assert v.evidence, "verdict must carry an evidence trail (explainability mandate)"
    assert v.missing_signals
    assert v.reasoning


async def test_genuine_finetune_is_coherent(services):
    claim = Claim(
        text=(
            "Fine-tuned Llama-3-8B with QLoRA on a 25,000-example curated dataset; "
            "eval F1 improved 0.71 to 0.84 vs baseline on a held-out test set, 4xA100."
        ),
        claim_type="fine_tuning",
        specificity=Specificity.SPECIFIC,
    )
    state = EvaluationState(domain="genai", claims=[claim])
    v = (await make_plausibility_node(services)(state))["verdicts"][0]
    assert v.coherence_score > 0.6
