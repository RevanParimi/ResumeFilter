"""S7.3 knobs + the one new consent purpose. Band cut-points are knobs (the
ai_*/fr_*/rep_* precedent); scorer internals are NOT (they define what the
number means and are versioned by SCORER_VERSION instead)."""

import pytest

from app.core.config import Settings
from app.ledger.schema import ConsentPurpose


@pytest.fixture
def s(monkeypatch) -> Settings:
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


def test_question_plan_knobs(s):
    assert s.interview_max_questions == 8
    assert s.interview_min_questions == 3
    assert s.interview_session_ttl_minutes == 120


def test_input_caps(s):
    assert s.interview_max_audio_b64_chars == 8_000_000
    assert s.interview_max_answer_chars == 20_000
    assert s.interview_min_answer_words == 12


def test_proxy_rate_knobs_are_generous(s):
    # Human speech is ~2.5 words/sec; 4.0 leaves room for fast speakers.
    assert s.interview_max_words_per_second == 4.0
    assert s.interview_max_typed_words_per_second == 8.0


def test_llm_pass_is_capped(s):
    assert s.interview_llm_max_delta == 0.2
    assert s.interview_llm_excerpt_chars == 4000


def test_band_thresholds_and_weights(s):
    assert s.interview_min_confidence == 0.5
    assert s.interview_deep_threshold == 0.75
    assert s.interview_solid_threshold == 0.55
    assert s.interview_emerging_threshold == 0.35
    assert s.interview_weight_depth == 1.5      # dominant axis
    assert s.interview_weight_specificity == 1.0
    assert s.interview_weight_ownership == 1.0
    assert s.interview_weight_consistency == 1.0


def test_retention_and_speech_knobs(s):
    assert s.ret_interview_session_days == 1095
    assert s.speech_timeout_seconds == 60
    assert s.speech_max_retries == 2


def test_scoring_tier_resolves_to_model_scoring(s):
    assert s.model_for_tier("scoring") == s.model_scoring


def test_interview_read_is_a_new_consent_purpose(s):
    assert ConsentPurpose.INTERVIEW_READ.value == "interview_read"
    # VERIFICATION_READ's redefinition window is closed (ROADMAP watch item):
    # interview disclosure gets its own purpose, not another widening.
    assert ConsentPurpose.INTERVIEW_READ is not ConsentPurpose.VERIFICATION_READ


def test_knob_floors_reject_nonsense(s):
    with pytest.raises(ValueError):
        Settings(_env_file=None, openrouter_api_key="", interview_min_questions=0)
    with pytest.raises(ValueError):
        Settings(_env_file=None, openrouter_api_key="", interview_llm_max_delta=1.5)


def test_the_shipped_config_yaml_agrees_with_the_code_defaults():
    """config.yaml is the deploy surface; a drift between it and the field
    defaults is a silent behaviour change nobody reviews."""
    shipped = Settings(_env_file=None, openrouter_api_key="")
    assert shipped.interview_max_questions == 8
    assert shipped.interview_weight_depth == 1.5
    assert shipped.ret_interview_session_days == 1095
