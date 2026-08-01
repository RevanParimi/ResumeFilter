"""The state machine. Every gate here exists because a candidate-facing entry
point without one is how S7.1 and S7.2 both got escalations."""

import base64
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.candidates.models import CandidateRow
from app.candidates.schema import (
    CandidateProfile, DateRange, ExperienceEntry, ExtractionResult, SkillItem,
)
from app.interview.questions import NothingToAskError
from app.interview.schema import AnswerChannel, InterviewBand, InterviewStatus
from app.interview.service import AnswerTooLargeError, SessionConflictError
from app.services.speech import SpeechFailed, SpeechUnavailable
from app.verification.schema import VerificationMethod
from tests.conftest import FakeSpeech, make_services

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)

GOOD_ANSWER = (
    "I rebuilt the ingestion path at Acme myself: the nightly PyTorch job kept "
    "failing on 8 GPUs, I traced it to a tokenizer change, and I cut p99 "
    "latency from 900 ms to 220 ms after the rollback"
)
AUDIO_B64 = base64.b64encode(b"not-really-audio-but-valid-base64").decode()


def _ingest(candidates) -> str:
    profile = CandidateProfile(
        experience=[
            ExperienceEntry(employer="Acme Technologies", employer_canonical="Acme",
                            title="ML Engineer",
                            dates=DateRange(start="2021-03", end="2024-01")),
            ExperienceEntry(employer="Globex", employer_canonical="Globex",
                            title="Data Engineer",
                            dates=DateRange(start="2019-01", end="2021-02")),
        ],
        skills=[SkillItem(name="PyTorch", canonical="pytorch"),
                SkillItem(name="Spark", canonical="apache_spark")],
    )
    outcome = candidates.ingest(
        ExtractionResult(profile=profile, method="heuristic"), "resume text")
    return outcome.candidate_id


@pytest.fixture
def svc(settings):
    services = make_services(settings)
    cid = _ingest(services.candidates)
    return services, cid


async def _answer_all(services, cid, session, *, at=NOW):
    """Answer every remaining question; returns the completed session."""
    following = services.interview.next_question(session)
    moment = at
    while following is not None:
        moment = moment + timedelta(seconds=60)
        session, following = await services.interview.answer(
            cid, session.id, question_id=following.id, text=GOOD_ANSWER, at=moment
        )
    return session


def test_start_builds_a_plan_and_stamps_the_current_assurance_level(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    assert session.status is InterviewStatus.IN_PROGRESS
    assert len(session.questions) >= services.settings.interview_min_questions
    assert session.assurance_level_at_start == 0
    assert session.turns == []


def test_start_stamps_a_higher_level_after_the_candidate_self_attests(svc):
    """The proxy hook, end to end: the number S7.1 produces is the number the
    interview records."""
    services, cid = svc
    services.verification.start(cid, VerificationMethod.SELF_ATTESTED, at=NOW)
    session = services.interview.start(cid, at=NOW)
    assert session.assurance_level_at_start == 1


def test_start_refuses_when_there_is_nothing_to_ask(settings):
    services = make_services(settings)
    with services.candidates._session_factory() as s:
        s.add(CandidateRow(id="bare_1"))
        s.commit()
    with pytest.raises(NothingToAskError):
        services.interview.start("bare_1", at=NOW)


def test_start_refuses_an_unknown_candidate(svc):
    services, _ = svc
    with pytest.raises(LookupError):
        services.interview.start("nope", at=NOW)


def test_a_second_start_while_one_is_live_is_a_conflict(svc):
    services, cid = svc
    first = services.interview.start(cid, at=NOW)
    with pytest.raises(SessionConflictError) as exc:
        services.interview.start(cid, at=NOW + timedelta(minutes=1))
    assert first.id in str(exc.value)


def test_a_second_start_is_allowed_once_the_first_expired(svc):
    services, cid = svc
    first = services.interview.start(cid, at=NOW)
    later = NOW + timedelta(
        minutes=services.settings.interview_session_ttl_minutes + 1)
    second = services.interview.start(cid, at=later)
    assert second.id != first.id


async def test_answering_the_current_question_scores_it_and_advances(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    first = session.questions[0]
    session, following = await services.interview.answer(
        cid, session.id, question_id=first.id, text=GOOD_ANSWER,
        at=NOW + timedelta(seconds=90),
    )
    assert len(session.turns) == 1
    assert session.turns[0].channel is AnswerChannel.TEXT
    assert session.turns[0].score.dimensions           # actually scored
    assert following is not None and following.id == session.questions[1].id


async def test_answering_a_question_out_of_turn_is_refused_and_records_nothing(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    with pytest.raises(SessionConflictError):
        await services.interview.answer(
            cid, session.id, question_id=session.questions[1].id, text=GOOD_ANSWER,
            at=NOW,
        )
    assert services.interview.get(cid, session.id).turns == []


async def test_answering_an_expired_session_is_refused(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    later = NOW + timedelta(
        minutes=services.settings.interview_session_ttl_minutes + 1)
    with pytest.raises(SessionConflictError):
        await services.interview.answer(
            cid, session.id, question_id=session.questions[0].id,
            text=GOOD_ANSWER, at=later,
        )


async def test_answering_a_completed_session_is_refused(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    session = await _answer_all(services, cid, session)
    assert session.status is InterviewStatus.COMPLETED
    with pytest.raises(SessionConflictError):
        await services.interview.answer(
            cid, session.id, question_id=session.questions[0].id,
            text=GOOD_ANSWER, at=NOW + timedelta(minutes=30),
        )


async def test_another_candidates_session_is_indistinguishable_from_a_missing_one(svc):
    services, cid = svc
    other = _ingest(services.candidates)
    session = services.interview.start(cid, at=NOW)

    with pytest.raises(LookupError):
        services.interview.get(other, session.id)
    with pytest.raises(LookupError):
        await services.interview.answer(
            other, session.id, question_id=session.questions[0].id,
            text=GOOD_ANSWER, at=NOW,
        )
    assert services.interview.get(cid, session.id).turns == []


async def test_an_audio_answer_with_no_provider_is_refused_and_records_nothing(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    with pytest.raises(SpeechUnavailable):
        await services.interview.answer(
            cid, session.id, question_id=session.questions[0].id,
            audio_b64=AUDIO_B64, mime="audio/wav", at=NOW,
        )
    assert services.interview.get(cid, session.id).turns == []


async def test_an_audio_answer_transcribes_and_keeps_only_the_digest(settings):
    fake = FakeSpeech(text=GOOD_ANSWER, settings=settings)
    services = make_services(settings, speech=fake)
    cid = _ingest(services.candidates)
    session = services.interview.start(cid, at=NOW)

    session, _ = await services.interview.answer(
        cid, session.id, question_id=session.questions[0].id,
        audio_b64=AUDIO_B64, mime="audio/wav", at=NOW + timedelta(seconds=60),
    )
    turn = session.turns[0]
    assert turn.channel is AnswerChannel.AUDIO
    assert turn.transcript == GOOD_ANSWER
    assert turn.audio_digest == hashlib.sha256(
        base64.b64decode(AUDIO_B64)).hexdigest()
    assert turn.audio_duration_seconds == 30.0
    # The payload itself is nowhere in the row.
    assert AUDIO_B64 not in turn.transcript
    assert fake.calls == [(AUDIO_B64, "audio/wav")]


async def test_a_failing_asr_records_no_turn_so_a_retry_is_free(settings):
    services = make_services(
        settings, speech=FakeSpeech(fail=SpeechFailed("upstream down"),
                                    settings=settings))
    cid = _ingest(services.candidates)
    session = services.interview.start(cid, at=NOW)
    with pytest.raises(SpeechFailed):
        await services.interview.answer(
            cid, session.id, question_id=session.questions[0].id,
            audio_b64=AUDIO_B64, mime="audio/wav", at=NOW,
        )
    assert services.interview.get(cid, session.id).turns == []


async def test_an_oversize_audio_body_is_refused_before_any_decode(settings):
    fake = FakeSpeech(settings=settings)
    services = make_services(settings, speech=fake)
    cid = _ingest(services.candidates)
    session = services.interview.start(cid, at=NOW)
    huge = "A" * (settings.interview_max_audio_b64_chars + 1)
    with pytest.raises(AnswerTooLargeError):
        await services.interview.answer(
            cid, session.id, question_id=session.questions[0].id,
            audio_b64=huge, mime="audio/wav", at=NOW,
        )
    assert fake.calls == []          # never handed to a provider


async def test_an_oversize_text_answer_is_refused(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    with pytest.raises(AnswerTooLargeError):
        await services.interview.answer(
            cid, session.id, question_id=session.questions[0].id,
            text="x " * services.settings.interview_max_answer_chars, at=NOW,
        )


async def test_an_answer_with_no_body_is_refused(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    with pytest.raises(ValueError):
        await services.interview.answer(
            cid, session.id, question_id=session.questions[0].id, at=NOW,
        )


async def test_answering_the_last_question_completes_and_stores_an_assessment(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    session = await _answer_all(services, cid, session)

    assert session.status is InterviewStatus.COMPLETED
    assert session.completed_at is not None
    assessment = session.assessment
    assert assessment is not None
    assert assessment.advisory is True and assessment.human_review_required is True
    assert assessment.coverage == 1.0
    assert assessment.questions_answered == len(session.questions)
    assert assessment.proxy.assurance_level_at_start == session.assurance_level_at_start
    assert assessment.scorer_version


async def test_finish_completes_early_with_lower_confidence(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    session, _ = await services.interview.answer(
        cid, session.id, question_id=session.questions[0].id, text=GOOD_ANSWER,
        at=NOW + timedelta(seconds=60),
    )
    done = services.interview.finish(cid, session.id, at=NOW + timedelta(minutes=2))
    assert done.status is InterviewStatus.COMPLETED
    assert done.assessment.coverage < 1.0
    assert done.assessment.band is InterviewBand.INSUFFICIENT_SIGNAL


async def test_finishing_an_already_completed_session_is_a_conflict(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    session = await _answer_all(services, cid, session)
    with pytest.raises(SessionConflictError):
        services.interview.finish(cid, session.id, at=NOW + timedelta(minutes=30))


def test_get_reports_an_expired_session_as_abandoned_without_writing_it(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    later = NOW + timedelta(
        minutes=services.settings.interview_session_ttl_minutes + 1)
    assert services.interview.get(cid, session.id, at=later).status is (
        InterviewStatus.ABANDONED)


async def test_list_for_candidate_returns_summaries_without_transcripts(svc):
    services, cid = svc
    session = services.interview.start(cid, at=NOW)
    await _answer_all(services, cid, session)

    summaries = services.interview.list_for_candidate(cid, at=NOW)
    assert len(summaries) == 1
    dumped = summaries[0].model_dump(mode="json")
    assert "transcript" not in dumped and "turns" not in dumped
    assert GOOD_ANSWER not in str(dumped)
    assert summaries[0].status is InterviewStatus.COMPLETED
