"""Verification orchestration (S7.1).

Two gates live here, in the spine, deliberately not in the adapters:

1. THIRD-PARTY CONSENT. Any adapter declaring `third_party` requires an active
   IDENTITY_VERIFY grant before anything happens. Putting this in the spine
   means a future vendor adapter is gated whether or not its author remembers.

2. DESTINATION BINDING. The candidates table stores only salted contact
   HASHES, so there is no address to look up. The candidate supplies the
   destination, we normalize + hash it with S1.1's helpers, and require it to
   equal the hash already on their row. This proves they know the contact on
   file, works regardless of what extraction retained, and lets the raw value
   stay transient -- only the hash is ever written.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Optional

from app.candidates.hashing import contact_hash, normalize_email, normalize_phone
from app.candidates.store import CandidateStore
from app.core.config import Settings, get_settings
from app.ledger import consent as consent_logic
from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError, LedgerStore
from app.verification.methods import get_adapter
from app.verification.otp import Notifier, NullNotifier
from app.verification.schema import (
    IdentityAssurance, Verification, VerificationMethod, VerificationStatus,
)
from app.verification.store import VerificationStore


class DestinationError(Exception):
    """The supplied OTP destination is missing, malformed, or does not match
    the contact hash on the candidate's record."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VerificationService:
    def __init__(
        self,
        store: VerificationStore,
        candidates: CandidateStore,
        ledger: LedgerStore,
        *,
        notifier: Optional[Notifier] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self._store = store
        self._candidates = candidates
        self._ledger = ledger
        self._notifier = notifier or NullNotifier()
        self._settings = settings or get_settings()

    def start(
        self,
        candidate_id: str,
        method: VerificationMethod,
        *,
        destination: Optional[str] = None,
        rng: Optional[random.Random] = None,
        at: Optional[datetime] = None,
    ) -> tuple[Verification, Optional[str]]:
        """Begin a verification. Returns (verification, plaintext_code | None).

        The plaintext code is returned ONLY so the route can honour the
        double-guarded debug echo; it is never persisted and never logged.
        """
        moment = consent_logic.as_utc(at) if at else _utcnow()
        summary = self._candidates.get_candidate(candidate_id)
        if summary is None:
            raise LookupError(f"unknown candidate: {candidate_id}")

        adapter = get_adapter(method)

        consent_id: Optional[str] = None
        if adapter.third_party:
            grants = self._ledger.consents_for_candidate(candidate_id)
            decision = consent_logic.has_any_active(
                grants, purpose=ConsentPurpose.IDENTITY_VERIFY, at=moment
            )
            if not decision.allowed:
                raise ConsentError(decision.reason)
            consent_id = decision.grant_id

        if adapter.challenge_based:
            destination_hash = self._bind_destination(summary, adapter, destination)
            verification = self._store.create_verification(
                candidate_id=candidate_id, method=method, consent_id=consent_id, at=moment
            )
            code = self._store.create_challenge(
                verification_id=verification.id,
                channel=adapter.channel or "",
                destination_hash=destination_hash,
                rng=rng,
                at=moment,
            )
            self._notifier.send(destination or "", code, channel=adapter.channel or "")
            return verification, code

        verification = self._store.create_verification(
            candidate_id=candidate_id, method=method, consent_id=consent_id, at=moment
        )
        completed = self._store.complete_verification(
            verification.id, status=VerificationStatus.VERIFIED, at=moment
        )
        return completed, None

    def _bind_destination(self, summary, adapter, destination: Optional[str]) -> str:
        if not destination or not destination.strip():
            raise DestinationError("destination is required for this method")
        if adapter.channel == "email":
            normalized = normalize_email(destination)
        else:
            normalized = normalize_phone(destination)
        if not normalized:
            raise DestinationError("destination is not a valid contact value")

        on_file = getattr(summary, adapter.contact_hash_field or "", None)
        if not on_file:
            raise DestinationError(f"no {adapter.channel} on file for this candidate")
        supplied = contact_hash(normalized, self._settings.contact_hash_salt)
        if supplied != on_file:
            raise DestinationError("destination does not match the contact on file")
        return supplied

    def confirm(
        self,
        candidate_id: str,
        verification_id: str,
        code: str,
        *,
        at: Optional[datetime] = None,
    ) -> Verification:
        existing = self._store.get_verification(verification_id)
        if existing is None or existing.candidate_id != candidate_id:
            # Same error either way: a candidate cannot probe for another's ids.
            raise LookupError(f"unknown verification for candidate: {verification_id}")
        return self._store.confirm_challenge(verification_id, code, at=at)

    def list_for_candidate(
        self, candidate_id: str, *, at: Optional[datetime] = None
    ) -> tuple[list[Verification], IdentityAssurance]:
        moment = consent_logic.as_utc(at) if at else _utcnow()
        return (
            self._store.verifications_for_candidate(candidate_id),
            self._store.assurance_for_candidate(candidate_id, at=moment),
        )

    def assurance_for_candidate(
        self, candidate_id: str, *, at: Optional[datetime] = None
    ) -> IdentityAssurance:
        return self._store.assurance_for_candidate(candidate_id, at=at)

    def record_manual_review(
        self,
        candidate_id: str,
        *,
        outcome: VerificationStatus,
        note: Optional[str] = None,
        evidence_digest: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> Verification:
        moment = consent_logic.as_utc(at) if at else _utcnow()
        verification = self._store.create_verification(
            candidate_id=candidate_id,
            method=VerificationMethod.MANUAL_REVIEW,
            at=moment,
        )
        return self._store.complete_verification(
            verification.id,
            status=outcome,
            evidence_digest=evidence_digest,
            details={"note": note} if note else None,
            at=moment,
        )

    def assurance_for_org(
        self, *, org_id: str, candidate_id: str, at: Optional[datetime] = None
    ) -> IdentityAssurance:
        return self._store.assurance_for_org(
            org_id=org_id, candidate_id=candidate_id, at=at
        )


def build_verification_service(
    settings: Optional[Settings] = None,
    *,
    candidates: CandidateStore,
    ledger: LedgerStore,
) -> VerificationService:
    settings = settings or get_settings()
    store = VerificationStore(
        candidates._session_factory, ledger=ledger, settings=settings
    )
    return VerificationService(store, candidates, ledger, settings=settings)
