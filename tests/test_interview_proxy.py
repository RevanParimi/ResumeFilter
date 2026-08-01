"""Proxy hooks: the S7.1 assurance number plus behaviour. No voice biometrics --
that would need a stored voiceprint, which the spine makes impossible on
purpose. Nothing here can CONFIRM a proxy; the band stops at elevated."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.interview.proxy import assess_proxy_risk
from app.interview.schema import AnswerChannel, InterviewTurn, ProxyBand, TurnScore
from app.verification.schema import AssuranceLevel, IdentityAssurance

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def s(monkeypatch) -> Settings:
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


def _assurance(level: AssuranceLevel) -> IdentityAssurance:
    return IdentityAssurance(candidate_id="c1", level=level)


def _turn(seq: int, *, channel=AnswerChannel.AUDIO, words=40, seconds=30.0) -> InterviewTurn:
    return InterviewTurn(
        id=f"t{seq}", sequence=seq, question_id=f"q{seq}", question_text="q",
        question_source="probe", channel=channel, transcript="word " * words,
        word_count=words, asked_at=NOW, answered_at=NOW + timedelta(seconds=seconds),
        score=TurnScore(dimensions={"depth": 0.5}),
    )


def _ids(risk) -> set[str]:
    return {f.id for f in risk.findings}


def _severity(risk, finding_id: str) -> str:
    return next(f.severity for f in risk.findings if f.id == finding_id)


def test_no_assurance_is_a_soft_finding(s):
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.NONE),
                             turns=[_turn(1)], settings=s)
    assert "identity_assurance_none" in _ids(risk)
    assert _severity(risk, "identity_assurance_none") == "soft"


def test_self_attested_only_is_info_not_soft(s):
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.SELF_ATTESTED),
                             turns=[_turn(1)], settings=s)
    assert "identity_assurance_low" in _ids(risk)
    assert "identity_assurance_none" not in _ids(risk)
    assert _severity(risk, "identity_assurance_low") == "info"


def test_contact_control_or_better_raises_no_assurance_finding(s):
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.CONTACT_CONTROL),
                             turns=[_turn(1)], settings=s)
    assert not {"identity_assurance_none", "identity_assurance_low"} & _ids(risk)
    assert risk.assurance_level_at_start == int(AssuranceLevel.CONTACT_CONTROL)


def test_impossibly_fast_speech_is_flagged(s):
    # 200 words in 10 seconds = 20 w/s, far past the 4.0 knob.
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.CONTACT_CONTROL),
                             turns=[_turn(1, words=200, seconds=10.0)], settings=s)
    assert "answer_rate_implausible" in _ids(risk)


def test_a_normal_speaking_rate_is_not_flagged(s):
    # 40 words in 30 seconds = 1.3 w/s.
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.CONTACT_CONTROL),
                             turns=[_turn(1)], settings=s)
    assert "answer_rate_implausible" not in _ids(risk)
    assert risk.band is ProxyBand.LOW


def test_pasted_text_is_flagged_on_its_own_threshold(s):
    risk = assess_proxy_risk(
        assurance=_assurance(AssuranceLevel.CONTACT_CONTROL),
        turns=[_turn(1, channel=AnswerChannel.TEXT, words=300, seconds=5.0)],
        settings=s,
    )
    assert "typed_answer_rate_implausible" in _ids(risk)


def test_a_typed_answer_at_human_speed_is_not_flagged(s):
    # 60 words in 120 seconds = 0.5 w/s.
    risk = assess_proxy_risk(
        assurance=_assurance(AssuranceLevel.CONTACT_CONTROL),
        turns=[_turn(1, channel=AnswerChannel.TEXT, words=60, seconds=120.0)],
        settings=s,
    )
    assert "typed_answer_rate_implausible" not in _ids(risk)


def test_a_text_only_session_says_so_rather_than_hiding_it(s):
    risk = assess_proxy_risk(
        assurance=_assurance(AssuranceLevel.CONTACT_CONTROL),
        turns=[_turn(1, channel=AnswerChannel.TEXT, words=40, seconds=120.0)],
        settings=s,
    )
    assert "text_channel_only" in _ids(risk)
    assert _severity(risk, "text_channel_only") == "info"


def test_band_needs_two_soft_findings_before_it_escalates(s):
    one_soft = assess_proxy_risk(assurance=_assurance(AssuranceLevel.NONE),
                                 turns=[_turn(1)], settings=s)
    assert one_soft.band is ProxyBand.MODERATE

    two_soft = assess_proxy_risk(assurance=_assurance(AssuranceLevel.NONE),
                                 turns=[_turn(1, words=200, seconds=10.0)], settings=s)
    assert two_soft.band is ProxyBand.ELEVATED


def test_the_band_stops_at_elevated_and_stays_advisory(s):
    risk = assess_proxy_risk(
        assurance=_assurance(AssuranceLevel.NONE),
        turns=[_turn(i, words=300, seconds=1.0) for i in range(1, 6)],
        settings=s,
    )
    assert risk.band is ProxyBand.ELEVATED
    assert risk.advisory is True
    assert all(f.severity != "hard" for f in risk.findings)


def test_no_turns_yields_the_assurance_finding_only(s):
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.NONE),
                             turns=[], settings=s)
    assert _ids(risk) == {"identity_assurance_none"}


def test_a_zero_length_turn_does_not_divide_by_zero(s):
    risk = assess_proxy_risk(assurance=_assurance(AssuranceLevel.CONTACT_CONTROL),
                             turns=[_turn(1, words=10, seconds=0.0)], settings=s)
    assert risk.band in (ProxyBand.LOW, ProxyBand.MODERATE)
