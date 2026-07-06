"""Candidate store — identity resolution, versioned resumes, extraction audit.

Identity resolution matches on the S1.1 salted contact hashes: email_hash
first, phone_hash second. A match attaches the new resume to that candidate
(and backfills any hash the candidate is missing); it NEVER merges two
existing candidates — that needs human judgment, not a heuristic. No hashes
at all ⇒ a new candidate every time (advisory system: never guess identity).

DPDP: delete_candidate / delete_resume are hard deletes that cascade to
resumes and extractions, erasing raw resume text on request.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.candidates.models import CandidateRow, ExtractionRow, ResumeRow, _utcnow
from app.candidates.schema import CandidateProfile, ExtractionResult
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory

MatchedOn = Literal["email_hash", "phone_hash"]


class IngestOutcome(BaseModel):
    """What one ingest did: which candidate/resume/extraction, and why."""

    candidate_id: str
    resume_id: str
    extraction_id: str
    resume_version: int
    matched_existing: bool = False
    matched_on: Optional[MatchedOn] = None
    duplicate_resume: bool = False


class CandidateStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def ingest(self, result: ExtractionResult, resume_text: str) -> IngestOutcome:
        sha = hashlib.sha256(resume_text.encode("utf-8")).hexdigest()
        profile = result.profile
        with self._session_factory() as session:
            cand, matched_on = self._resolve_candidate(session, profile)
            matched = cand is not None
            if cand is None:
                cand = CandidateRow()
                session.add(cand)
            self._refresh_identity(cand, profile)
            session.flush()

            resume = (
                session.execute(
                    select(ResumeRow).where(
                        ResumeRow.candidate_id == cand.id,
                        ResumeRow.text_sha256 == sha,
                    )
                )
                .scalars()
                .first()
            )
            duplicate = resume is not None
            if resume is None:
                latest = session.execute(
                    select(func.max(ResumeRow.version)).where(
                        ResumeRow.candidate_id == cand.id
                    )
                ).scalar()
                resume = ResumeRow(
                    candidate_id=cand.id,
                    version=(latest or 0) + 1,
                    raw_text=resume_text,
                    text_sha256=sha,
                )
                session.add(resume)
                session.flush()

            extraction = ExtractionRow(
                resume_id=resume.id,
                candidate_id=cand.id,
                method=result.method,
                profile=profile.model_dump(mode="json"),
                warnings=list(result.warnings),
            )
            session.add(extraction)
            session.commit()
            return IngestOutcome(
                candidate_id=cand.id,
                resume_id=resume.id,
                extraction_id=extraction.id,
                resume_version=resume.version,
                matched_existing=matched,
                matched_on=matched_on,
                duplicate_resume=duplicate,
            )

    @staticmethod
    def _resolve_candidate(
        session: Session, profile: CandidateProfile
    ) -> tuple[Optional[CandidateRow], Optional[MatchedOn]]:
        contact = profile.contact
        if contact.email_hash:
            row = (
                session.execute(
                    select(CandidateRow).where(CandidateRow.email_hash == contact.email_hash)
                )
                .scalars()
                .first()
            )
            if row is not None:
                return row, "email_hash"
        if contact.phone_hash:
            row = (
                session.execute(
                    select(CandidateRow).where(CandidateRow.phone_hash == contact.phone_hash)
                )
                .scalars()
                .first()
            )
            if row is not None:
                return row, "phone_hash"
        return None, None

    @staticmethod
    def _refresh_identity(cand: CandidateRow, profile: CandidateProfile) -> None:
        """Backfill hashes this resume adds; latest non-empty name wins."""
        contact = profile.contact
        if contact.email_hash and not cand.email_hash:
            cand.email_hash = contact.email_hash
        if contact.phone_hash and not cand.phone_hash:
            cand.phone_hash = contact.phone_hash
        if profile.full_name and profile.full_name.value:
            cand.full_name = profile.full_name.value
        cand.updated_at = _utcnow()
