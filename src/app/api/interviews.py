"""Candidate interview workflows and consent-gated employer summaries.

Shared principal/CSRF dependencies retain subject and tenant boundaries.
Interview services own content scoring, transcription and persistence.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.dependencies import _rate_limited, _services, require_candidate, require_org
from app.interview.questions import NothingToAskError
from app.interview.schema import InterviewQuestion, InterviewSession, InterviewSummary
from app.interview.service import AnswerTooLargeError, SessionConflictError
from app.ledger.store import ConsentError
from app.ratelimit.service import RateLimited
from app.services.speech import SpeechFailed, SpeechUnavailable


candidate_router = APIRouter()
org_router = APIRouter()


class OrgInterviewAssessments(BaseModel):
    """The org-facing interview read: summaries only, no transcript (S7.3)."""

    attempts: int = 0
    assessments: list[InterviewSummary] = Field(default_factory=list)


class InterviewTurnResponse(BaseModel):
    """The candidate-plane interview body: the session plus what to ask next.
    `next_question` is None when the session is finished."""

    session: InterviewSession
    next_question: Optional[InterviewQuestion] = None


class InterviewListResponse(BaseModel):
    interviews: list[InterviewSummary] = Field(default_factory=list)


# ── AI interviews, candidate plane (S7.3) ───────────────────────────────────
# The interview asks the depth report's OWN probes. Every handler resolves the
# candidate from the key, never a path or body param. Audio is transcribed in
# memory and discarded (only a sha256 digest survives); the TRANSCRIPT is kept
# and is the candidate's to read here — it is never in an org payload.


class StartInterviewRequest(BaseModel):
    domain: str = "genai"


class SubmitAnswerRequest(BaseModel):
    """Exactly one of `text` / `audio_b64`. `question_id` is REQUIRED: an answer
    must name the question it answers, so two racing clients cannot collapse
    into one turn (409 on a mismatch)."""

    question_id: str
    text: str | None = None
    audio_b64: str | None = None
    mime: str | None = None


def _interview_body(session, following) -> InterviewTurnResponse:
    return InterviewTurnResponse(session=session, next_question=following)


@candidate_router.post("/portal/interviews", response_model=InterviewTurnResponse)
async def start_interview(
    req: StartInterviewRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> InterviewTurnResponse:
    services = _services(request)
    try:
        session = services.interview.start(candidate_id, domain_key=req.domain)
    except NothingToAskError as exc:   # nothing on file worth asking about
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:            # unknown domain key
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _interview_body(session, services.interview.next_question(session))


@candidate_router.get("/portal/interviews", response_model=InterviewListResponse)
async def list_interviews(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> InterviewListResponse:
    summaries = _services(request).interview.list_for_candidate(candidate_id)
    return {"interviews": [s.model_dump(mode="json") for s in summaries]}


@candidate_router.get("/portal/interviews/{session_id}", response_model=InterviewTurnResponse)
async def get_interview(
    session_id: str, request: Request, candidate_id: str = Depends(require_candidate)
) -> InterviewTurnResponse:
    """The candidate's own full view — transcripts included. It is their data,
    and an advisory score whose basis they cannot read is not advisory."""
    services = _services(request)
    try:
        session = services.interview.get(candidate_id, session_id)
    except LookupError as exc:  # unknown OR not owned — same 404 (no probing)
        raise HTTPException(status_code=404, detail="interview not found") from exc
    return _interview_body(session, services.interview.next_question(session))


@candidate_router.post("/portal/interviews/{session_id}/answers", response_model=InterviewTurnResponse)
async def submit_answer(
    session_id: str,
    req: SubmitAnswerRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> InterviewTurnResponse:
    services = _services(request)
    try:
        session, following = await services.interview.answer(
            candidate_id, session_id, question_id=req.question_id,
            text=req.text, audio_b64=req.audio_b64, mime=req.mime,
        )
    except RateLimited as exc:
        # Audio answers only (S8.3): the ASR path is the S7.3 review's named
        # spend surface. A typed answer is never refused here.
        raise _rate_limited(exc) from exc
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AnswerTooLargeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SpeechUnavailable as exc:
        # The designed no-key path, said out loud: answer in text instead.
        raise HTTPException(
            status_code=422, detail="speech_unavailable: answer this question in text"
        ) from exc
    except SpeechFailed as exc:
        # Nothing was recorded, so retrying costs the candidate nothing.
        raise HTTPException(status_code=422, detail="speech_failed: no answer saved; record again or answer in text") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="interview not found") from exc
    except ValueError as exc:          # no body, or bad base64
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _interview_body(session, following)


@candidate_router.post("/portal/interviews/{session_id}/finish", response_model=InterviewTurnResponse)
async def finish_interview(
    session_id: str, request: Request, candidate_id: str = Depends(require_candidate)
) -> InterviewTurnResponse:
    services = _services(request)
    try:
        session = services.interview.finish(candidate_id, session_id)
    except SessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="interview not found") from exc
    return _interview_body(session, None)


@org_router.get("/interview/candidates/{candidate_id}/assessments", response_model=OrgInterviewAssessments)
async def org_candidate_interviews(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> OrgInterviewAssessments:
    """Consent-gated interview assessments (INTERVIEW_READ — a new purpose, not
    a widening of verification_read). Every attempt — allowed or denied — is
    audited by the store. Headers only: bands, dimensions, proxy band,
    timestamps. NEVER the candidate's words."""
    try:
        summaries = _services(request).interview.assessments_for_org(
            org_id=org_id, candidate_id=candidate_id
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "attempts": len(summaries),
        "assessments": [s.model_dump(mode="json") for s in summaries],
    }
