"""S7.1 verification contracts -- the spine PI-7 producers write into.

Taxonomies here are code constants, not config: the assurance ladder is a
reviewed schema decision, never a deploy-time tunable (same stance as
InterviewStage/ConsentPurpose). AssuranceLevel is an IntEnum because ordering
is genuinely semantic -- "the highest level a candidate currently holds" is an
ordinary max().

DPDP posture is STRUCTURAL: the only evidence field is `evidence_digest`, a
sha256 hex string. There is deliberately no field capable of holding a
document, image, or biometric, so a future government-ID adapter cannot
persist one without a migration a reviewer would see.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class AssuranceLevel(IntEnum):
    """Ordered ladder. Higher = stronger evidence that the candidate is who
    they claim. Advisory: a level never gates ranking, matching, or scoring."""

    NONE = 0
    SELF_ATTESTED = 1
    CONTACT_CONTROL = 2
    REVIEWED = 3
    GOVERNMENT_ID = 4


class VerificationMethod(StrEnum):
    SELF_ATTESTED = "self_attested"
    OTP_EMAIL = "otp_email"
    OTP_PHONE = "otp_phone"
    MANUAL_REVIEW = "manual_review"
    GOVERNMENT_ID = "government_id"  # declared; no v0 implementation


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"


METHOD_LEVEL: dict[VerificationMethod, AssuranceLevel] = {
    VerificationMethod.SELF_ATTESTED: AssuranceLevel.SELF_ATTESTED,
    VerificationMethod.OTP_EMAIL: AssuranceLevel.CONTACT_CONTROL,
    VerificationMethod.OTP_PHONE: AssuranceLevel.CONTACT_CONTROL,
    VerificationMethod.MANUAL_REVIEW: AssuranceLevel.REVIEWED,
    VerificationMethod.GOVERNMENT_ID: AssuranceLevel.GOVERNMENT_ID,
}


class Verification(BaseModel):
    """One verification attempt and its outcome."""

    id: str
    candidate_id: str
    method: VerificationMethod
    assurance_level: AssuranceLevel
    status: VerificationStatus
    consent_id: Optional[str] = None       # set only for third-party adapters
    evidence_digest: Optional[str] = None  # sha256 hex; NEVER an artifact
    details: dict = Field(default_factory=dict)  # non-PII
    requested_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class IdentityAssurance(BaseModel):
    """Advisory roll-up of a candidate's verifications. Computed at read time,
    never stored: a stored status would go stale the moment an outcome lapsed."""

    candidate_id: str
    level: AssuranceLevel = AssuranceLevel.NONE
    methods: list[VerificationMethod] = Field(default_factory=list)
    verified_at: Optional[datetime] = None       # most recent contributing outcome
    expired_methods: list[VerificationMethod] = Field(default_factory=list)
    advisory: bool = True
