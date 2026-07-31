"""Verification orchestration (S7.1).

`start` is the CANDIDATE-INITIATED entry point; operator-recorded outcomes come
in through `record_manual_review` on the admin plane instead. Four gates live
here, in the spine, deliberately not in the adapters:

1. SELF-SERVICE. A candidate may only start a method whose adapter says a
   candidate may start it. `manual_review` asserts that a human at the platform
   looked; a candidate who could request it would just award themselves L3.

2. IMPLEMENTED. A method with nothing behind it is refused here, not inside the
   adapter. The spine performs verifications itself and never calls into an
   adapter to do the work, so an adapter-side `NotImplementedError` would never
   fire -- `government_id` would complete VERIFIED at L4 on request.

3. THIRD-PARTY CONSENT. Any adapter declaring `third_party` requires an active
   IDENTITY_VERIFY grant before anything happens. Putting this in the spine
   means a future vendor adapter is gated whether or not its author remembers.
   Necessary, never sufficient: a candidate can grant IDENTITY_VERIFY to
   themselves from the portal, so gate 2 stands in front of it.

4. DESTINATION BINDING. The candidates table stores only salted contact
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
from app.verification.documents import assess, parse_document
from app.verification.methods import get_adapter
from app.verification.moonlighting import assess_concurrent_employment
from app.verification.otp import Notifier, NullNotifier
from app.verification.schema import (
    CLAIM_REF_MAX_CHARS, METHOD_SUBJECT, ClaimEvidence, DocumentFinding,
    DocumentType, IdentityAssurance, Verification, VerificationMethod,
    VerificationStatus, VerificationSubject,
)
from app.verification.store import VerificationStore


class DestinationError(Exception):
    """The supplied OTP destination is missing, malformed, or does not match
    the contact hash on the candidate's record."""


class MethodNotPermittedError(Exception):
    """The candidate may not initiate this method themselves (it is recorded by
    an operator, not requested). Distinct from "not implemented"."""


class DocumentTooLargeError(Exception):
    """The submitted body exceeds `doc_max_b64_chars`, or `claim_ref` exceeds
    its column width. The body check runs BEFORE decoding, so an oversize
    payload is never expanded in memory."""


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
        """Begin a CANDIDATE-INITIATED verification. Returns
        (verification, plaintext_code | None).

        The plaintext code is returned ONLY so the route can honour the
        double-guarded debug echo; it is never persisted and never logged.
        """
        moment = consent_logic.as_utc(at) if at else _utcnow()
        summary = self._candidates.get_candidate(candidate_id)
        if summary is None:
            raise LookupError(f"unknown candidate: {candidate_id}")

        adapter = get_adapter(method)

        # This is the candidate's own entry point, so the first question is
        # whether a candidate may award themselves this level at all. Only then
        # does it matter whether anything stands behind the method.
        if not adapter.self_service:
            raise MethodNotPermittedError(
                f"{method.value} is recorded by an operator, not requested"
            )
        if not adapter.implemented:
            raise NotImplementedError(f"{method.value} verification is not implemented")

        # SUBJECT (S7.2). This route mints IDENTITY rows and nothing else.
        # S7.2's claim methods declare `instant = True` meaning "assessment IS
        # the evidence" -- true in submit_document, which has actually run the
        # forensics, and false here, where no document exists. Without this gate
        # a candidate POSTs {"method": "experience_letter"} and gets a VERIFIED
        # row stamped subject=identity, which compute_assurance then folds. The
        # gate lives in the spine because "a check only one of two entry points
        # applies" is exactly the shape of the S7.1 escalation.
        #
        # Deliberately placed AFTER `implemented`, so a declared-but-inert
        # method answers 422 at every door regardless of its subject --
        # `epfo_employment` stays indistinguishable from `government_id`, which
        # is what makes inertness legible (spec section 3). Every S7.1 answer is
        # unchanged by this gate's presence.
        if METHOD_SUBJECT[method] is not VerificationSubject.IDENTITY:
            raise MethodNotPermittedError(
                f"{method.value} is not an identity method; "
                "employment-claim evidence is submitted with its document"
            )

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

        # Everything below marks an outcome VERIFIED on the strength of the
        # request alone, so it is reserved for methods where the assertion IS
        # the evidence. "Not challenge-based" must never imply "believe it".
        if not adapter.instant:
            raise NotImplementedError(
                f"{method.value} declares no way to reach an outcome"
            )

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
            actor_type="system",  # an operator did this, not the candidate
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

    # -- employment claims (S7.2) ---------------------------------------------

    def submit_document(
        self,
        candidate_id: str,
        doc_type: DocumentType,
        content_b64: str,
        *,
        claim_ref: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> tuple[Verification, list[DocumentFinding], ClaimEvidence]:
        """Parse, assess, and record ONE claim verification.

        The document lives only inside this call: `parse_document` returns text
        plus a digest, the assessment turns that into finding CODES, and the
        bytes go out of scope. Nothing that could reconstruct the document is
        written -- there is no column that could hold it (spec section 5).

        The same spine gates as `start` apply, in the same order and for the
        same reason. They are re-run here rather than assumed because this is a
        second candidate-initiated entry point, and a gate that only one entry
        point applies is the exact shape of the S7.1 escalation.
        """
        moment = consent_logic.as_utc(at) if at else _utcnow()
        summary = self._candidates.get_candidate(candidate_id)
        if summary is None:
            raise LookupError(f"unknown candidate: {candidate_id}")
        if len(content_b64 or "") > self._settings.doc_max_b64_chars:
            raise DocumentTooLargeError(
                f"document exceeds doc_max_b64_chars={self._settings.doc_max_b64_chars}"
            )
        # SQLite does not enforce VARCHAR(n). Without this, `claim_ref` -- the
        # ONE column the "nothing wider than 64 chars" models test excepts --
        # is an unbounded text field a caller can paste a whole document,
        # salary or UAN into, which is precisely the guarantee this subsystem
        # claims to make structurally. Enforced here as well as at the route so
        # a direct service caller cannot bypass it either.
        if len(claim_ref or "") > CLAIM_REF_MAX_CHARS:
            raise DocumentTooLargeError(
                f"claim_ref exceeds {CLAIM_REF_MAX_CHARS} characters; it is a "
                "label, not a place to put document content"
            )

        method = (VerificationMethod.PAYSLIP if doc_type is DocumentType.PAYSLIP
                  else VerificationMethod.EXPERIENCE_LETTER)
        adapter = get_adapter(method)
        if not adapter.self_service:
            raise MethodNotPermittedError(
                f"{method.value} is recorded by an operator, not requested"
            )
        if not adapter.implemented:
            raise NotImplementedError(f"{method.value} verification is not implemented")
        # This route hands the spine a document; a method that has not declared
        # it takes one must not be reachable through it.
        if not adapter.document_based:
            raise MethodNotPermittedError(
                f"{method.value} does not take a document"
            )
        if adapter.third_party:
            grants = self._ledger.consents_for_candidate(candidate_id)
            decision = consent_logic.has_any_active(
                grants, purpose=ConsentPurpose.IDENTITY_VERIFY, at=moment
            )
            if not decision.allowed:
                raise ConsentError(decision.reason)

        # Parse and assess BEFORE writing anything: a body we cannot read must
        # not leave a dangling `pending` row behind (an S7.1 deferred minor
        # that there is no reason to repeat here).
        parsed = parse_document(content_b64, max_pages=self._settings.doc_max_pages)
        profile = self._candidates.latest_profile(candidate_id)
        assessment = assess(
            parsed, profile, doc_type, at=moment,
            metadata_skew_days=self._settings.doc_metadata_skew_days,
        )

        verification = self._store.create_verification(
            candidate_id=candidate_id, method=method,
            subject=VerificationSubject.EMPLOYMENT_CLAIM,
            claim_ref=claim_ref, at=moment,
        )
        completed = self._store.complete_verification(
            verification.id,
            status=assessment.status,
            evidence_digest=parsed.digest,
            details={"findings": [f.model_dump() for f in assessment.findings],
                     "doc_type": doc_type.value},
            at=moment,
        )
        return completed, assessment.findings, self.claims_for_candidate(
            candidate_id, at=moment)

    def claims_for_candidate(
        self, candidate_id: str, *, at: Optional[datetime] = None
    ) -> ClaimEvidence:
        moment = consent_logic.as_utc(at) if at else _utcnow()
        return self._store.claims_for_candidate(
            candidate_id, at=moment, concurrent=self._concurrent(candidate_id, moment)
        )

    def claims_for_org(
        self, *, org_id: str, candidate_id: str, at: Optional[datetime] = None
    ) -> ClaimEvidence:
        moment = consent_logic.as_utc(at) if at else _utcnow()
        return self._store.claims_for_org(
            org_id=org_id, candidate_id=candidate_id, at=moment,
            concurrent=self._concurrent(candidate_id, moment),
        )

    def _concurrent(self, candidate_id: str, moment: datetime):
        """Derived read-time from the candidate's own resume intervals -- never
        stored, because a stored overlap would go stale the moment the resume
        is updated."""
        return assess_concurrent_employment(
            self._candidates.latest_profile(candidate_id),
            today=moment.date(),
            min_months=self._settings.moonlight_min_overlap_months,
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
