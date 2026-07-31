"""Pure employment-claim folding (S7.2). No I/O, no clock -- the caller passes
`at`, exactly like assurance.py.

Deliberately a SEPARATE roll-up from IdentityAssurance. An experience letter
says a job was real; it says nothing about whether this person is who they
claim to be. One number for both would let a payslip raise a figure orgs read
as identity confidence -- the same failure class as the S7.1 ladder escalation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from app.verification.assurance import effective_status
from app.verification.schema import (
    METHOD_CLAIM_STRENGTH, ClaimEvidence, ClaimStrength, ConcurrentEmployment,
    DocumentFinding, DocumentType, Verification, VerificationStatus,
    VerificationSubject,
)

_METHOD_DOCUMENT: dict[str, DocumentType] = {
    "experience_letter": DocumentType.EXPERIENCE_LETTER,
    "payslip": DocumentType.PAYSLIP,
}


def _findings(v: Verification) -> list[DocumentFinding]:
    """Findings are stored as plain dicts in `details`. A malformed or
    hand-edited row must never 500 a candidate reading their own portal."""
    out: list[DocumentFinding] = []
    for raw in v.details.get("findings", []) or []:
        if not isinstance(raw, dict):
            continue
        try:
            out.append(DocumentFinding(**raw))
        except (TypeError, ValueError):
            continue
    return out


def compute_claim_evidence(
    candidate_id: str,
    verifications: Sequence[Verification],
    *,
    at: datetime,
    concurrent: Optional[ConcurrentEmployment] = None,
) -> ClaimEvidence:
    """Fold a candidate's employment-claim verifications into one advisory
    roll-up. Contributing = VERIFIED and not lapsed.

    Findings from FAILED rows are still surfaced: they are the reason the
    submission failed and the candidate is entitled to see them. Strength is a
    max() over what IS held, so a failed document never lowers anything.
    """
    strength = ClaimStrength.NONE
    documents: list[DocumentType] = []
    findings: list[DocumentFinding] = []

    for v in verifications:
        if v.subject is not VerificationSubject.EMPLOYMENT_CLAIM:
            continue
        findings.extend(_findings(v))
        if effective_status(v, at=at) is not VerificationStatus.VERIFIED:
            continue
        if v.method in METHOD_CLAIM_STRENGTH:
            strength = max(strength, METHOD_CLAIM_STRENGTH[v.method])
        doc = _METHOD_DOCUMENT.get(v.method.value)
        if doc is not None and doc not in documents:
            documents.append(doc)

    return ClaimEvidence(
        candidate_id=candidate_id,
        strength=strength,
        documents=documents,
        findings=findings,
        concurrent_employment=concurrent,
    )
