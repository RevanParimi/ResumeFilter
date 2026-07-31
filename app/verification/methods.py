"""Verification method adapters (S7.1) -- the seam a real KYC vendor plugs into.

An adapter declares WHAT a method is, not how the spine treats it. In
particular the consent gate lives in the spine, keyed off `third_party`, never
inside an adapter: a gate an adapter could forget to apply is not a gate.

`GovernmentIdAdapter` is deliberately declared and inert. Shipping the slot
(with its level, its third_party flag, and therefore its consent requirement)
means a real DigiLocker/Aadhaar integration is later a new adapter rather than
a schema migration plus a consent retrofit.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from app.verification.schema import AssuranceLevel, VerificationMethod


@runtime_checkable
class VerificationMethodAdapter(Protocol):
    method: VerificationMethod
    level: AssuranceLevel
    third_party: bool      # True => spine requires an IDENTITY_VERIFY grant
    challenge_based: bool  # True => two-step start/confirm
    self_service: bool     # True => a candidate may initiate it themselves
    implemented: bool      # False => the spine refuses; there is no adapter behind it
    instant: bool          # True => assertion IS the evidence; completes on start


class _Base:
    method: VerificationMethod
    level: AssuranceLevel
    third_party: bool = False
    challenge_based: bool = False
    channel: Optional[str] = None
    contact_hash_field: Optional[str] = None
    # Defaults are the SAFE answers: a new adapter is refused by the spine
    # until it says out loud that a candidate may start it, that something
    # actually stands behind it, and how it reaches an outcome.
    self_service: bool = False
    implemented: bool = False
    instant: bool = False


class SelfAttestedAdapter(_Base):
    """The candidate asserts their own identity. Weakest rung, but a real one:
    it records that the claim was made, by whom, and when."""

    method = VerificationMethod.SELF_ATTESTED
    level = AssuranceLevel.SELF_ATTESTED
    self_service = True
    implemented = True
    instant = True


class OtpEmailAdapter(_Base):
    method = VerificationMethod.OTP_EMAIL
    level = AssuranceLevel.CONTACT_CONTROL
    challenge_based = True
    channel = "email"
    contact_hash_field = "email_hash"
    self_service = True
    implemented = True


class OtpPhoneAdapter(_Base):
    method = VerificationMethod.OTP_PHONE
    level = AssuranceLevel.CONTACT_CONTROL
    challenge_based = True
    channel = "phone"
    contact_hash_field = "phone_hash"
    self_service = True
    implemented = True


class ManualReviewAdapter(_Base):
    """An operator checked something out of band and recorded the outcome.

    NOT self-service: this level asserts that a human at the platform looked.
    Reachable only through the admin plane's record_manual_review -- a
    candidate who could start it would simply award themselves L3.
    """

    method = VerificationMethod.MANUAL_REVIEW
    level = AssuranceLevel.REVIEWED
    implemented = True


class GovernmentIdAdapter(_Base):
    """DECLARED, NOT IMPLEMENTED. Needs a vendor and a legal review of
    DigiLocker API terms (gap-analysis section 8).

    `implemented = False` is what actually keeps it inert. The raise below is a
    backstop for a caller that reaches past the spine: the spine performs
    verifications itself and never calls into the adapter, so an adapter-side
    raise alone would let a consented start sail through to a VERIFIED L4.
    Candidate-initiated (`self_service`) is correct and stays true -- the
    consent flow is the point; there is simply nothing behind it yet.
    """

    method = VerificationMethod.GOVERNMENT_ID
    level = AssuranceLevel.GOVERNMENT_ID
    third_party = True
    self_service = True
    implemented = False

    def start(self, *args, **kwargs):
        raise NotImplementedError(
            "government_id verification needs a KYC vendor + legal review (PI-8+)"
        )


ADAPTERS: dict[VerificationMethod, _Base] = {
    VerificationMethod.SELF_ATTESTED: SelfAttestedAdapter(),
    VerificationMethod.OTP_EMAIL: OtpEmailAdapter(),
    VerificationMethod.OTP_PHONE: OtpPhoneAdapter(),
    VerificationMethod.MANUAL_REVIEW: ManualReviewAdapter(),
    VerificationMethod.GOVERNMENT_ID: GovernmentIdAdapter(),
}


def get_adapter(method: VerificationMethod) -> _Base:
    """KeyError for anything outside the taxonomy -- callers validate first."""
    return ADAPTERS[method]
