"""Interview orchestration (S7.3).

This is a CANDIDATE-INITIATED entry point, so the gates live HERE rather than in
the route. The S7.1/S7.2 lesson is that a gate applied at one entry point and
not the other is this codebase's recurring bug shape, and a service-level gate
holds for a direct caller too. In order:

1. ONE LIVE SESSION. Concurrent sessions would make both attempt counting and
   the timing-based proxy signals meaningless.
2. OWNERSHIP. Every method resolves the session from (candidate_id, session_id);
   another candidate's session is indistinguishable from a missing one.
3. CURRENT QUESTION. An answer must name the question it answers, so two racing
   clients cannot collapse into one turn.
4. LIVE SESSION ONLY. Expired (read-time) and completed sessions refuse answers.
5. SIZE, BEFORE DECODE. An oversize body is refused before base64 is expanded.

Nothing here can auto-reject: the output is an advisory assessment.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from datetime import datetime, timezone
from typing import Optional

from app.candidates.store import CandidateStore
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.domains.base import get_domain
from app.interview.proxy import assess_proxy_risk
from app.interview.questions import build_question_plan
from app.interview.schema import (
    AnswerChannel, InterviewBand, InterviewQuestion, InterviewSession, InterviewStatus,
    InterviewSummary, ProxyBand,
)
from app.interview.scoring import adjust_with_llm, aggregate, score_turn, word_count
from app.interview.session import effective_status
from app.interview.store import InterviewStore
from app.ledger.consent import as_utc
from app.ledger.store import LedgerStore
from app.services.llm import LLMClient
from app.services.speech import SpeechClient
from app.verification.schema import AssuranceLevel, IdentityAssurance

log = get_logger(__name__)


class SessionConflictError(Exception):
    """The session is not in a state that accepts this action -- one is already
    live, this one is finished or expired, or the answer names the wrong
    question. Maps to 409."""


class AnswerTooLargeError(Exception):
    """The submitted answer exceeds its cap. Checked BEFORE any base64 decode,
    so an oversize payload is never expanded in memory."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewService:
    def __init__(
        self,
        store: InterviewStore,
        candidates: CandidateStore,
        ledger: LedgerStore,
        report_store,
        *,
        verification,
        llm: LLMClient,
        speech: SpeechClient,
        settings: Optional[Settings] = None,
    ) -> None:
        self._store = store
        self._candidates = candidates
        self._ledger = ledger
        self._report_store = report_store
        self._verification = verification
        self._llm = llm
        self._speech = speech
        self._settings = settings or get_settings()

    # -- candidate plane -------------------------------------------------------

    def start(
        self,
        candidate_id: str,
        *,
        domain_key: str = "genai",
        at: Optional[datetime] = None,
    ) -> InterviewSession:
        """Plan an interview and open a session. Raises NothingToAskError when
        there is too little on file to ask anything meaningful -- refusing beats
        conducting an empty interview and scoring the silence."""
        moment = as_utc(at) if at else _utcnow()
        if self._candidates.get_candidate(candidate_id) is None:
            raise LookupError(f"unknown candidate: {candidate_id}")

        live = self._store.live_session_for_candidate(candidate_id, at=moment)
        if live is not None:
            raise SessionConflictError(
                f"an interview is already in progress: {live.id}"
            )

        report = self._latest_report(candidate_id)
        questions = build_question_plan(
            profile=self._candidates.latest_profile(candidate_id),
            report=report,
            domain=get_domain(domain_key),
            limit=self._settings.interview_max_questions,
            minimum=self._settings.interview_min_questions,
        )
        assurance = self._verification.assurance_for_candidate(candidate_id, at=moment)
        return self._store.create_session(
            candidate_id=candidate_id,
            domain=domain_key,
            report_id=report.id if report is not None else None,
            questions=questions,
            assurance_level=int(assurance.level),
            at=moment,
        )

    async def answer(
        self,
        candidate_id: str,
        session_id: str,
        *,
        question_id: str,
        text: Optional[str] = None,
        audio_b64: Optional[str] = None,
        mime: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> tuple[InterviewSession, Optional[InterviewQuestion]]:
        """Record and score ONE answer. Returns (session, next_question); the
        next question is None once the session has completed.

        A speech failure propagates BEFORE any row is written, so a retry is
        free and a vendor outage never costs a candidate their answer.
        """
        moment = as_utc(at) if at else _utcnow()
        session = self._owned(candidate_id, session_id)
        status = effective_status(session.status, session.expires_at, at=moment)
        if status is not InterviewStatus.IN_PROGRESS:
            raise SessionConflictError(f"this interview is {status.value}")

        current = self._next_question(session)
        if current is None:
            raise SessionConflictError("every question has already been answered")
        if question_id != current.id:
            raise SessionConflictError(
                f"answer question {current.id}; {question_id} is not the current one"
            )

        channel, transcript, digest, duration = await self._resolve_answer(
            text=text, audio_b64=audio_b64, mime=mime
        )

        profile = self._candidates.latest_profile(candidate_id)
        score = score_turn(
            transcript=transcript,
            expected_signals=current.expected_signals,
            profile=profile,
            settings=self._settings,
        )
        score = await adjust_with_llm(
            self._llm,
            question_text=current.text,
            transcript=transcript,
            expected_signals=current.expected_signals,
            base=score,
            settings=self._settings,
        )

        # The clock starts at the previous answer (or the session's start): that
        # is the window in which this answer was actually produced, and it is
        # what the words-per-second proxy signal reads.
        asked_at = session.turns[-1].answered_at if session.turns else session.started_at
        self._store.add_turn(
            session.id,
            question=current,
            channel=channel,
            transcript=transcript,
            word_count=word_count(transcript),
            audio_digest=digest,
            audio_duration_seconds=duration,
            score=score,
            asked_at=asked_at,
            answered_at=moment,
        )

        session = self._store.get_session(session.id)
        following = self._next_question(session)
        if following is None:
            session = self._complete(session, at=moment)
        return session, following

    def finish(
        self, candidate_id: str, session_id: str, *, at: Optional[datetime] = None
    ) -> InterviewSession:
        """Complete early. The assessment is computed over what WAS answered and
        its confidence falls with coverage -- an unfinished interview says less,
        rather than saying the same thing about less."""
        moment = as_utc(at) if at else _utcnow()
        session = self._owned(candidate_id, session_id)
        status = effective_status(session.status, session.expires_at, at=moment)
        if status is not InterviewStatus.IN_PROGRESS:
            raise SessionConflictError(f"this interview is {status.value}")
        return self._complete(session, at=moment)

    def get(
        self, candidate_id: str, session_id: str, *, at: Optional[datetime] = None
    ) -> InterviewSession:
        """The candidate's own full view, transcripts included -- it is their
        data, and a score whose basis they cannot read is not advisory, it is
        oracular."""
        moment = as_utc(at) if at else _utcnow()
        session = self._owned(candidate_id, session_id)
        return session.model_copy(
            update={
                "status": effective_status(
                    session.status, session.expires_at, at=moment
                )
            }
        )

    def list_for_candidate(
        self, candidate_id: str, *, at: Optional[datetime] = None
    ) -> list[InterviewSummary]:
        moment = as_utc(at) if at else _utcnow()
        return [
            self.summarize(s, at=moment)
            for s in self._store.sessions_for_candidate(candidate_id)
        ]

    def next_question(
        self, session: InterviewSession
    ) -> Optional[InterviewQuestion]:
        return self._next_question(session)

    # -- org plane -------------------------------------------------------------

    def assessments_for_org(
        self, *, org_id: str, candidate_id: str, at: Optional[datetime] = None
    ) -> list[InterviewSummary]:
        return self._store.assessments_for_org(
            org_id=org_id, candidate_id=candidate_id, at=at
        )

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def summarize(
        session: InterviewSession, *, at: Optional[datetime] = None
    ) -> InterviewSummary:
        """Header projection: no transcript, no turns, by construction."""
        moment = at or _utcnow()
        assessment = session.assessment
        return InterviewSummary(
            id=session.id,
            status=effective_status(session.status, session.expires_at, at=moment),
            domain=session.domain,
            band=assessment.band if assessment else InterviewBand.INSUFFICIENT_SIGNAL,
            overall=assessment.overall if assessment else 0.0,
            dimensions=dict(assessment.dimensions) if assessment else {},
            confidence=assessment.confidence if assessment else 0.0,
            proxy_band=assessment.proxy.band if assessment else ProxyBand.LOW,
            questions_planned=(
                assessment.questions_planned if assessment else len(session.questions)
            ),
            questions_answered=(
                assessment.questions_answered if assessment else len(session.turns)
            ),
            started_at=session.started_at,
            completed_at=session.completed_at,
        )

    def _owned(self, candidate_id: str, session_id: str) -> InterviewSession:
        session = self._store.get_session(session_id)
        if session is None or session.candidate_id != candidate_id:
            # Same error either way: a candidate cannot probe for another's ids.
            raise LookupError(f"unknown interview for candidate: {session_id}")
        return session

    @staticmethod
    def _next_question(session: InterviewSession) -> Optional[InterviewQuestion]:
        answered = {t.question_id for t in session.turns}
        for question in session.questions:
            if question.id not in answered:
                return question
        return None

    def _latest_report(self, candidate_id: str):
        """The newest depth report, or None. Best effort: a report-store hiccup
        must never block a candidate starting their own interview -- the
        `_corroborating_employers` precedent."""
        try:
            reports = self._report_store.for_candidate(candidate_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("interview_report_lookup_failed", error=str(exc))
            return None
        if not reports:
            return None
        return max(reports, key=lambda r: r.created_at)

    async def _resolve_answer(
        self, *, text: Optional[str], audio_b64: Optional[str], mime: Optional[str]
    ) -> tuple[AnswerChannel, str, Optional[str], Optional[float]]:
        """(channel, transcript, audio_digest, duration). The audio bytes exist
        only inside this method: they are hashed and dropped, and nothing that
        could reconstruct them is returned."""
        if audio_b64:
            if len(audio_b64) > self._settings.interview_max_audio_b64_chars:
                raise AnswerTooLargeError(
                    "audio exceeds interview_max_audio_b64_chars="
                    f"{self._settings.interview_max_audio_b64_chars}"
                )
            # Speech first: a provider failure must leave no trace, so nothing
            # is written and the candidate simply answers again.
            transcript = await self._speech.atranscribe(
                audio_b64=audio_b64, mime=mime or "audio/wav"
            )
            try:
                raw = base64.b64decode(audio_b64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("audio is not valid base64") from exc
            digest = hashlib.sha256(raw).hexdigest()
            return (
                AnswerChannel.AUDIO,
                (transcript.text or "").strip(),
                digest,
                transcript.duration_seconds,
            )

        if text and text.strip():
            if len(text) > self._settings.interview_max_answer_chars:
                raise AnswerTooLargeError(
                    "answer exceeds interview_max_answer_chars="
                    f"{self._settings.interview_max_answer_chars}"
                )
            return AnswerChannel.TEXT, text.strip(), None, None

        raise ValueError("provide either text or audio_b64")

    def _complete(
        self, session: InterviewSession, *, at: datetime
    ) -> InterviewSession:
        # The STAMPED level, never a fresh read: verifying yourself after the
        # fact must not rewrite what the session was worth.
        assurance = IdentityAssurance(
            candidate_id=session.candidate_id,
            level=AssuranceLevel(session.assurance_level_at_start),
        )
        proxy = assess_proxy_risk(
            assurance=assurance, turns=session.turns, settings=self._settings
        )
        assessment = aggregate(
            session_id=session.id,
            candidate_id=session.candidate_id,
            questions=session.questions,
            turns=session.turns,
            proxy=proxy,
            settings=self._settings,
        )
        return self._store.complete_session(session.id, assessment=assessment, at=at)


def build_interview_service(
    settings: Optional[Settings] = None,
    *,
    candidates: CandidateStore,
    ledger: LedgerStore,
    report_store,
    verification,
    llm: LLMClient,
    speech: SpeechClient,
) -> InterviewService:
    settings = settings or get_settings()
    store = InterviewStore(
        candidates._session_factory, ledger=ledger, settings=settings
    )
    return InterviewService(
        store, candidates, ledger, report_store,
        verification=verification, llm=llm, speech=speech, settings=settings,
    )
