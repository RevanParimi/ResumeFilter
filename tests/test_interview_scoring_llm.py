"""The LLM may ADJUST a dimension, never decide one. Same stance as S2.1: the
deterministic pass is the score, the model is a nudge with a hard cap."""

import pytest

from app.core.config import Settings
from app.interview.schema import TurnScore
from app.interview.scoring import adjust_with_llm
from app.services.llm import LLMClient, NullLLM
from tests.conftest import FakeLLM


@pytest.fixture
def s(monkeypatch) -> Settings:
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


BASE = TurnScore(dimensions={"specificity": 0.5, "ownership": 0.5,
                             "depth": 0.5, "consistency": 0.5})


async def _adjust(llm: LLMClient, s: Settings, base: TurnScore = BASE) -> TurnScore:
    return await adjust_with_llm(
        llm, question_text="Which GPUs?", transcript="I used 8 A100s for 14 hours",
        expected_signals=["gpu"], base=base, settings=s,
    )


async def test_no_key_leaves_the_deterministic_score_untouched(s):
    out = await _adjust(NullLLM(s), s)
    assert out.dimensions == BASE.dimensions
    assert "llm_adjusted" not in out.codes


async def test_an_adjustment_is_clamped_to_the_max_delta(s):
    llm = FakeLLM({"Which GPUs?": '{"dimensions": {"depth": 1.0}}'}, settings=s)
    out = await _adjust(llm, s)
    assert out.dimensions["depth"] == pytest.approx(0.7)   # 0.5 + the 0.2 cap
    assert "llm_adjusted" in out.codes


async def test_a_downward_adjustment_is_clamped_the_same_way(s):
    llm = FakeLLM({"Which GPUs?": '{"dimensions": {"depth": 0.0}}'}, settings=s)
    out = await _adjust(llm, s)
    assert out.dimensions["depth"] == pytest.approx(0.3)


async def test_scores_stay_inside_0_1_after_adjustment(s):
    base = TurnScore(dimensions={"depth": 0.95})
    llm = FakeLLM({"Which GPUs?": '{"dimensions": {"depth": 5.0}}'}, settings=s)
    out = await _adjust(llm, s, base)
    assert out.dimensions["depth"] == 1.0


async def test_unknown_dimensions_and_junk_values_are_ignored(s):
    llm = FakeLLM(
        {"Which GPUs?": '{"dimensions": {"charisma": 1.0, "depth": "very good"}}'},
        settings=s,
    )
    out = await _adjust(llm, s)
    assert out.dimensions == BASE.dimensions
    assert "charisma" not in out.dimensions


async def test_an_insufficient_answer_is_never_rescued_by_the_model(s):
    base = TurnScore(insufficient=True, codes=["insufficient_answer"])
    llm = FakeLLM({"Which GPUs?": '{"dimensions": {"depth": 1.0}}'}, settings=s)
    out = await _adjust(llm, s, base)
    assert out.dimensions == {} and out.insufficient is True


async def test_a_raising_llm_is_not_an_error(s):
    class Boom(LLMClient):
        async def _araw(self, **kw):
            raise RuntimeError("upstream down")

    out = await _adjust(Boom(s), s)
    assert out.dimensions == BASE.dimensions


async def test_the_scoring_tier_is_the_one_actually_requested(s):
    """A decisive-sounding pass must not quietly bill the reasoning tier."""
    seen: dict = {}

    class Recording(LLMClient):
        async def _araw(self, *, model, system, prompt, max_tokens):
            seen["model"] = model
            return "{}"

    await _adjust(Recording(s), s)
    assert seen["model"] == s.model_scoring
