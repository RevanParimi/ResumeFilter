"""ai_signals node: deterministic path, LLM fusion, caps, and wiring."""

import json

from app.graph.build import _PIPELINE
from app.graph.nodes.ai_signals import make_ai_signals_node
from app.graph.state import EvaluationState
from app.schemas.fabrication import AILikelihoodBand, SignalSource
from tests.conftest import FakeLLM, make_services


async def test_deterministic_path_flags_ai_resume(services, ai_resume):
    node = make_ai_signals_node(services)  # services carries NullLLM
    out = await node(EvaluationState(resume_text=ai_resume))
    a = out["ai_generation"]
    assert a.band is AILikelihoodBand.LIKELY
    assert all(s.source is SignalSource.DETERMINISTIC for s in a.signals)
    assert len(a.signals) >= 2
    assert a.advisory is True


async def test_no_text_produces_no_assessment(services):
    node = make_ai_signals_node(services)
    assert await node(EvaluationState()) == {}
    assert await node(EvaluationState(resume_text="   ")) == {}


async def test_llm_pass_fuses_and_confidence_is_capped(settings, ai_resume):
    # A dissenting LLM (reads human) pulls the fused likelihood DOWN, but its
    # confidence contribution is capped at 0.75 so it cannot dominate.
    script = {"RESUME:": json.dumps({
        "likelihood": 0.1, "confidence": 0.99,
        "indicators": ["varied sentence rhythm"], "reasoning": "reads human",
    })}
    services = make_services(settings, llm=FakeLLM(script, settings))
    node = make_ai_signals_node(services)
    out = await node(EvaluationState(resume_text=ai_resume))
    a = out["ai_generation"]
    llm_signals = [s for s in a.signals if s.source is SignalSource.LLM]
    assert llm_signals and "varied sentence rhythm" in llm_signals[0].detail
    assert "[llm] reads human" in a.reasoning
    # deterministic ~0.94@0.90 fused with 0.1@0.75 -> pulled down but > 0.4
    assert 0.4 < a.likelihood < 0.9


async def test_llm_alone_cannot_reach_likely(settings, genuine_resume):
    # Genuine resume: no deterministic tells fire. Even a screaming LLM must
    # not produce LIKELY (conservative gate: >=2 deterministic tells required).
    script = {"RESUME:": json.dumps({
        "likelihood": 0.95, "confidence": 0.95,
        "indicators": ["uniform phrasing"], "reasoning": "very ai",
    })}
    services = make_services(settings, llm=FakeLLM(script, settings))
    node = make_ai_signals_node(services)
    out = await node(EvaluationState(resume_text=genuine_resume))
    assert out["ai_generation"].band is not AILikelihoodBand.LIKELY


async def test_llm_garbage_degrades_to_deterministic(settings, ai_resume):
    services = make_services(settings, llm=FakeLLM({"RESUME:": "not json"}, settings))
    node = make_ai_signals_node(services)
    out = await node(EvaluationState(resume_text=ai_resume))
    a = out["ai_generation"]
    assert a.band is AILikelihoodBand.LIKELY
    assert all(s.source is SignalSource.DETERMINISTIC for s in a.signals)


def test_pipeline_wires_ai_signals_after_ingest():
    names = [name for name, _ in _PIPELINE]
    assert names.index("ai_signals") == names.index("ingest") + 1
