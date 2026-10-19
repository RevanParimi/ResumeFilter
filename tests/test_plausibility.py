from app.graph.nodes.plausibility import make_plausibility_node
from app.graph.state import EvaluationState
from app.schemas.claims import CandidateContext, Claim, Specificity

import json

import httpx
import pytest

from app.graph.nodes.provenance import make_provenance_node
from app.graph.nodes.scoring import make_scoring_node
from app.schemas.report import EvidenceSource, Polarity, VerdictStatus
from app.services.github import GitHubClient
from tests.conftest import FakeLLM


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


@pytest.mark.parametrize('mode', [200, 403, 404, 429, 503, 'timeout', 'transport'])
async def test_github_metadata_and_outages_cannot_verify_a_claim(services, mode):
    def handler(request):
        if mode == 'timeout':
            raise httpx.ReadTimeout('upstream detail must remain private', request=request)
        if mode == 'transport':
            raise httpx.ConnectError('upstream detail must remain private', request=request)
        if mode != 200:
            return httpx.Response(mode, json={'message': 'upstream detail must remain private'})
        if request.url.path.endswith('/languages'):
            return httpx.Response(200, json={'Python': 100})
        if request.url.path.endswith('/commits'):
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={'language': 'Python', 'stargazers_count': 4})

    client = httpx.AsyncClient(base_url='https://api.github.com', transport=httpx.MockTransport(handler))
    services.github = GitHubClient(settings=services.settings, client=client)
    try:
        # No domain rule/model opinion: a visible repository or an outage alone
        # cannot turn an unverified claim into a claim assessment.
        claim = Claim(text='Owned a private project', claim_type='unknown')
        state = EvaluationState(claims=[claim], github_url='https://github.com/alice/project')
        state = state.model_copy(update=await make_provenance_node(services)(state))
        state = state.model_copy(update=await make_plausibility_node(services)(state))
        verdict = (await make_scoring_node(services)(state))['verdicts'][0]
        github = [e for e in verdict.evidence if e.source == EvidenceSource.GITHUB]
        assert github, 'fetch context should remain visible to the reviewer'
        assert all(e.polarity == Polarity.NEUTRAL and e.weight == 0 for e in github)
        assert verdict.status == VerdictStatus.UNVERIFIED
        assert verdict.confidence == 0
        assert 'upstream detail must remain private' not in verdict.model_dump_json()
    finally:
        await client.aclose()


@pytest.mark.parametrize("domain,claim_type,text", [
    ("genai", "fine_tuning", "Fine-tuned an open model for our support chatbot."),
    ("data_eng", "etl_pipeline", "Built a daily ingestion pipeline for analytics."),
])
@pytest.mark.parametrize("model_opinion", [False, True])
async def test_repository_context_cannot_change_rules_model_or_claim_scores(
        services, domain, claim_type, text, model_opinion):
    prompts = []

    class CapturingLLM(FakeLLM):
        async def acomplete_json(self, **kwargs):
            prompts.append(kwargs["prompt"])
            return await super().acomplete_json(**kwargs)

    script = {"": json.dumps({"coherence": 0.7, "confidence": 0.8, "reasoning": "Local opinion",
                              "expected_signals": [], "missing_signals": []})} if model_opinion else {}
    services.llm = CapturingLLM(script, settings=services.settings)
    claim = Claim(text=text, claim_type=claim_type)
    state = EvaluationState(domain=domain, claims=[claim])
    node = make_plausibility_node(services)
    baseline = state.model_copy(update=await node(state))
    baseline_verdict = (await make_scoring_node(services)(baseline))["verdicts"][0]
    assert any(e.source == EvidenceSource.RULE for e in baseline_verdict.evidence)
    assert any(e.source == EvidenceSource.LLM for e in baseline_verdict.evidence) == model_opinion
    # Repo names/languages can contain rule keywords and contradiction triggers.
    # Metadata and unavailable diagnostics must never act as technical signals.
    context = state.model_copy(update={
        "provenance": {claim.id: ["Repo synthetic/gpt-4-qlora-a100-eval-airflow-spark-kafka visible."]},
        "provenance_warnings": {claim.id: ["Synthetic commits unavailable (HTTP 429)."]},
    })
    actual = context.model_copy(update=await node(context))
    verdict = (await make_scoring_node(services)(actual))["verdicts"][0]
    assessed = verdict.model_dump()
    assessed["evidence"] = [e for e in assessed["evidence"] if e["source"] != EvidenceSource.GITHUB]
    assert assessed == baseline_verdict.model_dump()
    assert prompts[0] == prompts[1]
    assert "synthetic/gpt-4" not in prompts[1]
    assert "Synthetic commits" not in prompts[1]
    context_evidence = [e for e in verdict.evidence if e.source == EvidenceSource.GITHUB]
    assert {e.ref for e in context_evidence} == {"github.repository_metadata", "github.unavailable"}
    assert all(e.weight == 0 and e.polarity == Polarity.NEUTRAL for e in context_evidence)
