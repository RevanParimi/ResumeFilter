"""S7.3 interview contracts.

Taxonomies here are code constants, not config -- the same stance as
AssuranceLevel/ConsentPurpose. Two deliberate shapes:

* `InterviewBand` duplicates `DepthBand`'s members and is NOT the same type. A
  resume-depth band answers "how deep does the written claim look"; an
  interview band answers "how deep did the live answers go". Making them one
  type invites a fusion nobody reviewed -- the S7.2 "two ladders" lesson.
* `InterviewSummary` has no transcript or turn field at all. It is the
  org-facing projection, and structural absence beats a filter someone forgets.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class InterviewStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"   # never stored; derived read-time past expires_at


class QuestionSource(StrEnum):
    PROBE = "probe"       # from the depth report -- the questions that matter most
    PROFILE = "profile"   # deterministic template over the candidate's own profile
    DOMAIN = "domain"     # a registered DomainModel's seed opener


class AnswerChannel(StrEnum):
    AUDIO = "audio"
    TEXT = "text"


class InterviewBand(StrEnum):
    INSUFFICIENT_SIGNAL = "insufficient_signal"
    SUPERFICIAL = "superficial"
    EMERGING = "emerging"
    SOLID = "solid"
    DEEP = "deep"


class ProxyBand(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"   # the ceiling: nothing here can CONFIRM a proxy


#: The rubric axes, in report order. A dict keyed by these is the score.
DIMENSIONS: tuple[str, ...] = ("specificity", "ownership", "depth", "consistency")

_PROXY_SEVERITIES = ("info", "soft")   # deliberately no "hard": see ProxyBand


class InterviewQuestion(BaseModel):
    id: str
    sequence: int
    text: str
    source: QuestionSource
    #: What a genuine answer would have to mention. For PROBE questions these
    #: are the verdict's missing_signals -- the scorer's yardstick without an LLM.
    expected_signals: list[str] = Field(default_factory=list)
    claim_id: Optional[str] = None


class TurnScore(BaseModel):
    """Per-answer rubric result. `dimensions` is a subset of DIMENSIONS: an
    insufficient answer scores nothing rather than scoring zero."""

    dimensions: dict[str, float] = Field(default_factory=dict)
    insufficient: bool = False
    codes: list[str] = Field(default_factory=list)


class InterviewTurn(BaseModel):
    id: str
    sequence: int
    question_id: str
    question_text: str
    question_source: QuestionSource
    expected_signals: list[str] = Field(default_factory=list)
    channel: AnswerChannel
    transcript: str = ""
    word_count: int = 0
    #: sha256 of the submitted audio. The bytes themselves are never stored and
    #: no field here could hold them.
    audio_digest: Optional[str] = None
    audio_duration_seconds: Optional[float] = None
    asked_at: datetime
    answered_at: datetime
    score: TurnScore = Field(default_factory=TurnScore)


class ProxyFinding(BaseModel):
    """One advisory proxy observation. Never an accusation, never `hard`."""

    id: str
    severity: str = "info"
    message: str
    detail: dict = Field(default_factory=dict)

    @field_validator("severity")
    @classmethod
    def _known_severity(cls, v: str) -> str:
        if v not in _PROXY_SEVERITIES:
            raise ValueError(f"severity must be one of {_PROXY_SEVERITIES}")
        return v


class ProxyRisk(BaseModel):
    band: ProxyBand = ProxyBand.LOW
    findings: list[ProxyFinding] = Field(default_factory=list)
    #: The S7.1 hook, as stamped when the session STARTED.
    assurance_level_at_start: int = 0
    advisory: bool = True


class InterviewAssessment(BaseModel):
    session_id: str
    candidate_id: str
    band: InterviewBand = InterviewBand.INSUFFICIENT_SIGNAL
    overall: float = Field(default=0.0, ge=0.0, le=1.0)
    dimensions: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    questions_planned: int = 0
    questions_answered: int = 0
    proxy: ProxyRisk = Field(default_factory=ProxyRisk)
    scorer_version: str = ""
    advisory: bool = True
    human_review_required: bool = True


class InterviewSession(BaseModel):
    """The candidate's own view: questions, turns (with transcripts), outcome."""

    id: str
    candidate_id: str
    domain: str = "genai"
    report_id: Optional[str] = None
    status: InterviewStatus = InterviewStatus.IN_PROGRESS
    assurance_level_at_start: int = 0
    questions: list[InterviewQuestion] = Field(default_factory=list)
    turns: list[InterviewTurn] = Field(default_factory=list)
    assessment: Optional[InterviewAssessment] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class InterviewSummary(BaseModel):
    """Header projection. Used by the candidate's list view AND the org read --
    which is why it has no transcript and no turns: an org must not be one
    forgotten filter away from the candidate's words."""

    id: str
    status: InterviewStatus
    domain: str = "genai"
    band: InterviewBand = InterviewBand.INSUFFICIENT_SIGNAL
    overall: float = 0.0
    dimensions: dict[str, float] = Field(default_factory=dict)
    confidence: float = 0.0
    proxy_band: ProxyBand = ProxyBand.LOW
    questions_planned: int = 0
    questions_answered: int = 0
    started_at: datetime
    completed_at: Optional[datetime] = None
    advisory: bool = True
