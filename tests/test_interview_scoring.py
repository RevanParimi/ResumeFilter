"""Deterministic rubric. Every dimension is neutral-when-unknown: a scorer that
confuses "no yardstick" with "shallow answer" punishes candidates for gaps in
the question bank."""

from datetime import datetime, timezone
import json
from pathlib import Path

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


def test_specificity_requires_content_beyond_vague_claims(s, profile):
    vague = ("I worked on the model and made it better for the users over "
             "several months with the team and it went well overall")
    concrete = ("I fine-tuned PyTorch on 8 A100 GPUs for 14 hours, cut p99 "
                "latency from 900 ms to 220 ms and dropped cost by 40 percent")
    assert (score_turn(transcript=concrete, expected_signals=[], profile=profile,
                       settings=s).dimensions["specificity"]
            > score_turn(transcript=vague, expected_signals=[], profile=profile,
                         settings=s).dimensions.get("specificity", 0.0))


def test_ownership_recognizes_claimed_actions_and_keeps_team_or_unknown_neutral(s, profile):
    mine = ("I traced the regression to a tokenizer change, I rewrote the "
            "batching path and I shipped the fix behind a flag that week")
    ours = ("we traced the regression to a tokenizer change, we rewrote the "
            "batching path and our team shipped the fix behind a flag")
    neither = ("the regression came from a tokenizer change; the batching path "
               "was rewritten and the fix shipped behind a flag that week")
    assert score_turn(transcript=mine, expected_signals=[], profile=profile,
                      settings=s).dimensions["ownership"] == 1.0
    assert score_turn(transcript=ours, expected_signals=[], profile=profile,
                      settings=s).dimensions["ownership"] == 0.5
    assert score_turn(transcript=neither, expected_signals=[], profile=profile,
                      settings=s).dimensions["ownership"] == 0.5


def test_depth_rewards_reasoning_stages_over_literal_signal_share(s, profile):
    answer = ("I compared GPU checkpoint logs; I pinned the dataset version; "
              "replay tests confirmed recovery")
    score = score_turn(transcript=answer,
                       expected_signals=["gpu", "dataset", "eval harness"],
                       profile=profile, settings=s)
    assert score.dimensions["depth"] == 1.0


def test_depth_is_neutral_when_the_question_has_no_yardstick(s, profile):
    answer = "I built the thing and then I rebuilt it after it fell over twice in production"
    score = score_turn(transcript=answer, expected_signals=[], profile=profile, settings=s)
    assert score.dimensions["depth"] == 0.5


def test_consistency_does_not_treat_a_profile_name_as_independent_corroboration(s, profile):
    known = ("At Acme I moved the PyTorch training job onto spot instances and "
             "handled the preemption restarts myself over that quarter")
    unknown = ("At a client I cannot name I moved the training job onto spot "
               "instances and handled the preemption restarts myself")
    assert score_turn(transcript=known, expected_signals=[], profile=profile,
                      settings=s).dimensions["consistency"] == 0.5
    # Neither a repeated profile term nor an unnamed client proves truth/falsehood.
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


def test_legacy_aggregate_means_and_version_are_preserved(s):
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
    assert a.scorer_version == "s73.1"


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


def test_keyword_repetition_never_earns_a_strong_band(s):
    python = CandidateProfile(skills=[SkillItem(name="Python", canonical="python")])
    answer = "I Python 123 retrieval " * 20
    score = score_turn(transcript=answer, expected_signals=["retrieval"], profile=python, settings=s)
    turns = [_turn(i, score, word_count(answer)) for i in range(1, 4)]
    result = aggregate(session_id="s", candidate_id="c", questions=_questions(3),
                       turns=turns, proxy=ProxyRisk(), settings=s)
    assert result.band not in (InterviewBand.SOLID, InterviewBand.DEEP)
    assert result.confidence < s.interview_min_confidence


RUBRIC = json.loads((Path(__file__).parent / "fixtures/interview_rubric_v2.json").read_text(encoding="utf-8"))


def _content_assessment(text, s, *, signals=None, question=None, profile=None):
    score = score_turn(transcript=text, expected_signals=signals if signals is not None else RUBRIC["signals"],
        question_text=question if question is not None else RUBRIC["question"], profile=profile, settings=s)
    turn = _turn(1, score, word_count(text)).model_copy(update={"transcript": text})
    return score, aggregate(session_id="s", candidate_id="c", questions=_questions(1),
                            turns=[turn], proxy=ProxyRisk(), settings=s)


@pytest.mark.parametrize("case", RUBRIC["cases"], ids=lambda case: case["id"])
def test_frozen_development_examples(s, case):
    score, result = _content_assessment(case["text"], s)
    assert score.scorer_version == RUBRIC["version"] == SCORER_VERSION
    if case["usable"]:
        assert not score.insufficient
        assert result.band in (InterviewBand.SOLID, InterviewBand.DEEP)
        assert result.confidence >= s.interview_min_confidence
    else:
        assert result.band is InterviewBand.INSUFFICIENT_SIGNAL
        assert result.confidence < s.interview_min_confidence


def test_padding_and_repetition_do_not_raise_content_confidence(s):
    answer = RUBRIC["cases"][1]["text"]
    score, result = _content_assessment(answer, s)
    for padded in (answer * 10, answer + " wonderful excellent impressive " * 30,
                   RUBRIC["question"] * 5 + answer):
        repeated, aggregate_score = _content_assessment(padded, s)
        assert repeated.dimensions == score.dimensions
        assert repeated.evidence_confidence == score.evidence_confidence
        assert aggregate_score.confidence == result.confidence


def test_substantive_clause_credit_is_not_a_punctuation_preference(s):
    separate = RUBRIC["cases"][0]["text"]
    combined = separate.replace("; ", " and ")
    a, _ = _content_assessment(separate, s)
    b, _ = _content_assessment(combined, s)
    assert b.dimensions == a.dimensions
    assert b.evidence_confidence == a.evidence_confidence


def test_repetition_or_filler_cannot_cross_a_single_clause_word_floor(s):
    answer = "I compared restored cut tokenizer regression."
    base, original = _content_assessment(answer, s)
    for padded in (answer * 20, answer + " wonderful excellent impressive " * 30):
        score, result = _content_assessment(padded, s)
        assert score.evidence_confidence == base.evidence_confidence
        assert result.confidence == original.confidence
        assert result.band is InterviewBand.INSUFFICIENT_SIGNAL


def test_unrelated_or_limited_turns_never_inflate_an_otherwise_partial_assessment(s):
    good, _ = _content_assessment(RUBRIC["cases"][1]["text"], s)
    unrelated, _ = _content_assessment(RUBRIC["cases"][6]["text"], s)
    limited, _ = _content_assessment("I compared restored cut tokenizer regression." * 20, s)
    before = aggregate(session_id="s", candidate_id="c", questions=_questions(3),
        turns=[_turn(1, good)], proxy=ProxyRisk(), settings=s)
    after = aggregate(session_id="s", candidate_id="c", questions=_questions(3),
        turns=[_turn(1, good), _turn(2, unrelated), _turn(3, limited)], proxy=ProxyRisk(), settings=s)
    assert after.coverage == 1.0 and before.coverage < 1
    assert after.dimensions == before.dimensions
    assert after.overall == before.overall and after.confidence == before.confidence


def test_profile_word_overlap_is_not_independent_consistency_evidence(s, profile):
    answer = RUBRIC["cases"][1]["text"]
    plain, _ = _content_assessment(answer, s)
    named, _ = _content_assessment(answer, s, profile=profile)
    assert plain.dimensions == named.dimensions
    assert named.dimensions["consistency"] == 0.5


def test_non_software_content_and_concise_answers_are_usable(s):
    _, result = _content_assessment("Compared stock records; replaced duplicate orders; follow-up checks confirmed fewer shortages.",
        s, signals=["inventory", "orders"], question="How did you resolve duplicate stock orders?")
    assert result.band in (InterviewBand.SOLID, InterviewBand.DEEP)


def test_missing_yardstick_is_neutral_and_unrelated_relevance_is_uncertain(s):
    score, _ = _content_assessment(RUBRIC["cases"][1]["text"], s, signals=[])
    assert score.dimensions["depth"] == 0.5
    unrelated, result = _content_assessment(RUBRIC["cases"][6]["text"], s)
    assert unrelated.dimensions["depth"] == 0.5
    assert "relevance_unconfirmed" in unrelated.codes
    assert result.band is InterviewBand.INSUFFICIENT_SIGNAL


def test_mixed_score_versions_do_not_create_a_confident_new_assessment(s):
    legacy = _turn(1, TurnScore(dimensions=dict.fromkeys(("depth", "ownership"), 1.0)))
    current_score, _ = _content_assessment(RUBRIC["cases"][1]["text"], s)
    current = _turn(2, current_score)
    result = aggregate(session_id="s", candidate_id="c", questions=_questions(2),
        turns=[legacy, current], proxy=ProxyRisk(), settings=s)
    assert result.dimensions == {} and result.confidence == 0
    assert result.band is InterviewBand.INSUFFICIENT_SIGNAL
    assert "mixed" in result.scorer_version
    assert len(result.scorer_version) <= 16  # Existing persisted version column.


def test_lowered_confidence_setting_cannot_turn_unknown_relevance_into_a_strong_band(s):
    lowered = s.model_copy(update={"interview_min_confidence": 0.0})
    for answer in (RUBRIC["cases"][6]["text"], "I Python 123 retrieval " * 20):
        _, result = _content_assessment(answer, lowered)
        assert result.band is InterviewBand.INSUFFICIENT_SIGNAL


def test_unrelated_answer_is_not_rescued_by_a_missing_signal_yardstick(s):
    score, result = _content_assessment(RUBRIC["cases"][6]["text"], s, signals=[])
    assert score.dimensions["depth"] == 0.5
    assert result.band is InterviewBand.INSUFFICIENT_SIGNAL
    assert "relevance_unconfirmed" in score.codes


def test_profile_template_accepts_substance_without_repeating_a_tool_or_failure_word(s, profile):
    from app.interview.questions import SKILL_TEMPLATE, DEPTH_MARKERS
    _, result = _content_assessment(
        "I compared checkpoint logs; I restored the tokenizer version; replay checks confirmed recovery.",
        s, question=SKILL_TEMPLATE.format(skill="PyTorch"), signals=["pytorch", *DEPTH_MARKERS], profile=profile)
    assert result.band in (InterviewBand.SOLID, InterviewBand.DEEP)


def test_profile_template_does_not_accept_a_generic_investigation_cue_as_relevance(s, profile):
    from app.interview.questions import SKILL_TEMPLATE, DEPTH_MARKERS
    _, result = _content_assessment(RUBRIC["cases"][6]["text"], s,
        question=SKILL_TEMPLATE.format(skill="PyTorch"), signals=["pytorch", *DEPTH_MARKERS], profile=profile)
    assert result.band is InterviewBand.INSUFFICIENT_SIGNAL
