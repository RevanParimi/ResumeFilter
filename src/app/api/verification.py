"""Candidate verification/documents and consent-gated employer assurance.

Operator manual review retains its separate shared admin/CSRF gate.
Verification services own delivery, evidence policy and persistence.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.dependencies import _services, require_api_key, require_candidate, require_org
from app.ledger.store import ConsentError
from app.core.blocking import ExecutionPending, ExecutionUnavailable
from app.services.email import EmailSendFailed
from app.verification.documents import DocumentParseError
from app.verification.otp import DeliveryUnavailable
from app.verification.schema import (
    CLAIM_REF_MAX_CHARS, ClaimEvidence, DocumentFinding, DocumentType,
    IdentityAssurance, Verification, VerificationMethod, VerificationStatus,
)
from app.verification.service import (
    DestinationError, DocumentTooLargeError, MethodNotPermittedError,
)
from app.verification.store import ChallengeError


candidate_router = APIRouter()
org_router = APIRouter()
router = APIRouter(dependencies=[Depends(require_api_key)])


class StartVerificationResponse(BaseModel):
    verification: Verification
    #: local env + verif_otp_debug_echo ONLY; production can never echo.
    debug_code: Optional[str] = None


class VerificationListResponse(BaseModel):
    verifications: list[Verification] = Field(default_factory=list)
    assurance: IdentityAssurance
    #: S7.2: a SECOND number beside assurance, never folded into it.
    claims: ClaimEvidence


class DocumentSubmitResponse(BaseModel):
    verification: Verification
    findings: list[DocumentFinding] = Field(default_factory=list)
    claims: ClaimEvidence


# ── Identity verification, candidate plane (S7.1) ───────────────────────────
# Candidate-initiated by design. Every handler resolves candidate_id from the
# key — never a path/body param — so cross-candidate isolation is structural.


class StartVerificationRequest(BaseModel):
    """`destination` is required for OTP methods and must match the contact
    hash already on the candidate's record."""

    method: VerificationMethod
    destination: str | None = None


class ConfirmVerificationRequest(BaseModel):
    code: str


class ManualReviewRequest(BaseModel):
    """Operator-recorded verification outcome. `evidence_digest` is a hash of
    whatever was checked out of band -- never the artifact itself."""

    outcome: VerificationStatus
    note: str | None = None
    evidence_digest: str | None = None


@candidate_router.post("/portal/verifications", response_model=StartVerificationResponse)
async def start_verification(
    req: StartVerificationRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> StartVerificationResponse:
    services = _services(request)
    try:
        verification, code = await services.contact_codes.run(services.verification.start,
            candidate_id, req.method, destination=req.destination
        )
    except ExecutionUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={'Retry-After': '1'}) from None
    except ExecutionPending:
        # The worker may still deliver/commit; the candidate must recover saved
        # state rather than replaying an operation whose outcome is uncertain.
        raise HTTPException(status_code=504, detail='contact_code_pending') from None
    except DeliveryUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.detail) from None
    except EmailSendFailed:
        raise HTTPException(status_code=503, detail="email_send_failed") from None
    except DestinationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MethodNotPermittedError as exc:  # e.g. self-awarding a manual review
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ChallengeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    body: dict = {"verification": verification.model_dump(mode="json")}
    # Double-guarded: local env AND the knob. Exists so the sprint smoke can
    # drive the two-step flow over plain HTTP; production can never echo.
    if (
        code is not None
        and services.settings.env == "local"
        and services.settings.verif_otp_debug_echo
    ):
        body["debug_code"] = code
    return body


@candidate_router.post("/portal/verifications/{verification_id}/confirm", response_model=Verification)
async def confirm_verification(
    verification_id: str,
    req: ConfirmVerificationRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> Verification:
    services = _services(request)
    try:
        verification = services.verification.confirm(
            candidate_id, verification_id, req.code
        )
    except LookupError as exc:  # unknown OR not owned — same 404 (no probing)
        raise HTTPException(status_code=404, detail="verification not found") from exc
    except ChallengeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return verification.model_dump(mode="json")


@candidate_router.get("/portal/verifications", response_model=VerificationListResponse)
async def list_verifications(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> VerificationListResponse:
    services = _services(request)
    verifications, assurance = services.verification.list_for_candidate(candidate_id)
    return {
        "verifications": [v.model_dump(mode="json") for v in verifications],
        "assurance": assurance.model_dump(mode="json"),
        # S7.2: a SECOND number beside the first, never folded into it.
        "claims": services.verification.claims_for_candidate(
            candidate_id
        ).model_dump(mode="json"),
    }


@org_router.get("/verification/candidates/{candidate_id}/assurance", response_model=IdentityAssurance)
async def org_candidate_assurance(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> IdentityAssurance:
    """Consent-gated identity assurance. Every attempt — allowed or denied — is
    audited by the store. Returns the advisory roll-up only: never the evidence
    digests, the destination hashes, or the individual attempt rows."""
    try:
        assurance = _services(request).verification.assurance_for_org(
            org_id=org_id, candidate_id=candidate_id
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return assurance.model_dump(mode="json")


# ── Employment-claim documents, candidate plane (S7.2) ──────────────────────
# First-party intake: the candidate submits their OWN letter or payslip. The
# document is parsed in memory and discarded — only a sha256 digest and finding
# CODES survive the request. Org-supplied documents ABOUT a candidate are
# third-party data under DPDP and are deliberately out of scope.


class SubmitDocumentRequest(BaseModel):
    """`content_b64` is a base64 PDF or plain-text body. It is parsed in memory
    and discarded -- only a sha256 digest and finding CODES are stored.
    `claim_ref` is a free-text LABEL (employer + interval), never a selector:
    the candidate is always resolved from the key."""

    doc_type: DocumentType
    content_b64: str
    # Bounded to the column width: SQLite would happily store a whole document
    # in an unbounded VARCHAR(128), and this table's design claim is that no
    # column can hold one. The service enforces the same cap for non-HTTP
    # callers.
    claim_ref: str | None = Field(default=None, max_length=CLAIM_REF_MAX_CHARS)


@candidate_router.post("/portal/documents", response_model=DocumentSubmitResponse)
async def submit_document(
    req: SubmitDocumentRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> DocumentSubmitResponse:
    services = _services(request)
    try:
        verification, findings, claims = await services.verification.asubmit_document(
            candidate_id, req.doc_type, req.content_b64, claim_ref=req.claim_ref,
            executor=services.pdf,
        )
    except DocumentTooLargeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DocumentParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MethodNotPermittedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "verification": verification.model_dump(mode="json"),
        "findings": [f.model_dump(mode="json") for f in findings],
        "claims": claims.model_dump(mode="json"),
    }


@org_router.get("/verification/candidates/{candidate_id}/claims", response_model=ClaimEvidence)
async def org_candidate_claims(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> ClaimEvidence:
    """Consent-gated employment-claim evidence. Every attempt — allowed or
    denied — is audited by the store. Returns the advisory roll-up only: never
    an evidence digest, never a claim_ref, never a document."""
    try:
        claims = _services(request).verification.claims_for_org(
            org_id=org_id, candidate_id=candidate_id
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return claims.model_dump(mode="json")


@router.post("/candidates/{candidate_id}/verifications/manual-review", response_model=Verification)
async def record_manual_review(
    candidate_id: str, req: ManualReviewRequest, request: Request
) -> Verification:
    """Admin plane: an operator checked something out of band (L3 REVIEWED).
    Only a digest of what was checked is stored, never the artifact."""
    try:
        verification = _services(request).verification.record_manual_review(
            candidate_id,
            outcome=req.outcome,
            note=req.note,
            evidence_digest=req.evidence_digest,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return verification.model_dump(mode="json")
