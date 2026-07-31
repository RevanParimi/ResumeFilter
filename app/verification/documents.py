"""Document parsing + deterministic forensics (S7.2).

NO LLM and no network. These checks are structural and arithmetic, so the
"every LLM step needs a deterministic fallback" convention is satisfied by
having no LLM at all -- the S6.2/S6.3 precedent.

The document does not survive this module. `parse_document` returns text,
metadata and a sha256 digest; the decoded bytes are local and go out of scope.
ParsedDocument deliberately has no field able to hold them.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from app.candidates.normalize.orgs import canonicalize_employer, strip_legal_suffix
from app.candidates.normalize.text import norm_key
from app.candidates.schema import CandidateProfile
from app.fabrication.cross_field import narrow_interval, overlap_months
from app.verification.schema import (
    ClaimStrength, DocumentFinding, DocumentType, VerificationStatus,
)


class DocumentParseError(Exception):
    """The submitted body could not be decoded, was empty, or exceeded the
    page cap. Carries no document content."""


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    page_count: int
    digest: str                       # sha256 of the decoded bytes
    metadata: dict = field(default_factory=dict)


def parse_document(content_b64: str, *, max_pages: int) -> ParsedDocument:
    """Decode, extract text + metadata, and hash. PDF first; anything that is
    not a PDF is treated as a UTF-8 text body, because a pasted letter is still
    assessable and refusing it would push candidates toward worse workarounds.
    """
    try:
        data = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DocumentParseError("content is not valid base64") from exc
    if not data:
        raise DocumentParseError("document is empty")

    digest = hashlib.sha256(data).hexdigest()

    if data[:5] == b"%PDF-":
        from app.core.pdf import pdf_b64_to_document
        try:
            text, pages, meta = pdf_b64_to_document(content_b64)
        except DocumentParseError:
            raise
        except Exception as exc:  # pypdf raises a zoo of types on damaged files
            raise DocumentParseError("document could not be read as a PDF") from exc
        if pages > max_pages:
            raise DocumentParseError(f"document exceeds {max_pages} pages")
        return ParsedDocument(text=text, page_count=pages, digest=digest, metadata=meta)

    text = data.decode("utf-8", errors="replace").strip()
    if not text:
        raise DocumentParseError("document contains no readable text")
    return ParsedDocument(text=text, page_count=1, digest=digest)


# ── Forensics ───────────────────────────────────────────────────────────────
# Deterministic and arithmetic. Every finding is a CODE plus a human-readable
# description of the CHECK -- never of the document's content.

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_DATE_RE = re.compile(
    r"(" + "|".join(_MONTHS) + r")\s+(\d{4})|(\d{4})-(\d{2})", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+\.[\w.-]+)")
_EMPLOYEE_ID_RE = re.compile(r"employee\s*(id|code|no|number)", re.IGNORECASE)
_SIGNATORY_RE = re.compile(
    r"human resources|hr manager|director|authorized signatory|for [A-Z]",
    re.IGNORECASE)
_PDF_DATE_RE = re.compile(r"D:(\d{4})(\d{2})(\d{2})")

# Severity is a CODE CONSTANT, not a config knob: a deploy-time switch that can
# silently reclassify soft -> hard is exactly what schema.py's "taxonomies are
# code constants" stance exists to prevent.
_HARD = "hard"
_SOFT = "soft"
_INFO = "info"


@dataclass(frozen=True)
class DocumentAssessment:
    status: VerificationStatus
    strength: ClaimStrength
    findings: list[DocumentFinding]


def _f(id_: str, severity: str, message: str, **detail) -> DocumentFinding:
    return DocumentFinding(id=id_, severity=severity, message=message, detail=detail)


def _text_months(text: str) -> list[int]:
    """Month indices mentioned in the document, as cross_field's YYYY*12+M-1."""
    out: list[int] = []
    for m in _DATE_RE.finditer(text):
        if m.group(1):
            out.append(int(m.group(2)) * 12 + _MONTHS[m.group(1).lower()] - 1)
        else:
            out.append(int(m.group(3)) * 12 + int(m.group(4)) - 1)
    return sorted(out)


def _pdf_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    m = _PDF_DATE_RE.match(str(value))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _metadata_findings(parsed: ParsedDocument, skew_days: int) -> list[DocumentFinding]:
    created, modified = _pdf_date(parsed.metadata.get("created")), _pdf_date(
        parsed.metadata.get("modified"))
    out: list[DocumentFinding] = []
    if created and modified and (modified - created).days > skew_days:
        out.append(_f("metadata_modified_after_creation", _SOFT,
                      "the file was modified well after it was created",
                      days=(modified - created).days))
    if parsed.metadata.get("producer"):
        out.append(_f("metadata_producer_present", _INFO,
                      "the file records the tool that produced it"))
    return out


def _match_employer(profile: Optional[CandidateProfile], text: str):
    """The resume entry this document appears to be about, or None.

    Matching runs through S1.4's normalization on BOTH sides, and tolerates a
    differently written legal suffix ("Acme Technologies Pvt Ltd" on the resume,
    "ACME TECHNOLOGIES PRIVATE LIMITED" on the letterhead). That tolerance
    matters because "employer not claimed" is one of only two HARD findings --
    a false one is the most expensive mistake this module can make.
    """
    if profile is None:
        return None
    normalized = norm_key(text)
    for entry in profile.experience:
        name = entry.employer or ""
        candidates = {
            norm_key(name),
            strip_legal_suffix(name),
            norm_key(entry.employer_canonical or canonicalize_employer(name) or ""),
        }
        if any(c and c in normalized for c in candidates):
            return entry
    return None


def assess_experience_letter(
    parsed: ParsedDocument,
    profile: Optional[CandidateProfile],
    *,
    at: datetime,
    metadata_skew_days: int,
) -> DocumentAssessment:
    """Deterministic forensics over a letter offered as proof of a role.

    Conservative on purpose: only two things are HARD -- the letter naming an
    employer the resume never claimed, and letter dates that cannot be
    reconciled with the claimed interval. Everything else is soft or
    informational, because letterhead conventions vary enormously across Indian
    employers and a false 'fake' is far more costly than a missed one.
    """
    text = parsed.text
    lowered = text.lower()
    findings: list[DocumentFinding] = []

    if not _EMAIL_RE.search(text):
        findings.append(_f("issuer_domain_unknown", _SOFT,
                           "the letter carries no issuer email domain"))
    if not _EMPLOYEE_ID_RE.search(text):
        findings.append(_f("no_employee_id", _SOFT,
                           "the letter records no employee id"))
    if not _SIGNATORY_RE.search(text):
        findings.append(_f("no_signatory", _SOFT,
                           "the letter names no signatory or issuing office"))

    findings.extend(_metadata_findings(parsed, metadata_skew_days))

    if profile is None or not profile.experience:
        findings.append(_f("no_profile_to_compare", _INFO,
                           "no resume on file to corroborate the letter against"))
        return DocumentAssessment(VerificationStatus.VERIFIED,
                                  ClaimStrength.DOCUMENTED, findings)

    matched = _match_employer(profile, text)
    if matched is None:
        findings.append(_f("employer_not_claimed", _HARD,
                           "the letter's employer does not appear in the resume"))
        return DocumentAssessment(VerificationStatus.FAILED, ClaimStrength.NONE,
                                  findings)

    months = _text_months(text)
    interval = narrow_interval(matched.dates, at.date())
    if months and interval:
        letter_iv = (months[0], months[-1])
        if overlap_months(letter_iv, interval) == 0:
            findings.append(_f("letter_dates_mismatch", _HARD,
                               "the letter's dates do not overlap the claimed role"))
            return DocumentAssessment(VerificationStatus.FAILED, ClaimStrength.NONE,
                                      findings)

    title = (matched.title or "").lower()
    if title and title not in lowered:
        findings.append(_f("designation_mismatch", _SOFT,
                           "the letter's designation differs from the resume"))

    return DocumentAssessment(VerificationStatus.VERIFIED, ClaimStrength.DOCUMENTED,
                              findings)
