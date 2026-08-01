"""Interview persistence + audit (S7.3).

Mirrors VerificationStore: every mutation that matters is audited in the SAME
transaction as the write, through LedgerStore._audit, so an interview shows up
in the candidate's own DPDP access log for free.

Start and completion are audited; individual turns are not. A turn is the
candidate acting on their own session, inside a session whose start they can
already see -- a row per answer would flood the very log that exists to make
disclosure legible.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.candidates.models import CandidateRow
from app.core.config import Settings, get_settings
from app.interview.models import InterviewSessionRow, InterviewTurnRow
from app.interview.schema import (
    AnswerChannel, InterviewAssessment, InterviewQuestion, InterviewSession,
    InterviewStatus, InterviewTurn, QuestionSource, TurnScore,
)
from app.interview.session import effective_status
from app.ledger.consent import as_utc
from app.ledger.store import LedgerStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _turn(row: InterviewTurnRow) -> InterviewTurn:
    return InterviewTurn(
        id=row.id,
        sequence=row.sequence,
        question_id=row.question_id,
        question_text=row.question_text,
        question_source=QuestionSource(row.question_source),
        expected_signals=list(row.expected_signals or []),
        channel=AnswerChannel(row.channel),
        transcript=row.transcript or "",
        word_count=row.word_count or 0,
        audio_digest=row.audio_digest,
        audio_duration_seconds=row.audio_duration_seconds,
        asked_at=as_utc(row.asked_at),
        answered_at=as_utc(row.answered_at),
        score=TurnScore(**(row.scores or {})),
    )


def _session(
    row: InterviewSessionRow, turns: Sequence[InterviewTurnRow]
) -> InterviewSession:
    return InterviewSession(
        id=row.id,
        candidate_id=row.candidate_id,
        domain=row.domain,
        report_id=row.report_id,
        status=InterviewStatus(row.status),
        assurance_level_at_start=row.assurance_level_at_start or 0,
        questions=[InterviewQuestion(**q) for q in (row.planned_questions or [])],
        turns=[_turn(t) for t in turns],
        assessment=(InterviewAssessment(**row.assessment) if row.assessment else None),
        started_at=as_utc(row.started_at),
        completed_at=as_utc(row.completed_at) if row.completed_at else None,
        expires_at=as_utc(row.expires_at) if row.expires_at else None,
    )


class InterviewStore:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        ledger: LedgerStore,
        settings: Optional[Settings] = None,
    ) -> None:
        self._session_factory = session_factory
        self._ledger = ledger
        self._settings = settings or get_settings()

    # -- reads -----------------------------------------------------------------

    @staticmethod
    def _turn_rows(session, session_id: str) -> list[InterviewTurnRow]:
        return list(
            session.execute(
                select(InterviewTurnRow)
                .where(InterviewTurnRow.session_id == session_id)
                .order_by(InterviewTurnRow.sequence, InterviewTurnRow.id)
            ).scalars().all()
        )

    def get_session(self, session_id: str) -> Optional[InterviewSession]:
        with self._session_factory() as session:
            row = session.get(InterviewSessionRow, session_id)
            if row is None:
                return None
            return _session(row, self._turn_rows(session, session_id))

    def sessions_for_candidate(self, candidate_id: str) -> list[InterviewSession]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(InterviewSessionRow)
                    .where(InterviewSessionRow.candidate_id == candidate_id)
                    .order_by(InterviewSessionRow.started_at, InterviewSessionRow.id)
                ).scalars().all()
            )
            return [_session(r, self._turn_rows(session, r.id)) for r in rows]

    def live_session_for_candidate(
        self, candidate_id: str, *, at: Optional[datetime] = None
    ) -> Optional[InterviewSession]:
        """The candidate's one unfinished, unexpired session, if any. Expiry is
        applied here rather than written, so nothing has to run on a schedule."""
        moment = as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(InterviewSessionRow)
                    .where(
                        InterviewSessionRow.candidate_id == candidate_id,
                        InterviewSessionRow.status == InterviewStatus.IN_PROGRESS.value,
                    )
                    .order_by(
                        InterviewSessionRow.started_at.desc(), InterviewSessionRow.id
                    )
                ).scalars().all()
            )
            for row in rows:
                live = effective_status(
                    InterviewStatus(row.status), as_utc(row.expires_at), at=moment
                )
                if live is InterviewStatus.IN_PROGRESS:
                    return _session(row, self._turn_rows(session, row.id))
            return None

    # -- writes ----------------------------------------------------------------

    def create_session(
        self,
        *,
        candidate_id: str,
        domain: str,
        report_id: Optional[str],
        questions: Sequence[InterviewQuestion],
        assurance_level: int,
        at: Optional[datetime] = None,
    ) -> InterviewSession:
        moment = as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            row = InterviewSessionRow(
                id=str(uuid.uuid4()),
                candidate_id=candidate_id,
                domain=domain,
                report_id=report_id,
                status=InterviewStatus.IN_PROGRESS.value,
                assurance_level_at_start=int(assurance_level),
                planned_questions=[q.model_dump(mode="json") for q in questions],
                assessment=None,
                scorer_version=None,
                started_at=moment,
                expires_at=moment
                + timedelta(minutes=self._settings.interview_session_ttl_minutes),
            )
            session.add(row)
            session.flush()
            self._ledger._audit(
                session,
                actor_type="candidate",
                actor_id=candidate_id,
                action="interview.start",
                entity_type="interview_session",
                entity_id=row.id,
                candidate_id=candidate_id,
                details={
                    "domain": domain,
                    "questions": len(questions),
                    "assurance_level": int(assurance_level),
                },
            )
            session.commit()
            return _session(row, [])

    def add_turn(
        self,
        session_id: str,
        *,
        question: InterviewQuestion,
        channel: AnswerChannel,
        transcript: str,
        word_count: int,
        audio_digest: Optional[str],
        audio_duration_seconds: Optional[float],
        score: TurnScore,
        asked_at: datetime,
        answered_at: datetime,
    ) -> InterviewTurn:
        """Record ONE answered turn. Deliberately unaudited (see the module
        docstring). The audio bytes never reach this method -- only their
        digest does."""
        with self._session_factory() as session:
            if session.get(InterviewSessionRow, session_id) is None:
                raise LookupError(f"unknown interview session: {session_id}")
            answered = session.execute(
                select(func.count())
                .select_from(InterviewTurnRow)
                .where(InterviewTurnRow.session_id == session_id)
            ).scalar_one()
            row = InterviewTurnRow(
                id=str(uuid.uuid4()),
                session_id=session_id,
                sequence=int(answered) + 1,
                question_id=question.id,
                question_text=question.text[:512],
                question_source=question.source.value,
                expected_signals=list(question.expected_signals),
                channel=channel.value,
                transcript=transcript,
                word_count=word_count,
                audio_digest=audio_digest,
                audio_duration_seconds=audio_duration_seconds,
                scores=score.model_dump(mode="json"),
                asked_at=as_utc(asked_at),
                answered_at=as_utc(answered_at),
            )
            session.add(row)
            session.commit()
            return _turn(row)

    def complete_session(
        self,
        session_id: str,
        *,
        assessment: InterviewAssessment,
        at: Optional[datetime] = None,
    ) -> InterviewSession:
        moment = as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            row = session.get(InterviewSessionRow, session_id)
            if row is None:
                raise LookupError(f"unknown interview session: {session_id}")
            row.status = InterviewStatus.COMPLETED.value
            row.completed_at = moment
            row.assessment = assessment.model_dump(mode="json")
            row.scorer_version = assessment.scorer_version
            self._ledger._audit(
                session,
                actor_type="system",
                actor_id=None,
                action="interview.complete",
                entity_type="interview_session",
                entity_id=row.id,
                candidate_id=row.candidate_id,
                details={
                    "band": assessment.band.value,
                    "answered": assessment.questions_answered,
                    "planned": assessment.questions_planned,
                    "proxy_band": assessment.proxy.band.value,
                },
            )
            session.commit()
            return _session(row, self._turn_rows(session, session_id))
