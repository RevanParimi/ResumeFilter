"""Verification persistence + audit (S7.1).

Mirrors LedgerStore's discipline: every mutation is audited in the SAME
transaction as the write, so an outcome can never exist without its trail.
Audit rows go to the shared `audit_log` via LedgerStore._audit, which is what
makes verifications show up in the candidate's own DPDP access log for free.

Challenge hygiene is real deletion, not a retention policy: a consumed or
superseded OTP is secret material with no reason to survive, and it is removed
on paths that already run, so no scheduler is needed.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.candidates.models import CandidateRow
from app.core.config import Settings, get_settings
from app.ledger.consent import as_utc
from app.ledger.store import LedgerStore
from app.verification import otp as otp_logic
from app.verification.assurance import compute_assurance
from app.verification.models import VerificationChallengeRow, VerificationRow
from app.verification.schema import (
    METHOD_LEVEL, AssuranceLevel, IdentityAssurance, Verification,
    VerificationMethod, VerificationStatus,
)


class ChallengeError(Exception):
    """A challenge could not be issued or confirmed (wrong/expired/exhausted/
    cooling down). Carries no information about the correct code."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _verification(row: VerificationRow) -> Verification:
    return Verification(
        id=row.id,
        candidate_id=row.candidate_id,
        method=VerificationMethod(row.method),
        assurance_level=AssuranceLevel(row.assurance_level),
        status=VerificationStatus(row.status),
        consent_id=row.consent_id,
        evidence_digest=row.evidence_digest,
        details=row.details or {},
        requested_at=as_utc(row.requested_at),
        completed_at=as_utc(row.completed_at) if row.completed_at else None,
        expires_at=as_utc(row.expires_at) if row.expires_at else None,
    )


class VerificationStore:
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

    # -- outcomes -------------------------------------------------------------

    def create_verification(
        self,
        *,
        candidate_id: str,
        method: VerificationMethod,
        consent_id: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> Verification:
        moment = as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            row = VerificationRow(
                id=str(uuid.uuid4()),
                candidate_id=candidate_id,
                method=method.value,
                assurance_level=int(METHOD_LEVEL[method]),
                status=VerificationStatus.PENDING.value,
                consent_id=consent_id,
                details={},
                requested_at=moment,
            )
            session.add(row)
            session.flush()
            self._ledger._audit(
                session,
                actor_type="candidate",
                actor_id=candidate_id,
                action="verification.start",
                entity_type="verification",
                entity_id=row.id,
                candidate_id=candidate_id,
                details={"method": method.value, "third_party": consent_id is not None},
            )
            session.commit()
            return _verification(row)

    def get_verification(self, verification_id: str) -> Optional[Verification]:
        with self._session_factory() as session:
            row = session.get(VerificationRow, verification_id)
            return _verification(row) if row else None

    def verifications_for_candidate(self, candidate_id: str) -> list[Verification]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(VerificationRow)
                    .where(VerificationRow.candidate_id == candidate_id)
                    .order_by(VerificationRow.requested_at, VerificationRow.id)
                ).scalars().all()
            )
            return [_verification(r) for r in rows]

    def complete_verification(
        self,
        verification_id: str,
        *,
        status: VerificationStatus,
        evidence_digest: Optional[str] = None,
        details: Optional[dict] = None,
        at: Optional[datetime] = None,
    ) -> Verification:
        moment = as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            row = session.get(VerificationRow, verification_id)
            if row is None:
                raise LookupError(f"unknown verification: {verification_id}")
            row.status = status.value
            row.completed_at = moment
            if status is VerificationStatus.VERIFIED:
                row.expires_at = moment + timedelta(
                    days=self._settings.verif_outcome_ttl_days
                )
            if evidence_digest is not None:
                row.evidence_digest = evidence_digest
            if details:
                row.details = {**(row.details or {}), **details}
            self._ledger._audit(
                session,
                actor_type="system",
                actor_id=None,
                action="verification.complete",
                entity_type="verification",
                entity_id=row.id,
                candidate_id=row.candidate_id,
                details={"method": row.method, "status": status.value},
            )
            session.commit()
            return _verification(row)

    # -- challenges (short-lived secret material) ------------------------------

    def create_challenge(
        self,
        *,
        verification_id: str,
        channel: str,
        destination_hash: str,
        rng: Optional[random.Random] = None,
        at: Optional[datetime] = None,
    ) -> str:
        """Issue a code and return the PLAINTEXT once, for immediate delivery.
        Only its salted digest is stored. A prior challenge on the same
        verification is deleted, so exactly one code is ever live."""
        moment = as_utc(at) if at else _utcnow()
        rng = rng or random.SystemRandom()
        s = self._settings
        with self._session_factory() as session:
            row = session.get(VerificationRow, verification_id)
            if row is None:
                raise LookupError(f"unknown verification: {verification_id}")
            existing = (
                session.execute(
                    select(VerificationChallengeRow).where(
                        VerificationChallengeRow.verification_id == verification_id
                    )
                ).scalars().all()
            )
            for prior in existing:
                if otp_logic.cooldown_active(
                    prior.last_sent_at, s.verif_otp_resend_cooldown_seconds, at=moment
                ):
                    raise ChallengeError("a code was sent recently; try again shortly")
                session.delete(prior)
            session.flush()

            code = otp_logic.generate_code(s.verif_otp_length, rng=rng)
            session.add(
                VerificationChallengeRow(
                    id=str(uuid.uuid4()),
                    verification_id=verification_id,
                    code_hash=otp_logic.hash_code(code, s.contact_hash_salt),
                    channel=channel,
                    destination_hash=destination_hash,
                    attempts=0,
                    max_attempts=s.verif_otp_max_attempts,
                    expires_at=moment + timedelta(minutes=s.verif_otp_ttl_minutes),
                    last_sent_at=moment,
                )
            )
            session.commit()
            return code

    def confirm_challenge(
        self, verification_id: str, code: str, *, at: Optional[datetime] = None
    ) -> Verification:
        moment = as_utc(at) if at else _utcnow()
        s = self._settings
        with self._session_factory() as session:
            row = session.get(VerificationRow, verification_id)
            if row is None:
                raise LookupError(f"unknown verification: {verification_id}")
            challenge = (
                session.execute(
                    select(VerificationChallengeRow).where(
                        VerificationChallengeRow.verification_id == verification_id
                    )
                ).scalars().first()
            )
            if challenge is None:
                raise ChallengeError("no active challenge")
            if otp_logic.is_challenge_expired(challenge.expires_at, at=moment):
                session.delete(challenge)
                session.commit()
                raise ChallengeError("challenge expired")

            if otp_logic.hash_code(code or "", s.contact_hash_salt) != challenge.code_hash:
                challenge.attempts += 1
                exhausted = otp_logic.attempts_exhausted(
                    challenge.attempts, challenge.max_attempts
                )
                if exhausted:
                    row.status = VerificationStatus.FAILED.value
                    row.completed_at = moment
                    session.delete(challenge)
                    self._ledger._audit(
                        session,
                        actor_type="candidate",
                        actor_id=row.candidate_id,
                        action="verification.complete",
                        entity_type="verification",
                        entity_id=row.id,
                        candidate_id=row.candidate_id,
                        details={"method": row.method, "status": "failed",
                                 "reason": "attempts_exhausted"},
                    )
                session.commit()
                raise ChallengeError(
                    "incorrect code" if not exhausted else "too many attempts"
                )

            row.status = VerificationStatus.VERIFIED.value
            row.completed_at = moment
            row.expires_at = moment + timedelta(days=s.verif_outcome_ttl_days)
            session.delete(challenge)  # consumed secret material: gone
            self._ledger._audit(
                session,
                actor_type="candidate",
                actor_id=row.candidate_id,
                action="verification.complete",
                entity_type="verification",
                entity_id=row.id,
                candidate_id=row.candidate_id,
                details={"method": row.method, "status": "verified"},
            )
            session.commit()
            return _verification(row)

    # -- roll-up ---------------------------------------------------------------

    def assurance_for_candidate(
        self, candidate_id: str, *, at: Optional[datetime] = None
    ) -> IdentityAssurance:
        moment = as_utc(at) if at else _utcnow()
        return compute_assurance(
            candidate_id, self.verifications_for_candidate(candidate_id), at=moment
        )
