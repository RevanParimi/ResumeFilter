"""An LLM outage in the two costliest signals must be visible.

Both handlers degrade correctly and said NOTHING, while their siblings
(claim_extraction, probe_generation, provenance) logged the identical failure.
The cause is scope, not judgement: each swallow lives in a module-level
`_llm_assessment` helper while every node binds its logger inside the factory,
so there was no `log` in scope to call.
"""

from __future__ import annotations

import pytest

from app.graph.nodes.ai_signals import _llm_assessment as ai_assess
from app.graph.nodes.plausibility import _llm_assessment as plaus_assess
from app.schemas.claims import CandidateContext, Claim


class _BoomLLM:
    """A vendor outage, which is the case both handlers exist to survive."""

    async def acomplete_json(self, **kw):
        raise RuntimeError("vendor outage")


@pytest.mark.asyncio
async def test_ai_signals_logs_when_the_llm_fails(services, log_events):
    services.llm = _BoomLLM()
    result = await ai_assess(services, "some resume text")
    assert result == (None, [], ""), "the degradation itself must not change"
    assert any(e["event"] == "ai_signals_llm_failed" for e in log_events)


@pytest.mark.asyncio
async def test_plausibility_logs_when_the_llm_fails(services, log_events):
    services.llm = _BoomLLM()
    claim = Claim(text="Fine-tuned an LLM for support triage")
    result = await plaus_assess(services, "genai", claim, CandidateContext(), [])
    assert result == (None, None, [], [], ""), "the degradation itself must not change"
    assert any(e["event"] == "plausibility_llm_failed" for e in log_events)


def test_unmapped_skill_capture_logs_when_curation_fails(services, log_events):
    """Still never fatal -- but a capture queue that has stopped accepting
    anything looks exactly like a taxonomy with nothing left to map."""
    from app.profile_sources.service import ProfileSourceService

    class _BoomCuration:
        def record_unmapped(self, *a, **kw):
            raise RuntimeError("curation down")

    class _Skill:
        canonical = None
        name = "kubernetes"

    class _SourceType:
        value = "github"

    class _Signal:
        skills = [_Skill()]
        source_type = _SourceType()

    svc = ProfileSourceService.__new__(ProfileSourceService)
    svc._curation = _BoomCuration()
    svc._capture_unmapped(_Signal())

    assert any(e["event"] == "unmapped_skill_capture_failed" for e in log_events)
