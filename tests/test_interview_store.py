"""Persistence + audit. Expiry is READ-TIME: the stored status stays
in_progress and `effective_status` derives `abandoned`, because no sweeper
exists and a stored `abandoned` would be a lie nobody corrects (the S7.1 rule)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.candidates.models import CandidateRow
from app.interview.schema import (
    AnswerChannel, InterviewAssessment, InterviewQuestion, InterviewStatus, ProxyRisk,
    TurnScore,
)
from app.interview.session import effective_status
from app.interview.store import InterviewStore
from app.ledger.store import LedgerStore
from tests.conftest import make_candidate_store

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def wiring(settings):
    candidates = make_candidate_store()
    ledger = LedgerStore(candidates._session_factory, settings=settings)
    store = InterviewStore(candidates._session_factory, ledger=ledger, settings=settings)
    return candidates, ledger, store


@pytest.fixture
def candidate_id(wiring):
    candidates, _, _ = wiring
    with candidates._session_factory() as s:
        s.add(CandidateRow(id="cand_1"))
        s.commit()
    return "cand_1"


def _questions(n: int = 2) -> list[InterviewQuestion]:
    return [
        InterviewQuestion(id=f"q{i}", sequence=i, text=f"question {i}", source="probe",
                          expected_signals=["gpu"])
        for i in range(1, n + 1)
    ]


def test_effective_status_derives_abandoned_without_writing_it():
    expires = NOW + timedelta(hours=1)
    assert effective_status(InterviewStatus.IN_PROGRESS, expires, at=NOW) is (
        InterviewStatus.IN_PROGRESS)
    assert effective_status(InterviewStatus.IN_PROGRESS, expires,
                            at=NOW + timedelta(hours=2)) is InterviewStatus.ABANDONED
    # A completed session never expires into abandoned.
    assert effective_status(InterviewStatus.COMPLETED, expires,
                            at=NOW + timedelta(days=9)) is InterviewStatus.COMPLETED


def test_create_session_stores_the_plan_and_stamps_assurance(
    wiring, candidate_id, settings
):
    _, _, store = wiring
    session = store.create_session(
        candidate_id=candidate_id, domain="genai", report_id="rep_1",
        questions=_questions(), assurance_level=2, at=NOW,
    )
    assert session.status is InterviewStatus.IN_PROGRESS
    assert session.assurance_level_at_start == 2
    assert [q.text for q in session.questions] == ["question 1", "question 2"]
    assert session.report_id == "rep_1"
    assert session.expires_at == NOW + timedelta(
        minutes=settings.interview_session_ttl_minutes)


def test_create_session_refuses_an_unknown_candidate(wiring):
    _, _, store = wiring
    with pytest.raises(LookupError):
        store.create_session(candidate_id="nope", domain="genai", report_id=None,
                             questions=_questions(), assurance_level=0, at=NOW)


def test_starting_a_session_is_audited_into_the_candidates_access_log(
    wiring, candidate_id
):
    _, ledger, store = wiring
    store.create_session(candidate_id=candidate_id, domain="genai", report_id=None,
                         questions=_questions(), assurance_level=0, at=NOW)
    actions = [e.action for e in ledger.audit_for_candidate(candidate_id)]
    assert "interview.start" in actions


def test_add_turn_persists_the_transcript_and_the_digest_only(wiring, candidate_id):
    _, _, store = wiring
    session = store.create_session(candidate_id=candidate_id, domain="genai",
                                   report_id=None, questions=_questions(),
                                   assurance_level=0, at=NOW)
    turn = store.add_turn(
        session.id, question=session.questions[0], channel=AnswerChannel.AUDIO,
        transcript="I ran it on 8 A100s", word_count=6, audio_digest="a" * 64,
        audio_duration_seconds=12.0, score=TurnScore(dimensions={"depth": 1.0}),
        asked_at=NOW, answered_at=NOW + timedelta(seconds=30),
    )
    assert turn.transcript == "I ran it on 8 A100s"
    assert turn.audio_digest == "a" * 64
    assert turn.sequence == 1

    reread = store.get_session(session.id)
    assert len(reread.turns) == 1
    assert reread.turns[0].score.dimensions == {"depth": 1.0}
    assert reread.turns[0].channel is AnswerChannel.AUDIO


def test_turns_come_back_in_sequence_order(wiring, candidate_id):
    _, _, store = wiring
    session = store.create_session(candidate_id=candidate_id, domain="genai",
                                   report_id=None, questions=_questions(3),
                                   assurance_level=0, at=NOW)
    for q in reversed(session.questions):
        store.add_turn(session.id, question=q, channel=AnswerChannel.TEXT,
                       transcript="answer", word_count=1, audio_digest=None,
                       audio_duration_seconds=None, score=TurnScore(),
                       asked_at=NOW, answered_at=NOW)
    assert [t.sequence for t in store.get_session(session.id).turns] == [1, 2, 3]


def test_add_turn_refuses_an_unknown_session(wiring, candidate_id):
    _, _, store = wiring
    with pytest.raises(LookupError):
        store.add_turn("nope", question=_questions()[0], channel=AnswerChannel.TEXT,
                       transcript="a", word_count=1, audio_digest=None,
                       audio_duration_seconds=None, score=TurnScore(),
                       asked_at=NOW, answered_at=NOW)


def test_complete_session_stores_the_assessment_and_audits(wiring, candidate_id):
    _, ledger, store = wiring
    session = store.create_session(candidate_id=candidate_id, domain="genai",
                                   report_id=None, questions=_questions(),
                                   assurance_level=0, at=NOW)
    assessment = InterviewAssessment(
        session_id=session.id, candidate_id=candidate_id, questions_planned=2,
        questions_answered=2, proxy=ProxyRisk(), scorer_version="s73.1", overall=0.6,
    )
    done = store.complete_session(session.id, assessment=assessment,
                                  at=NOW + timedelta(minutes=5))
    assert done.status is InterviewStatus.COMPLETED
    assert done.assessment.overall == 0.6
    assert done.completed_at == NOW + timedelta(minutes=5)
    assert "interview.complete" in [
        e.action for e in ledger.audit_for_candidate(candidate_id)
    ]


def test_live_session_ignores_completed_and_expired_ones(wiring, candidate_id):
    _, _, store = wiring
    session = store.create_session(candidate_id=candidate_id, domain="genai",
                                   report_id=None, questions=_questions(),
                                   assurance_level=0, at=NOW)
    assert store.live_session_for_candidate(candidate_id, at=NOW).id == session.id
    # Past its TTL it is no longer live, without anything being written.
    assert store.live_session_for_candidate(
        candidate_id, at=NOW + timedelta(days=1)) is None
    assert store.get_session(session.id).status is InterviewStatus.IN_PROGRESS


def test_sessions_for_candidate_is_scoped_to_one_candidate(wiring, candidate_id):
    candidates, _, store = wiring
    with candidates._session_factory() as s:
        s.add(CandidateRow(id="cand_2"))
        s.commit()
    store.create_session(candidate_id=candidate_id, domain="genai", report_id=None,
                         questions=_questions(), assurance_level=0, at=NOW)
    store.create_session(candidate_id="cand_2", domain="genai", report_id=None,
                         questions=_questions(), assurance_level=0, at=NOW)
    mine = store.sessions_for_candidate(candidate_id)
    assert len(mine) == 1 and mine[0].candidate_id == candidate_id
