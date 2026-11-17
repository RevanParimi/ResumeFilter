"""The fixed runner preserves partial updates, request isolation and failures."""
import asyncio

import pytest

import app.graph.build as pipeline
from app.schemas.report import Report


def test_partial_updates_replace_values_and_retain_other_fields(services, monkeypatch):
    seen = []

    def factory(name, updates):
        async def step(state):
            seen.append((name, state.resume_text, list(state.errors)))
            return updates(state)
        return lambda services: step

    monkeypatch.setattr(pipeline, "_PIPELINE", [
        ("first", factory("first", lambda state: {"resume_text": state.raw_resume_text, "errors": ["first"]})),
        ("second", factory("second", lambda state: {"errors": ["second"]})),
        ("report", factory("report", lambda state: {"report": Report(summary=state.resume_text + state.errors[0])})),
    ])
    result = asyncio.run(pipeline.EvaluationEngine(services).evaluate(resume_text="input"))
    assert seen == [("first", None, []), ("second", "input", ["first"]), ("report", "input", ["second"])]
    assert result.summary == "inputsecond"


async def test_concurrent_evaluations_keep_independent_state(services, monkeypatch):
    def factory(services):
        async def step(state):
            await asyncio.sleep(0)
            return {"report": Report(summary=state.raw_resume_text)}
        return step
    monkeypatch.setattr(pipeline, "_PIPELINE", [("report", factory)])
    engine = pipeline.EvaluationEngine(services)
    results = await asyncio.gather(engine.evaluate(resume_text="first"), engine.evaluate(resume_text="second"))
    assert [r.summary for r in results] == ["first", "second"]


async def test_step_failure_propagates_and_missing_report_keeps_its_error(services, monkeypatch):
    failure = LookupError("synthetic step failure")
    async def fail(state):
        raise failure
    monkeypatch.setattr(pipeline, "_PIPELINE", [("fail", lambda services: fail)])
    with pytest.raises(LookupError) as raised:
        await pipeline.EvaluationEngine(services).evaluate(resume_text="input")
    assert raised.value is failure
    async def no_report(state):
        return {"errors": ["synthetic diagnostic"]}
    monkeypatch.setattr(pipeline, "_PIPELINE", [("empty", lambda services: no_report)])
    with pytest.raises(RuntimeError, match="pipeline produced no report; errors=\\['synthetic diagnostic'\\]"):
        await pipeline.EvaluationEngine(services).evaluate(resume_text="input")
