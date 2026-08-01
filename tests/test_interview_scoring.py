"""Deterministic rubric. Every dimension is neutral-when-unknown: a scorer that
confuses "no yardstick" with "shallow answer" punishes candidates for gaps in
the question bank."""

from datetime import datetime, timezone

import pytest

from app.candidates.schema import CandidateProfile, ExperienceEntry, SkillItem
from app.core.config import Settings
from app.interview.schema import (
    AnswerChannel, InterviewBand, InterviewQuestion, InterviewTurn, ProxyRisk, TurnScore,
)
from app.interview.scoring import (
    SCORER_VERSION, aggregate, band_for, score_turn, word_count,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def s(monkeypatch) -> Settings:
    monkeypatch.setenv("DEE_CONFIG_FILE", "__tests_no_config__.yaml")
    return Settings(_env_file=None, openrouter_api_key="")


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        experience=[ExperienceEntry(employer="Acme", employer_canonical="Acme")],
        skills=[SkillItem(name="PyTorch", canonical="pytorch")],
    )


def _turn(seq: int, score: TurnScore, words: int = 60) -> InterviewTurn:
    return InterviewTurn(
        id=f"t{seq}", sequence=seq, question_id=f"q{seq}", question_text="q",
        question_source="probe", channel=AnswerChannel.TEXT, transcript="x " * words,
        word_count=words, asked_at=NOW, answered_at=NOW, score=score,
    )


def _questions(n: int) -> list[InterviewQuestion]:
    return [InterviewQuestion(id=f"q{i}", sequence=i, text="q", source="probe")
            for i in range(1, n + 1)]


def test_word_count_ignores_pure_punctuation():
    assert word_count("we shipped a low-latency service -- twice") == 6


def test_an_answer_below_the_floor_scores_nothing_rather_than_zero(s, profile):
    score = score_turn(transcript="we did it", expected_signals=["gpu"],
                       profile=profile, settings=s)
    assert score.insufficient is True
    assert score.dimensions == {}
    assert score.codes == ["insufficient_answer"]


def test_specificity_rewards_numbers_and_named_tools(s, profile):
    vague = ("I worked on the model and made it better for the users over "
             "several months with the team and it went well overall")
    concrete = ("I fine-tuned PyTorch on 8 A100 GPUs for 14 hours, cut p99 "
                "latency from 900 ms to 220 ms and dropped cost by 40 percent")
    assert (score_turn(transcript=concrete, expected_signals=[], profile=profile,
                       settings=s).dimensions["specificity"]
            > score_turn(transcript=vague, expected_signals=[], profile=profile,
                         settings=s).dimensions["specificity"])


def test_ownership_prefers_i_over_we_and_is_neutral_when_neither_appears(s, profile):
    mine = ("I traced the regression to a tokenizer change, I rewrote the "
            "batching path and I shipped the fix behind a flag that week")
    ours = ("we traced the regression to a tokenizer change, we rewrote the "
            "batching path and our team shipped the fix behind a flag")
    neither = ("the regression came from a tokenizer change; the batching path "
               "was rewritten and the fix shipped behind a flag that week")
    assert score_turn(transcript=mine, expected_signals=[], profile=profile,
                      settings=s).dimensions["ownership"] == 1.0
    assert score_turn(transcript=ours, expected_signals=[], profile=profile,
                      settings=s).dimensions["ownership"] == 0.0
    assert score_turn(transcript=neither, expected_signals=[], profile=profile,
                      settings=s).dimensions["ownership"] == 0.5


def test_depth_is_the_share_of_expected_signals_actually_covered(s, profile):
    answer = ("I ran it on 8 GPUs for 14 hours over a dataset of 120k rows and "
              "logged every checkpoint so we could compare them properly")
    score = score_turn(transcript=answer,
                       expected_signals=["gpu", "dataset", "eval harness"],
                       profile=profile, settings=s)
    assert score.dimensions["depth"] == pytest.approx(2 / 3, abs=1e-3)


def test_depth_is_neutral_when_the_question_has_no_yardstick(s, profile):
    answer = "I built the thing and then I rebuilt it after it fell over twice in production"
    score = score_turn(transcript=answer, expected_signals=[], profile=profile, settings=s)
    assert score.dimensions["depth"] == 0.5


def test_consistency_corroborates_but_never_punishes(s, profile):
    known = ("At Acme I moved the PyTorch training job onto spot instances and "
             "handled the preemption restarts myself over that quarter")
    unknown = ("At a client I cannot name I moved the training job onto spot "
               "instances and handled the preemption restarts myself")
    assert score_turn(transcript=known, expected_signals=[], profile=profile,
                      settings=s).dimensions["consistency"] == 1.0
    # v0 can corroborate, not contradict: an unrecognised employer stays neutral.
    assert score_turn(transcript=unknown, expected_signals=[], profile=profile,
                      settings=s).dimensions["consistency"] == 0.5


def test_a_missing_profile_leaves_consistency_neutral_rather_than_failing(s):
    answer = "I rebuilt the ingestion path myself after it fell over during the migration"
    score = score_turn(transcript=answer, expected_signals=[], profile=None, settings=s)
    assert score.dimensions["consistency"] == 0.5


def test_band_needs_confidence_before_it_will_assert_anything(s):
    assert band_for(0.95, 0.10, s) is InterviewBand.INSUFFICIENT_SIGNAL
    assert band_for(0.80, 0.90, s) is InterviewBand.DEEP
    assert band_for(0.60, 0.90, s) is InterviewBand.SOLID
    assert band_for(0.40, 0.90, s) is InterviewBand.EMERGING
    assert band_for(0.10, 0.90, s) is InterviewBand.SUPERFICIAL


def test_aggregate_means_each_dimension_and_weights_depth_hardest(s):
    turns = [
        _turn(1, TurnScore(dimensions={"specificity": 1.0, "ownership": 1.0,
                                       "depth": 0.0, "consistency": 1.0})),
        _turn(2, TurnScore(dimensions={"specificity": 1.0, "ownership": 1.0,
                                       "depth": 0.0, "consistency": 1.0})),
    ]
    a = aggregate(session_id="s1", candidate_id="c1", questions=_questions(2),
                  turns=turns, proxy=ProxyRisk(), settings=s)
    assert a.dimensions["depth"] == 0.0
    # depth weighs 1.5 of 4.5 total, so a zero there pulls overall to 3/4.5.
    assert a.overall == pytest.approx(2 / 3, abs=1e-3)
    assert a.scorer_version == SCORER_VERSION


def test_insufficient_turns_count_against_coverage_but_not_the_means(s):
    turns = [
        _turn(1, TurnScore(dimensions={"depth": 1.0})),
        _turn(2, TurnScore(insufficient=True, codes=["insufficient_answer"]), words=3),
    ]
    a = aggregate(session_id="s1", candidate_id="c1", questions=_questions(4),
                  turns=turns, proxy=ProxyRisk(), settings=s)
    assert a.dimensions["depth"] == 1.0        # the empty turn did not drag it down
    assert a.coverage == 0.5                    # 2 answered of 4 planned
    assert a.questions_answered == 2 and a.questions_planned == 4
    assert a.confidence < 0.5                   # low coverage + one thin answer
    assert a.band is InterviewBand.INSUFFICIENT_SIGNAL


def test_an_unanswered_session_asserts_nothing(s):
    a = aggregate(session_id="s1", candidate_id="c1", questions=_questions(1),
                  turns=[], proxy=ProxyRisk(), settings=s)
    assert a.confidence == 0.0 and a.overall == 0.0
    assert a.band is InterviewBand.INSUFFICIENT_SIGNAL
    assert a.advisory is True and a.human_review_required is True


def test_a_full_thorough_session_can_reach_a_real_band(s):
    turns = [_turn(i, TurnScore(dimensions={"specificity": 0.9, "ownership": 0.9,
                                            "depth": 0.9, "consistency": 1.0}))
             for i in range(1, 4)]
    a = aggregate(session_id="s1", candidate_id="c1", questions=_questions(3),
                  turns=turns, proxy=ProxyRisk(), settings=s)
    assert a.coverage == 1.0
    assert a.confidence >= 0.5
    assert a.band is InterviewBand.DEEP
