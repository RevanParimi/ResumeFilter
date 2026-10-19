"""Whole malformed replies abstain at every consumer, including injected clients."""

from copy import deepcopy
import json

import pytest

from app.candidates.extractor import extract_profile
from app.graph.nodes.ai_signals import make_ai_signals_node
from app.graph.nodes.claim_extraction import make_claim_extraction_node
from app.graph.nodes.plausibility import make_plausibility_node
from app.graph.nodes.probe_generation import make_probe_generation_node
from app.graph.state import EvaluationState
from app.interview.schema import TurnScore
from app.interview.scoring import adjust_with_llm
from app.schemas.claims import Claim
from app.schemas.report import CoherenceVerdict
from app.services.llm import NullLLM


class ReplyLLM(NullLLM):
    """Bypass the text parser to prove consumers enforce their own contracts."""

    def __init__(self, settings, payload):
        super().__init__(settings)
        self.payload = payload

    async def acomplete_json(self, **kw):
        if isinstance(self.payload, Exception):
            raise self.payload
        return deepcopy(self.payload)


COMMON = [None, [], ["x"], "wrong", 42, True, {},
          RuntimeError("synthetic-sensitive-provider-detail")]
BAD_NUMBERS = ["0.9", True, float("nan"), float("inf"), float("-inf"), -0.1, 1.1]
PLAUS = dict(coherence=0.9, confidence=0.9, reasoning="model-only detail",
             expected_signals=["model-only expected"], missing_signals=[])
AI = dict(likelihood=0.9, confidence=0.9, reasoning="model-only detail",
          indicators=["model-only indicator"])


def malformed_scores(valid, numeric_keys, list_keys):
    replies = list(COMMON)
    for key in valid:
        replies.append({k: v for k, v in valid.items() if k != key})
    for key in numeric_keys:
        replies.extend([{**valid, key: raw} for raw in BAD_NUMBERS])
    for key in list_keys:
        replies.extend([{**valid, key: raw} for raw in
                        (None, "characters", {}, ["valid fragment", 3], [False])])
    replies.append({**valid, "reasoning": {"detail": "wrong"}})
    return replies


@pytest.mark.parametrize("payload", malformed_scores(
    PLAUS, ("coherence", "confidence"), ("expected_signals", "missing_signals")))
async def test_invalid_plausibility_is_exact_rule_baseline(services, payload):
    state = EvaluationState(claims=[Claim(
        text="Fine-tuned GPT-4 to improve accuracy", claim_type="fine_tuning")])
    baseline = (await make_plausibility_node(services)(state))["verdicts"][0]
    services.llm = ReplyLLM(services.settings, payload)
    actual = (await make_plausibility_node(services)(state))["verdicts"][0]
    assert actual == baseline
    assert all(e.source.value != "llm" for e in actual.evidence)


@pytest.mark.parametrize("payload", malformed_scores(
    AI, ("likelihood", "confidence"), ("indicators",)))
async def test_invalid_style_is_exact_deterministic_baseline(services, ai_resume, payload):
    state = EvaluationState(resume_text=ai_resume)
    baseline = await make_ai_signals_node(services)(state)
    services.llm = ReplyLLM(services.settings, payload)
    assert await make_ai_signals_node(services)(state) == baseline


@pytest.mark.parametrize("payload", COMMON + [
    {"probes": None}, {"probes": "characters"}, {"probes": {}},
    {"probes": ["valid fragment", {"question": "wrong"}]}, {"probes": [True]},
])
async def test_invalid_probes_keep_only_seeded_questions(services, payload):
    verdict = CoherenceVerdict(claim_id="claim-test", claim_text="Some claim",
        claim_type="generic", coherence_score=0.1, confidence=0.8, probes=["Rule question?"])
    services.llm = ReplyLLM(services.settings, payload)
    result = await make_probe_generation_node(services)(EvaluationState(verdicts=[verdict]))
    assert result["verdicts"][0].probes == ["Rule question?"]


CLAIMS = dict(candidate_context={"years_experience": 3}, claims=[{
    "text": "MODEL ONLY CLAIM", "claim_type": "custom_domain_type", "specificity": "specific"}])
BAD_CLAIMS = COMMON + [{"claims": None}, {"claims": "characters"}, {"claims": {}},
    {**CLAIMS, "claims": [CLAIMS["claims"][0], {"specificity": "specific"}]},
    {**CLAIMS, "claims": [CLAIMS["claims"][0], 4]},
    {**CLAIMS, "candidate_context": None},
    {**CLAIMS, "candidate_context": {"years_experience": "3"}},
    {**CLAIMS, "candidate_context": {"years_experience": float("nan")}},
    {**CLAIMS, "claims": [{"text": "MODEL", "external_anchor": {"url": 3}}]},
    {**CLAIMS, "claims": [{"text": "MODEL", "source_excerpt": []}]},
    {**CLAIMS, "claims": [{"text": "MODEL", "specificity": "wrong"}]},
]
BAD_CLAIMS += [{**CLAIMS, "candidate_context": {"years_experience": raw}}
               for raw in (True, float("inf"), float("-inf"), -1)]


@pytest.mark.parametrize("payload", BAD_CLAIMS)
async def test_invalid_claimset_discards_all_model_fragments(services, genuine_resume, payload):
    state = EvaluationState(resume_text=genuine_resume, github_url="https://github.com/shared")
    baseline = await make_claim_extraction_node(services)(state)
    services.llm = ReplyLLM(services.settings, payload)
    actual = await make_claim_extraction_node(services)(state)
    assert [c.text for c in actual["claims"]] == [c.text for c in baseline["claims"]]
    assert actual["candidate_context"] == baseline["candidate_context"]


PROFILE = dict(full_name={"value": "MODEL ONLY NAME", "confidence": 0.9,
                          "source_excerpt": "MODEL ONLY NAME"},
               contact={}, skills=[{"name": "MODEL ONLY SKILL", "confidence": 0.9}])
BAD_PROFILES = COMMON + [
    {**PROFILE, "skills": raw} for raw in (None, "characters", {}, [42],
        [{"name": "valid fragment", "confidence": 0.9}, {"confidence": 0.9}])
] + [{**PROFILE, "skills": [{"name": "MODEL", "confidence": raw}]} for raw in BAD_NUMBERS]
BAD_PROFILES += [{**PROFILE, "full_name": {"confidence": 0.9}},
    {**PROFILE, "contact": "wrong"},
    {**PROFILE, "projects": [{"name": "MODEL", "confidence": 0.9, "technologies": [3]}]},
    {**PROFILE, "certifications": [{"name": "MODEL", "confidence": 0.9, "year": "2020"}]},
    {**PROFILE, "education": [{"degree": "MODEL", "confidence": 0.9, "grade_value": float("inf")}]},
    {**PROFILE, "experience": [{"title": "MODEL", "confidence": 0.9, "is_current": "false"}]},
    {**PROFILE, "skills": [{"name": "MODEL"}]},
    {**PROFILE, "skills": [{"name": "MODEL", "confidence": 0.9, "source_excerpt": ["wrong"]}]},
    {**PROFILE, "experience": [{"title": "MODEL", "confidence": 0.9, "employment_type": "wrong"}]},
    {**PROFILE, "links": [{"type": "github"}]},
]
BAD_PROFILES += [{**PROFILE, collection: raw}
    for collection in ("education", "experience", "projects", "certifications", "links")
    for raw in (None, "characters", {}, [False], [{"confidence": 0.9}, 42])]


def without_ids(value):
    if isinstance(value, dict):
        return {k: without_ids(v) for k, v in value.items() if k != "id"}
    if isinstance(value, list):
        return [without_ids(v) for v in value]
    return value


@pytest.mark.parametrize("payload", BAD_PROFILES)
async def test_invalid_profile_is_whole_heuristic_result(settings, payload):
    text = "Test Person\ntest@example.com\nSKILLS\nPython, SQL\n"
    baseline = await extract_profile(text, llm=NullLLM(settings))
    actual = await extract_profile(text, llm=ReplyLLM(settings, payload))
    assert actual.method == "heuristic"
    assert without_ids(actual.profile.model_dump()) == without_ids(baseline.profile.model_dump())


@pytest.mark.parametrize("payload", COMMON + [
    {"dimensions": None}, {"dimensions": []}, {"dimensions": "wrong"},
] + [{"dimensions": {"ownership": 0.9, "depth": raw}} for raw in BAD_NUMBERS])
async def test_invalid_interview_adjustment_changes_no_dimensions(settings, payload):
    base = TurnScore(dimensions={"ownership": 0.5, "depth": 0.5}, codes=["rule_code"])
    result = await adjust_with_llm(ReplyLLM(settings, payload), question_text="What did you build?",
        transcript="I built a service", expected_signals=[], base=base, settings=settings)
    assert result == base


async def test_valid_plausibility_preserves_cap_and_evidence(services):
    services.llm = ReplyLLM(services.settings, PLAUS)
    result = await make_plausibility_node(services)(EvaluationState(claims=[Claim(text="Generic claim")]))
    verdict = result["verdicts"][0]
    assert verdict.coherence_score == 0.9 and verdict.confidence == 0.85
    assert verdict.evidence[0].detail == "model-only detail"
    assert verdict.expected_signals == ["model-only expected"]


async def test_valid_claims_preserve_domain_enum_and_shared_links(services):
    services.llm = ReplyLLM(services.settings, CLAIMS)
    actual = await make_claim_extraction_node(services)(EvaluationState(
        domain="data_eng", resume_text="Resume", portfolio_url="https://example.com"))
    claim = actual["claims"][0]
    assert (claim.domain, claim.claim_type, claim.specificity.value) == (
        "data_eng", "custom_domain_type", "specific")
    assert actual["candidate_context"].years_experience == 3
    assert actual["candidate_context"].portfolio_url == "https://example.com"


async def test_valid_probes_merge_and_deduplicate(services):
    services.llm = ReplyLLM(services.settings, {"probes": ["Rule question?", "Model question?"]})
    verdict = CoherenceVerdict(claim_id="claim-test", claim_text="Some claim",
        claim_type="generic", coherence_score=0.1, confidence=0.8, probes=["Rule question?"])
    result = await make_probe_generation_node(services)(EvaluationState(verdicts=[verdict]))
    assert result["verdicts"][0].probes == ["Rule question?", "Model question?"]


async def test_valid_unknown_interview_axis_cannot_introduce_a_dimension(settings):
    base = TurnScore(dimensions={"depth": 0.5})
    result = await adjust_with_llm(ReplyLLM(settings, {"dimensions": {"depth": 1.0, "charisma": 0.9}}),
        question_text="Question", transcript="Answer", expected_signals=[], base=base, settings=settings)
    assert result.dimensions == {"depth": 0.7}
    assert "llm_adjusted" in result.codes


@pytest.mark.parametrize("consumer", ["claims", "profile", "plausibility", "style", "probes", "interview"])
async def test_fallback_logs_do_not_include_provider_payload(services, log_events, consumer):
    services.llm = ReplyLLM(services.settings, RuntimeError("synthetic-sensitive-provider-detail"))
    state = EvaluationState(resume_text="Built production RAG at scale", claims=[Claim(text="Generic claim")])
    if consumer == "claims":
        await make_claim_extraction_node(services)(state)
    elif consumer == "profile":
        result = await extract_profile(state.resume_text, llm=services.llm)
        assert "synthetic-sensitive-provider-detail" not in json.dumps(result.warnings)
    elif consumer == "plausibility":
        await make_plausibility_node(services)(state)
    elif consumer == "style":
        await make_ai_signals_node(services)(state)
    elif consumer == "probes":
        state.verdicts = [CoherenceVerdict(claim_id="claim-test", claim_text="Claim",
            claim_type="generic", coherence_score=0.1, confidence=0.8)]
        await make_probe_generation_node(services)(state)
    else:
        await adjust_with_llm(services.llm, question_text="Question", transcript="Answer",
            expected_signals=[], base=TurnScore(dimensions={"depth": 0.5}), settings=services.settings)
    assert any("llm_failed" in e["event"] for e in log_events)
    assert "synthetic-sensitive-provider-detail" not in json.dumps(log_events)
