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

from pydantic import BaseModel, Field, field_validator


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
    # --- S7.2 employment-claim methods ---
    EXPERIENCE_LETTER = "experience_letter"
    PAYSLIP = "payslip"
    EPFO_EMPLOYMENT = "epfo_employment"  # declared; needs a BGV vendor


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"


class VerificationSubject(StrEnum):
    """WHAT a verification is about (S7.2). The discriminator that keeps two
    ladders apart: identity answers "is this who they say they are",
    employment_claim answers "is this job history real". Conflating them would
    let a payslip raise a number orgs read as identity confidence.

    It lives up here with the core taxonomies, not in the S7.2 block below,
    because `Verification` itself carries it -- every row has a subject.
    """

    IDENTITY = "identity"
    EMPLOYMENT_CLAIM = "employment_claim"


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
    # S7.2: which ladder this row feeds. Defaults to IDENTITY because every row
    # that predates S7.2 is an identity verification by definition.
    subject: VerificationSubject = VerificationSubject.IDENTITY
    claim_ref: Optional[str] = None        # which employment claim a document backs
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


# ── S7.2: employment-claim contracts ────────────────────────────────────────
# (VerificationSubject sits above, with Verification, which carries it.)


class ClaimStrength(IntEnum):
    """Ordered ladder for employment claims. IntEnum for the same reason
    AssuranceLevel is one: "the strongest evidence currently held" is a max()."""

    NONE = 0
    SELF_REPORTED = 1          # the resume says so, nothing backs it
    DOCUMENTED = 2             # a document backs it and forensics are clean
    CORROBORATED = 3           # document + an independent source agrees
    THIRD_PARTY_VERIFIED = 4   # EPFO et al -- declared, inert (needs a vendor)


class DocumentType(StrEnum):
    EXPERIENCE_LETTER = "experience_letter"
    PAYSLIP = "payslip"


METHOD_SUBJECT: dict[VerificationMethod, VerificationSubject] = {
    VerificationMethod.SELF_ATTESTED: VerificationSubject.IDENTITY,
    VerificationMethod.OTP_EMAIL: VerificationSubject.IDENTITY,
    VerificationMethod.OTP_PHONE: VerificationSubject.IDENTITY,
    VerificationMethod.MANUAL_REVIEW: VerificationSubject.IDENTITY,
    VerificationMethod.GOVERNMENT_ID: VerificationSubject.IDENTITY,
    VerificationMethod.EXPERIENCE_LETTER: VerificationSubject.EMPLOYMENT_CLAIM,
    VerificationMethod.PAYSLIP: VerificationSubject.EMPLOYMENT_CLAIM,
    VerificationMethod.EPFO_EMPLOYMENT: VerificationSubject.EMPLOYMENT_CLAIM,
}

METHOD_CLAIM_STRENGTH: dict[VerificationMethod, ClaimStrength] = {
    VerificationMethod.EXPERIENCE_LETTER: ClaimStrength.DOCUMENTED,
    VerificationMethod.PAYSLIP: ClaimStrength.DOCUMENTED,
    VerificationMethod.EPFO_EMPLOYMENT: ClaimStrength.THIRD_PARTY_VERIFIED,
}

_SEVERITIES = ("info", "soft", "hard")

# Must equal VerificationRow.claim_ref's String(n). SQLite does not enforce
# VARCHAR width, so this constant is the ONLY thing standing between a 128-char
# label and an unbounded text column on a table whose whole design claim is that
# no column can hold an artifact. Enforced at the route AND in the service.
CLAIM_REF_MAX_CHARS = 128


class DocumentFinding(BaseModel):
    """One forensic observation. Advisory, and NON-PII by contract: `message`
    describes the check, never the document's content, and `detail` carries
    coarse buckets only -- never text, salary amounts, or an identifier."""

    id: str                                       # stable code
    severity: str = "soft"                        # info | soft | hard
    message: str
    detail: dict = Field(default_factory=dict)

    @field_validator("severity")
    @classmethod
    def _known_severity(cls, v: str) -> str:
        if v not in _SEVERITIES:
            raise ValueError(f"severity must be one of {_SEVERITIES}")
        return v


class ConcurrentEmployment(BaseModel):
    """Advisory dual-employment signal derived from the candidate's OWN resume
    intervals. Never an accusation: overlapping periods are consulting, notice
    periods and year-only imprecision at least as often as moonlighting."""

    periods: list[str] = Field(default_factory=list)   # "2023-04..2024-02"
    max_overlap_months: int = 0
    severity: str = "info"
    advisory: bool = True


class ClaimEvidence(BaseModel):
    """Advisory roll-up of a candidate's employment-claim verifications.
    Computed at read time, never stored -- same reasoning as IdentityAssurance."""

    candidate_id: str
    strength: ClaimStrength = ClaimStrength.NONE
    documents: list[DocumentType] = Field(default_factory=list)
    findings: list[DocumentFinding] = Field(default_factory=list)
    concurrent_employment: Optional[ConcurrentEmployment] = None
    advisory: bool = True
