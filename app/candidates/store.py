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
import secrets
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.candidates.models import (
    CandidateCredentialRow,
    CandidateRow,
    ExtractionRow,
    FingerprintRow,
    ResumeRow,
    _utcnow,
)
from app.candidates.schema import CandidateProfile, ExtractionResult
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.fabrication.similarity import Fingerprint, estimate_similarity
from app.schemas.fabrication import ResumeMatch

MatchedOn = Literal["email_hash", "phone_hash"]


def _as_utc(dt: datetime) -> datetime:
    """Aware-UTC view of any datetime; naive values are assumed UTC (SQLite
    drops tzinfo, so refetched timestamps come back naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _hash_access_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IngestOutcome(BaseModel):
    """What one ingest did: which candidate/resume/extraction, and why."""

    candidate_id: str
    resume_id: str
    extraction_id: str
    resume_version: int
    matched_existing: bool = False
    matched_on: Optional[MatchedOn] = None
    duplicate_resume: bool = False


class ResumeSummary(BaseModel):
    id: str
    version: int
    text_sha256: str
    created_at: datetime


class CandidateSummary(BaseModel):
    id: str
    full_name: Optional[str] = None
    email_hash: Optional[str] = None
    phone_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resume_count: int = 0


class CandidateStore:
    def __init__(self, session_factory: sessionmaker, *, access_key_bytes: int = 32) -> None:
        self._session_factory = session_factory
        self._access_key_bytes = access_key_bytes

    def ingest(
        self,
        result: ExtractionResult,
        resume_text: str,
        *,
        org_id: Optional[str] = None,
    ) -> IngestOutcome:
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
                    org_id=org_id,
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

    def get_candidate(self, candidate_id: str) -> Optional[CandidateSummary]:
        with self._session_factory() as session:
            cand = session.get(CandidateRow, candidate_id)
            if cand is None:
                return None
            return CandidateSummary(
                id=cand.id,
                full_name=cand.full_name,
                email_hash=cand.email_hash,
                phone_hash=cand.phone_hash,
                created_at=cand.created_at,
                updated_at=cand.updated_at,
                resume_count=len(cand.resumes),
            )

    def latest_profile(self, candidate_id: str) -> Optional[CandidateProfile]:
        """Profile from the newest resume version (ties: newest extraction)."""
        with self._session_factory() as session:
            row = (
                session.execute(
                    select(ExtractionRow)
                    .join(ResumeRow, ExtractionRow.resume_id == ResumeRow.id)
                    .where(ExtractionRow.candidate_id == candidate_id)
                    .order_by(ResumeRow.version.desc(), ExtractionRow.created_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            return CandidateProfile.model_validate(row.profile) if row else None

    def profile_as_of(self, candidate_id: str, as_of: datetime) -> Optional[CandidateProfile]:
        """Point-in-time profile: newest extraction with created_at <= as_of
        (tie-break: newest resume version, then newest created_at). None if the
        candidate had no extraction by as_of. Filtering happens in Python after
        as_utc coercion because SQLite returns naive datetimes (see consent.py)."""
        moment = _as_utc(as_of)
        with self._session_factory() as session:
            rows = session.execute(
                select(ExtractionRow, ResumeRow.version)
                .join(ResumeRow, ExtractionRow.resume_id == ResumeRow.id)
                .where(ExtractionRow.candidate_id == candidate_id)
            ).all()
        eligible = [
            (version, _as_utc(ext.created_at), ext)
            for ext, version in rows
            if _as_utc(ext.created_at) <= moment
        ]
        if not eligible:
            return None
        eligible.sort(key=lambda t: (t[0], t[1]))  # ascending; last = newest
        return CandidateProfile.model_validate(eligible[-1][2].profile)

    def list_resumes(self, candidate_id: str) -> list[ResumeSummary]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(ResumeRow)
                    .where(ResumeRow.candidate_id == candidate_id)
                    .order_by(ResumeRow.version)
                )
                .scalars()
                .all()
            )
            return [
                ResumeSummary(
                    id=r.id,
                    version=r.version,
                    text_sha256=r.text_sha256,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    def delete_candidate(self, candidate_id: str) -> bool:
        """DPDP erasure: candidate + all resumes (raw text) + extractions."""
        with self._session_factory() as session:
            cand = session.get(CandidateRow, candidate_id)
            if cand is None:
                return False
            session.delete(cand)
            session.commit()
            return True

    def delete_resume(self, resume_id: str) -> bool:
        """DPDP erasure of ONE resume version + its extractions; candidate stays."""
        with self._session_factory() as session:
            resume = session.get(ResumeRow, resume_id)
            if resume is None:
                return False
            session.delete(resume)
            session.commit()
            return True

    # -- candidate auth (S6.4): minted access key, mirrors org API keys ---------

    def issue_access_key(self, candidate_id: str) -> str:
        """Mint (or rotate) this candidate's access key; return the plaintext
        ONCE, storing only its hash. Overwriting an existing credential is
        rotation. LookupError if the candidate is unknown."""
        with self._session_factory() as session:
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            raw = secrets.token_urlsafe(self._access_key_bytes)
            cred = (
                session.execute(
                    select(CandidateCredentialRow).where(
                        CandidateCredentialRow.candidate_id == candidate_id
                    )
                ).scalars().first()
            )
            if cred is None:
                session.add(
                    CandidateCredentialRow(
                        candidate_id=candidate_id, access_key_hash=_hash_access_key(raw)
                    )
                )
            else:
                cred.access_key_hash = _hash_access_key(raw)
                cred.rotated_at = _utcnow()
            session.commit()
            return raw

    def authenticate_candidate(self, access_key: str) -> Optional[str]:
        """candidate_id for the credential holding this key, else None.
        Empty/whitespace keys never match."""
        access_key = (access_key or "").strip()
        if not access_key:
            return None
        digest = _hash_access_key(access_key)
        with self._session_factory() as session:
            row = (
                session.execute(
                    select(CandidateCredentialRow).where(
                        CandidateCredentialRow.access_key_hash == digest
                    )
                ).scalars().first()
            )
            return row.candidate_id if row else None

    # -- self-registration support (S8.2) --------------------------------------

    def find_by_email_hash(self, email_hash: str) -> Optional[str]:
        """The candidate whose contact hash matches, else None.

        This is what lets a self-registering candidate CLAIM the record built
        from a resume an org uploaded, rather than forking a duplicate person.

        The hash MUST be produced by the same salted function that wrote it
        (``app.candidates.hashing.contact_hash`` with ``contact_hash_salt``) or
        nothing will ever match and every signup silently creates a duplicate.
        """
        if not email_hash:
            return None
        with self._session_factory() as session:
            row = session.execute(
                select(CandidateRow).where(CandidateRow.email_hash == email_hash)
            ).scalars().first()
            return row.id if row else None

    def create_bare_candidate(self, *, email_hash: str) -> str:
        """A candidate row carrying a contact hash and nothing else — someone
        who signed up before any resume of theirs was ever submitted."""
        with self._session_factory() as session:
            row = CandidateRow(email_hash=email_hash)
            session.add(row)
            session.commit()
            return row.id

    def email_hash_for(self, candidate_id: str) -> Optional[str]:
        """The stored contact hash, needed by the erasure path to clear login
        challenges — which have no FK and therefore cannot cascade."""
        with self._session_factory() as session:
            row = session.get(CandidateRow, candidate_id)
            return row.email_hash if row else None

    def save_fingerprint(
        self, fp: Fingerprint, *, resume_id: str, candidate_id: str
    ) -> bool:
        """Idempotent per (resume, algo): re-uploads of an existing version
        write nothing. Returns True when a row was actually written."""
        with self._session_factory() as session:
            exists = session.execute(
                select(FingerprintRow.id).where(
                    FingerprintRow.resume_id == resume_id,
                    FingerprintRow.algo == fp.algo,
                )
            ).first()
            if exists:
                return False
            session.add(
                FingerprintRow(
                    resume_id=resume_id,
                    candidate_id=candidate_id,
                    algo=fp.algo,
                    signature=list(fp.values),
                    shingle_count=fp.shingle_count,
                )
            )
            session.commit()
            return True

    def similar_resumes(
        self,
        fp: Fingerprint,
        *,
        exclude_candidate_id: str,
        threshold: float,
        limit: int,
    ) -> tuple[list[ResumeMatch], int]:
        """Estimated-similarity matches from OTHER candidates, best first, plus
        how many stored fingerprints were compared (the corpus size). Linear
        scan in Python — signatures are small int lists and SQLite-scale
        corpora are thousands, not millions; LSH banding is the flagged
        optimization if this ever grows past that."""
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(FingerprintRow).where(
                        FingerprintRow.algo == fp.algo,
                        FingerprintRow.candidate_id != exclude_candidate_id,
                    )
                )
                .scalars()
                .all()
            )
            matches = [
                ResumeMatch(
                    candidate_id=r.candidate_id,
                    resume_id=r.resume_id,
                    similarity=sim,
                )
                for r in rows
                if (sim := estimate_similarity(fp.values, list(r.signature))) >= threshold
            ]
            matches.sort(key=lambda m: m.similarity, reverse=True)
            return matches[:limit], len(rows)


def build_candidate_store(settings: Optional[Settings] = None) -> CandidateStore:
    """Store on the configured URL. Schema is Alembic's job (`alembic upgrade
    head`), NOT the builder's — no create_all here by design."""
    settings = settings or get_settings()
    engine = make_engine(settings.candidates_db_url)
    return CandidateStore(
        make_session_factory(engine),
        access_key_bytes=settings.candidate_access_key_bytes,
    )
