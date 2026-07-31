# S7.2 — Document Forensics + Concurrent-Employment Advisory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a candidate submit an experience letter or payslip, assess it with
deterministic forensics, and record the outcome as a claim verification on the
S7.1 spine — without ever storing the document.

**Architecture:** A second producer on the existing `app/verification/` spine
(the S6.1 → S6.2 relationship). Three new pure modules — `documents.py` (parse +
forensics), `claims.py` (the `ClaimEvidence` roll-up), `moonlighting.py`
(concurrent-employment advisory) — plus a `subject` discriminator on the
existing `verifications` table so claim rows and identity rows share storage,
audit, consent and CASCADE while folding into two separate ladders.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 + Alembic on SQLite,
Pydantic v2, pytest. `pypdf` is already a dependency. **No LLM, no network.**

**Spec:** `docs/superpowers/specs/2026-07-31-s72-document-forensics-design.md`

## Global Constraints

- **TDD, fully offline.** `pytest -q` green before every commit. No test may
  touch the network or need an API key.
- **Advisory only.** Nothing here auto-rejects. No effect on depth scoring,
  `fabrication_risk` fusion, matching, or ranking.
- **The document is never stored.** Parse in memory, keep a sha256
  `evidence_digest`, discard the bytes. No column may hold an artifact.
- **`details` is codes, not content.** Never raw document text, never salary
  amounts, never UAN/PF/PAN numbers (presence booleans only).
- **The identity ladder is sacred.** A claim row must never lift
  `IdentityAssurance`. This is the same failure class as the S7.1 escalation.
- **The seam refuses by default.** `_Base` defaults `self_service`,
  `implemented`, `instant` to `False`. Gates live in the spine, never in an
  adapter.
- Config knobs in `config.yaml` + `Settings`; secrets only in `.env` (`DEE_*`).
- Commit messages: no `Co-Authored-By` trailer.
- Branch: `s72-document-forensics` (already created; the spec is committed on it).

**One deliberate deviation from the spec:** spec §8 lists
`doc_unknown_issuer_severity` as a config knob. It is implemented as a **code
constant** instead. Severity vocabulary is a reviewed schema decision, the same
stance `schema.py` takes for the assurance ladder ("taxonomies here are code
constants, not config"). A deploy-time knob that can silently reclassify a
finding from `soft` to `hard` is exactly what that stance exists to prevent.

---

### Task 1: Claim contracts in `schema.py`

**Files:**
- Modify: `app/verification/schema.py`
- Test: `tests/test_verification_claim_schema.py` (create)

**Interfaces:**
- Consumes: existing `VerificationMethod`, `AssuranceLevel`, `METHOD_LEVEL`.
- Produces: `VerificationSubject`, `ClaimStrength`, `DocumentType`,
  `DocumentFinding`, `ConcurrentEmployment`, `ClaimEvidence`,
  `METHOD_SUBJECT`, `METHOD_CLAIM_STRENGTH`, and three new
  `VerificationMethod` members: `EXPERIENCE_LETTER`, `PAYSLIP`,
  `EPFO_EMPLOYMENT`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verification_claim_schema.py
"""S7.2 claim contracts: two ladders, one method table, no ambiguity."""

import pytest

from app.verification.schema import (
    METHOD_CLAIM_STRENGTH, METHOD_LEVEL, METHOD_SUBJECT, ClaimEvidence,
    ClaimStrength, ConcurrentEmployment, DocumentFinding, DocumentType,
    VerificationMethod, VerificationSubject,
)


def test_every_method_declares_exactly_one_subject():
    assert set(METHOD_SUBJECT) == set(VerificationMethod)


def test_identity_methods_and_claim_methods_are_disjoint():
    identity = {m for m, s in METHOD_SUBJECT.items() if s is VerificationSubject.IDENTITY}
    claims = {m for m, s in METHOD_SUBJECT.items() if s is VerificationSubject.EMPLOYMENT_CLAIM}
    assert identity & claims == set()
    assert claims == {
        VerificationMethod.EXPERIENCE_LETTER,
        VerificationMethod.PAYSLIP,
        VerificationMethod.EPFO_EMPLOYMENT,
    }


def test_each_ladder_maps_only_its_own_methods():
    """A claim method has no AssuranceLevel and an identity method has no
    ClaimStrength -- that is what keeps a payslip out of the identity number."""
    for method, subject in METHOD_SUBJECT.items():
        if subject is VerificationSubject.IDENTITY:
            assert method in METHOD_LEVEL
            assert method not in METHOD_CLAIM_STRENGTH
        else:
            assert method in METHOD_CLAIM_STRENGTH
            assert method not in METHOD_LEVEL


def test_claim_strength_is_ordered_so_highest_held_is_a_max():
    assert ClaimStrength.NONE < ClaimStrength.SELF_REPORTED < ClaimStrength.DOCUMENTED
    assert ClaimStrength.DOCUMENTED < ClaimStrength.CORROBORATED
    assert ClaimStrength.CORROBORATED < ClaimStrength.THIRD_PARTY_VERIFIED
    assert int(ClaimStrength.DOCUMENTED) == 2


def test_epfo_is_the_only_third_party_claim_strength():
    assert METHOD_CLAIM_STRENGTH[VerificationMethod.EPFO_EMPLOYMENT] is (
        ClaimStrength.THIRD_PARTY_VERIFIED
    )


def test_a_document_finding_carries_a_code_and_no_document_content():
    f = DocumentFinding(id="issuer_domain_unknown", severity="soft", message="x")
    assert f.detail == {}
    with pytest.raises(ValueError):
        DocumentFinding(id="x", severity="catastrophic", message="y")


def test_claim_evidence_defaults_to_nothing_held_and_is_advisory():
    ev = ClaimEvidence(candidate_id="c1")
    assert ev.strength is ClaimStrength.NONE
    assert ev.documents == [] and ev.findings == []
    assert ev.concurrent_employment is None
    assert ev.advisory is True


def test_concurrent_employment_is_advisory_by_construction():
    ce = ConcurrentEmployment(periods=["2023-04..2024-02"], max_overlap_months=10,
                              severity="soft")
    assert ce.advisory is True


def test_document_types_are_the_two_shipped():
    assert {d.value for d in DocumentType} == {"experience_letter", "payslip"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_claim_schema.py -q`
Expected: FAIL — `ImportError: cannot import name 'VerificationSubject'`.

- [ ] **Step 3: Write minimal implementation**

In `app/verification/schema.py`, add the three new methods to
`VerificationMethod` (leave the existing members untouched):

```python
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
```

Then append:

```python
class VerificationSubject(StrEnum):
    """WHAT a verification is about. The discriminator that keeps two ladders
    apart: identity answers "is this who they say they are", employment_claim
    answers "is this job history real". Conflating them would let a payslip
    raise a number orgs read as identity confidence."""

    IDENTITY = "identity"
    EMPLOYMENT_CLAIM = "employment_claim"


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
```

Add `field_validator` to the pydantic import at the top of the file:

```python
from pydantic import BaseModel, Field, field_validator
```

**Do not** add the claim methods to `METHOD_LEVEL` — the test in Step 1 asserts
they are absent, and that absence is what keeps the ladders apart.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_verification_claim_schema.py -q`
Expected: PASS (9 tests).

Then run the existing suite to prove nothing regressed:
Run: `python -m pytest tests/test_verification_schema.py tests/test_verification_methods.py -q`
Expected: PASS. **If `test_every_method_has_an_adapter` fails, that is correct
and expected** — Task 2 adds the adapters. Leave it failing; do not weaken it.

- [ ] **Step 5: Commit**

```bash
git add app/verification/schema.py tests/test_verification_claim_schema.py
git commit -m "feat(s72): claim contracts — subject discriminator + ClaimStrength ladder"
```

---

### Task 2: Claim adapters on the seam (EPFO declared inert)

**Files:**
- Modify: `app/verification/methods.py`
- Test: `tests/test_verification_methods.py` (extend)

**Interfaces:**
- Consumes: `_Base`, `ADAPTERS`, `get_adapter` from Task 0 (existing S7.1 code);
  `ClaimStrength`, the new methods from Task 1.
- Produces: `ExperienceLetterAdapter`, `PayslipAdapter`, `EpfoEmploymentAdapter`
  registered in `ADAPTERS`; `_Base` gains `document_based: bool = False`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_verification_methods.py`:

```python
def test_document_methods_are_candidate_self_service_and_built():
    from app.verification.schema import DocumentType
    for method in (VerificationMethod.EXPERIENCE_LETTER, VerificationMethod.PAYSLIP):
        a = get_adapter(method)
        assert a.self_service is True
        assert a.implemented is True
        assert a.instant is True          # the outcome is known once assessed
        assert a.challenge_based is False
        assert a.third_party is False
        assert a.document_based is True
        assert a.document_type in set(DocumentType)


def test_epfo_is_declared_but_inert_exactly_like_government_id():
    """Lawful in India, but only via an authorized BGV aggregator -- there is
    no direct API, so there is nothing to implement offline (spec section 3)."""
    a = get_adapter(VerificationMethod.EPFO_EMPLOYMENT)
    assert a.third_party is True          # => spine demands IDENTITY_VERIFY
    assert a.implemented is False         # => spine refuses regardless
    assert a.self_service is True         # candidate-initiated, when it exists
    assert a.document_based is False


def test_only_document_methods_are_document_based():
    based = {m for m, a in ADAPTERS.items() if a.document_based}
    assert based == {VerificationMethod.EXPERIENCE_LETTER, VerificationMethod.PAYSLIP}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_methods.py -q`
Expected: FAIL — `KeyError: <VerificationMethod.EXPERIENCE_LETTER>` from
`get_adapter`, plus the pre-existing `test_every_method_has_an_adapter` failure
from Task 1.

- [ ] **Step 3: Write minimal implementation**

In `app/verification/methods.py`, add `document_based` and `document_type` to
`_Base` (keeping the refusing defaults intact):

```python
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
    # S7.2: True => the spine expects a document body and runs forensics.
    document_based: bool = False
    document_type: Optional[DocumentType] = None
```

Add `DocumentType` and `ClaimStrength` to the `schema` import, add
`document_based` to the `VerificationMethodAdapter` Protocol, then append the
three adapters and register them:

```python
class _ClaimBase(_Base):
    """Employment-claim adapters. `level` is unused for these -- the claim
    ladder is ClaimStrength, resolved from METHOD_CLAIM_STRENGTH -- but the
    attribute stays declared so one Protocol covers both subjects."""

    level = AssuranceLevel.NONE
    self_service = True
    implemented = True
    instant = True          # the outcome is known the moment forensics run
    document_based = True


class ExperienceLetterAdapter(_ClaimBase):
    """A letter from a former employer, offered as proof of a role."""

    method = VerificationMethod.EXPERIENCE_LETTER
    document_type = DocumentType.EXPERIENCE_LETTER


class PayslipAdapter(_ClaimBase):
    """A payslip, offered as proof of employment. Amounts are read for
    arithmetic consistency and then discarded -- never stored (spec section 5)."""

    method = VerificationMethod.PAYSLIP
    document_type = DocumentType.PAYSLIP


class EpfoEmploymentAdapter(_Base):
    """DECLARED, NOT IMPLEMENTED. EPFO/UAN dual-employment checks are lawful in
    India but reachable only through an authorized BGV aggregator holding an
    approved EPFO channel -- there is no direct third-party API (spec section
    3). The blocker is the vendor relationship, not the law.

    Same shape as GovernmentIdAdapter: `implemented = False` is what keeps it
    inert, because the spine never calls an adapter to do the work.
    """

    method = VerificationMethod.EPFO_EMPLOYMENT
    level = AssuranceLevel.NONE
    third_party = True
    self_service = True
    implemented = False

    def start(self, *args, **kwargs):
        raise NotImplementedError(
            "epfo_employment needs an authorized BGV aggregator (PI-8+)"
        )


ADAPTERS: dict[VerificationMethod, _Base] = {
    VerificationMethod.SELF_ATTESTED: SelfAttestedAdapter(),
    VerificationMethod.OTP_EMAIL: OtpEmailAdapter(),
    VerificationMethod.OTP_PHONE: OtpPhoneAdapter(),
    VerificationMethod.MANUAL_REVIEW: ManualReviewAdapter(),
    VerificationMethod.GOVERNMENT_ID: GovernmentIdAdapter(),
    VerificationMethod.EXPERIENCE_LETTER: ExperienceLetterAdapter(),
    VerificationMethod.PAYSLIP: PayslipAdapter(),
    VerificationMethod.EPFO_EMPLOYMENT: EpfoEmploymentAdapter(),
}
```

**Note for the implementer:** the existing
`test_only_self_attestation_completes_instantly` asserts `instant` is exactly
`{SELF_ATTESTED}`. It must now be `{SELF_ATTESTED, EXPERIENCE_LETTER, PAYSLIP}`.
Update that assertion — it is a genuine widening, not a weakening: the property
being protected is "nothing is marked verified on request unless the adapter
says assertion or assessment IS the evidence", and a document that has been
parsed and assessed satisfies it. Likewise
`test_manual_review_is_the_only_method_a_candidate_may_not_initiate` stays true
(claim methods are self-service) and must keep passing unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_verification_methods.py tests/test_verification_claim_schema.py -q`
Expected: PASS, including `test_every_method_has_an_adapter`.

- [ ] **Step 5: Commit**

```bash
git add app/verification/methods.py tests/test_verification_methods.py
git commit -m "feat(s72): experience-letter/payslip adapters; EPFO declared inert"
```

---

### Task 3: `claims.py` roll-up + the identity-isolation invariant

**Files:**
- Create: `app/verification/claims.py`
- Modify: `app/verification/assurance.py`
- Test: `tests/test_verification_claims.py` (create)

**Interfaces:**
- Consumes: `Verification`, `ClaimEvidence`, `ClaimStrength`, `METHOD_SUBJECT`,
  `METHOD_CLAIM_STRENGTH`, `VerificationSubject`, `effective_status`.
- Produces: `compute_claim_evidence(candidate_id, verifications, *, at,
  concurrent=None) -> ClaimEvidence`. Also: `Verification` gains
  `subject: VerificationSubject = VerificationSubject.IDENTITY` and
  `claim_ref: Optional[str] = None`, and `compute_assurance` filters on subject.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verification_claims.py
"""S7.2 roll-up. The load-bearing test in this file is the isolation one:
a payslip must never lift IdentityAssurance."""

from datetime import datetime, timedelta, timezone

from app.verification.assurance import compute_assurance
from app.verification.claims import compute_claim_evidence
from app.verification.schema import (
    AssuranceLevel, ClaimStrength, ConcurrentEmployment, DocumentFinding,
    DocumentType, Verification, VerificationMethod, VerificationStatus,
    VerificationSubject,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _claim(method=VerificationMethod.EXPERIENCE_LETTER,
           status=VerificationStatus.VERIFIED, expires=None, details=None):
    return Verification(
        id=f"v-{method.value}-{status.value}",
        candidate_id="c1",
        method=method,
        assurance_level=AssuranceLevel.NONE,
        subject=VerificationSubject.EMPLOYMENT_CLAIM,
        status=status,
        details=details or {},
        requested_at=NOW,
        completed_at=NOW,
        expires_at=expires,
    )


def _identity(method=VerificationMethod.SELF_ATTESTED):
    return Verification(
        id=f"v-id-{method.value}",
        candidate_id="c1",
        method=method,
        assurance_level=AssuranceLevel.SELF_ATTESTED,
        subject=VerificationSubject.IDENTITY,
        status=VerificationStatus.VERIFIED,
        requested_at=NOW,
        completed_at=NOW,
    )


def test_a_verified_claim_never_lifts_identity_assurance():
    """THE invariant. Same failure class as the S7.1 ladder escalation."""
    a = compute_assurance("c1", [_claim(), _claim(VerificationMethod.PAYSLIP)], at=NOW)
    assert a.level is AssuranceLevel.NONE
    assert a.methods == []


def test_an_identity_verification_never_lifts_claim_strength():
    ev = compute_claim_evidence("c1", [_identity()], at=NOW)
    assert ev.strength is ClaimStrength.NONE
    assert ev.documents == []


def test_the_two_ladders_coexist_on_one_candidate():
    rows = [_identity(), _claim()]
    assert compute_assurance("c1", rows, at=NOW).level is AssuranceLevel.SELF_ATTESTED
    assert compute_claim_evidence("c1", rows, at=NOW).strength is ClaimStrength.DOCUMENTED


def test_strength_is_the_highest_held():
    rows = [_claim(), _claim(VerificationMethod.PAYSLIP)]
    ev = compute_claim_evidence("c1", rows, at=NOW)
    assert ev.strength is ClaimStrength.DOCUMENTED
    assert set(ev.documents) == {DocumentType.EXPERIENCE_LETTER, DocumentType.PAYSLIP}


def test_a_failed_claim_contributes_nothing_but_keeps_its_findings():
    """A bad submission leaves the candidate exactly where they were."""
    failed = _claim(status=VerificationStatus.FAILED, details={
        "findings": [{"id": "payslip_arithmetic_mismatch", "severity": "hard",
                      "message": "gross minus deductions does not equal net"}]
    })
    ev = compute_claim_evidence("c1", [failed], at=NOW)
    assert ev.strength is ClaimStrength.NONE
    assert [f.id for f in ev.findings] == ["payslip_arithmetic_mismatch"]


def test_an_expired_claim_stops_contributing():
    stale = _claim(expires=NOW - timedelta(days=1))
    assert compute_claim_evidence("c1", [stale], at=NOW).strength is ClaimStrength.NONE


def test_findings_from_contributing_rows_are_surfaced():
    row = _claim(details={"findings": [
        {"id": "issuer_domain_unknown", "severity": "soft", "message": "no domain"}
    ]})
    ev = compute_claim_evidence("c1", [row], at=NOW)
    assert [f.id for f in ev.findings] == ["issuer_domain_unknown"]
    assert isinstance(ev.findings[0], DocumentFinding)


def test_malformed_stored_findings_are_skipped_not_fatal():
    """Old or hand-edited rows must not 500 a candidate's own portal."""
    row = _claim(details={"findings": [{"nope": 1}, "not-a-dict"]})
    assert compute_claim_evidence("c1", [row], at=NOW).findings == []


def test_the_concurrent_advisory_is_passed_through_untouched():
    ce = ConcurrentEmployment(periods=["2023-04..2024-02"], max_overlap_months=10,
                              severity="soft")
    ev = compute_claim_evidence("c1", [], at=NOW, concurrent=ce)
    assert ev.concurrent_employment == ce
    assert ev.strength is ClaimStrength.NONE   # an overlap is not evidence FOR a claim


def test_empty_is_none_and_advisory():
    ev = compute_claim_evidence("c1", [], at=NOW)
    assert ev.strength is ClaimStrength.NONE and ev.advisory is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_claims.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.verification.claims'`.

- [ ] **Step 3: Write minimal implementation**

First extend `Verification` in `app/verification/schema.py` (add the two fields
after `status`):

```python
    subject: VerificationSubject = VerificationSubject.IDENTITY
    claim_ref: Optional[str] = None   # which employment claim a document backs
```

Then make `compute_assurance` in `app/verification/assurance.py` subject-aware.
Change the loop body's first line from `for v in verifications:` to:

```python
    for v in verifications:
        # S7.2: two subjects share this table. A document-backed employment
        # claim is evidence about a JOB, not about who the person is, and must
        # never raise a number an org reads as identity confidence.
        if v.subject is not VerificationSubject.IDENTITY:
            continue
```

and add `VerificationSubject` to that module's `schema` import.

Then create `app/verification/claims.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_verification_claims.py tests/test_verification_assurance.py -q`
Expected: PASS (all of both files — the S7.1 assurance tests must be untouched).

- [ ] **Step 5: Commit**

```bash
git add app/verification/claims.py app/verification/assurance.py app/verification/schema.py tests/test_verification_claims.py
git commit -m "feat(s72): ClaimEvidence roll-up; assurance now filters on subject"
```

---

### Task 4: PDF metadata extraction + `parse_document`

**Files:**
- Modify: `app/core/pdf.py`
- Create: `app/verification/documents.py`
- Test: `tests/test_verification_documents_parse.py` (create)

**Interfaces:**
- Consumes: `pypdf`, `DocumentType`.
- Produces: `pdf_b64_to_document(b64: str) -> tuple[str, int, dict]` in
  `app/core/pdf.py`; `ParsedDocument` and
  `parse_document(content_b64: str, *, max_pages: int) -> ParsedDocument` and
  `DocumentParseError` in `app/verification/documents.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verification_documents_parse.py
"""S7.2 parsing: text + page count + metadata + digest, then the bytes go away."""

import base64
import hashlib

import pytest

from app.verification.documents import (
    DocumentParseError, ParsedDocument, parse_document,
)


def _pdf_b64(text: str = "Hello letter", *, producer: str | None = None) -> str:
    """Build a real one-page PDF in memory. pypdf is already a dependency."""
    from pypdf import PdfWriter
    import io
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    if producer:
        w.add_metadata({"/Producer": producer})
    buf = io.BytesIO()
    w.write(buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_a_plain_text_body_parses_without_a_pdf():
    """Not every letter arrives as a PDF; a pasted body is still assessable."""
    b64 = base64.b64encode(b"EXPERIENCE LETTER\nAcme Corp").decode("ascii")
    parsed = parse_document(b64, max_pages=20)
    assert isinstance(parsed, ParsedDocument)
    assert "Acme Corp" in parsed.text
    assert parsed.page_count == 1


def test_a_pdf_parses_and_reports_its_metadata():
    parsed = parse_document(_pdf_b64(producer="LetterMill 9000"), max_pages=20)
    assert parsed.page_count == 1
    assert parsed.metadata.get("producer") == "LetterMill 9000"


def test_the_digest_is_over_the_decoded_bytes():
    raw = b"EXPERIENCE LETTER"
    b64 = base64.b64encode(raw).decode("ascii")
    assert parse_document(b64, max_pages=20).digest == hashlib.sha256(raw).hexdigest()


def test_the_parsed_document_holds_no_reference_to_the_raw_bytes():
    """The bytes must not survive the request -- there is nowhere to put them."""
    parsed = parse_document(base64.b64encode(b"letter body").decode("ascii"), max_pages=20)
    assert not hasattr(parsed, "data")
    assert not hasattr(parsed, "raw")


def test_bad_base64_raises_a_parse_error_not_a_500():
    with pytest.raises(DocumentParseError):
        parse_document("!!!not base64!!!", max_pages=20)


def test_an_empty_document_raises_a_parse_error():
    with pytest.raises(DocumentParseError):
        parse_document(base64.b64encode(b"").decode("ascii"), max_pages=20)


def test_a_page_cap_is_enforced():
    from pypdf import PdfWriter
    import io
    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    with pytest.raises(DocumentParseError):
        parse_document(b64, max_pages=2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_documents_parse.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.verification.documents'`.

- [ ] **Step 3: Write minimal implementation**

Append to `app/core/pdf.py` (leave `pdf_b64_to_text` exactly as it is — the
ingest node and intake route depend on it):

```python
def pdf_b64_to_document(b64: str) -> tuple[str, int, dict]:
    """Text, page count, and normalized metadata. S7.2 forensics need the
    metadata (producer tool, creation-vs-modification skew), which the
    text-only helper deliberately discards."""
    from pypdf import PdfReader

    data = base64.b64decode(b64)
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    raw = reader.metadata or {}
    meta = {
        "producer": raw.get("/Producer"),
        "creator": raw.get("/Creator"),
        "created": raw.get("/CreationDate"),
        "modified": raw.get("/ModDate"),
    }
    return text, len(reader.pages), {k: v for k, v in meta.items() if v}
```

Create `app/verification/documents.py`:

```python
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
from dataclasses import dataclass, field


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_verification_documents_parse.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add app/core/pdf.py app/verification/documents.py tests/test_verification_documents_parse.py
git commit -m "feat(s72): document parsing — text, metadata, digest; bytes never kept"
```

---

### Task 5: Experience-letter forensics

**Files:**
- Modify: `app/verification/documents.py`
- Test: `tests/test_verification_documents_letter.py` (create)

**Interfaces:**
- Consumes: `ParsedDocument`, `CandidateProfile`, `canonicalize_employer`,
  `narrow_interval` / `overlap_months` from `app/fabrication/cross_field.py`.
- Produces: `DocumentAssessment` and
  `assess_experience_letter(parsed, profile, *, at, metadata_skew_days) ->
  DocumentAssessment`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verification_documents_letter.py
"""S7.2 experience-letter forensics. Conservative by construction: a small
Indian employer with no mail domain is SOFT, never HARD."""

from datetime import date, datetime, timezone

from app.candidates.schema import CandidateProfile, DateRange, ExperienceEntry
from app.verification.documents import ParsedDocument, assess_experience_letter
from app.verification.schema import ClaimStrength, VerificationStatus

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)

CLEAN = """
ACME TECHNOLOGIES PRIVATE LIMITED
hr@acme.com

TO WHOM IT MAY CONCERN

This is to certify that Ms. A Candidate (Employee ID ACM-4471) was employed
with Acme Technologies as a Senior Software Engineer from March 2021 to
January 2024.

Sincerely,
R. Sharma
Head of Human Resources
"""


def _profile(employer="Acme Technologies", title="Senior Software Engineer",
             start="2021-03", end="2024-01"):
    return CandidateProfile(
        experience=[ExperienceEntry(
            employer=employer, title=title,
            dates=DateRange(start=start, end=end),
        )]
    )


def _parsed(text=CLEAN, metadata=None):
    return ParsedDocument(text=text, page_count=1, digest="d" * 64,
                          metadata=metadata or {})


def _ids(assessment):
    return {f.id for f in assessment.findings}


def test_a_clean_letter_is_documented_and_verified():
    a = assess_experience_letter(_parsed(), _profile(), at=NOW, metadata_skew_days=1)
    assert a.status is VerificationStatus.VERIFIED
    assert a.strength is ClaimStrength.DOCUMENTED
    assert not [f for f in a.findings if f.severity == "hard"]


def test_dates_that_contradict_the_resume_are_a_hard_finding():
    a = assess_experience_letter(
        _parsed(), _profile(start="2018-01", end="2019-01"), at=NOW,
        metadata_skew_days=1,
    )
    assert "letter_dates_mismatch" in _ids(a)
    assert a.status is VerificationStatus.FAILED
    assert a.strength is ClaimStrength.NONE


def test_an_employer_absent_from_the_resume_is_a_hard_finding():
    a = assess_experience_letter(
        _parsed(), _profile(employer="Globex Corp"), at=NOW, metadata_skew_days=1,
    )
    assert "employer_not_claimed" in _ids(a)
    assert a.status is VerificationStatus.FAILED


def test_a_missing_issuer_domain_is_soft_never_hard():
    """Small Indian employers legitimately have no mail domain."""
    text = CLEAN.replace("hr@acme.com", "")
    a = assess_experience_letter(_parsed(text), _profile(), at=NOW, metadata_skew_days=1)
    assert "issuer_domain_unknown" in _ids(a)
    assert all(f.severity != "hard" for f in a.findings)
    assert a.status is VerificationStatus.VERIFIED


def test_a_missing_signatory_and_employee_id_are_mill_markers():
    text = "This certifies employment with Acme Technologies from March 2021 to January 2024."
    a = assess_experience_letter(_parsed(text), _profile(), at=NOW, metadata_skew_days=1)
    assert {"no_signatory", "no_employee_id"} <= _ids(a)


def test_a_designation_that_disagrees_is_soft():
    a = assess_experience_letter(
        _parsed(), _profile(title="Principal Architect"), at=NOW, metadata_skew_days=1,
    )
    assert "designation_mismatch" in _ids(a)
    assert a.status is VerificationStatus.VERIFIED   # titles drift legitimately


def test_metadata_skew_between_creation_and_modification_is_flagged():
    a = assess_experience_letter(
        _parsed(metadata={"created": "D:20240101120000", "modified": "D:20260101120000"}),
        _profile(), at=NOW, metadata_skew_days=1,
    )
    assert "metadata_modified_after_creation" in _ids(a)


def test_identical_creation_and_modification_are_not_flagged():
    a = assess_experience_letter(
        _parsed(metadata={"created": "D:20240101120000", "modified": "D:20240101120000"}),
        _profile(), at=NOW, metadata_skew_days=1,
    )
    assert "metadata_modified_after_creation" not in _ids(a)


def test_no_profile_on_file_means_no_corroboration_not_a_failure():
    a = assess_experience_letter(_parsed(), None, at=NOW, metadata_skew_days=1)
    assert "no_profile_to_compare" in _ids(a)
    assert a.status is VerificationStatus.VERIFIED
    assert a.strength is ClaimStrength.DOCUMENTED


def test_no_finding_ever_carries_document_text():
    a = assess_experience_letter(_parsed(), _profile(employer="Globex Corp"), at=NOW,
                                 metadata_skew_days=1)
    blob = " ".join(f.message + str(f.detail) for f in a.findings)
    assert "R. Sharma" not in blob
    assert "ACM-4471" not in blob
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_documents_letter.py -q`
Expected: FAIL — `ImportError: cannot import name 'assess_experience_letter'`.

- [ ] **Step 3: Write minimal implementation**

Append to `app/verification/documents.py`:

```python
import re
from datetime import date, datetime
from typing import Optional

from app.candidates.normalize.orgs import canonicalize_employer
from app.candidates.schema import CandidateProfile
from app.fabrication.cross_field import narrow_interval, overlap_months
from app.verification.schema import (
    ClaimStrength, DocumentFinding, VerificationStatus,
)

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
    """Month indices mentioned in the letter, as cross_field's YYYY*12+M-1."""
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

    matched = None
    for entry in profile.experience:
        name = entry.employer or ""
        canon = entry.employer_canonical or canonicalize_employer(name)
        candidates = {name.lower(), (canon or "").lower()}
        if any(c and c in lowered for c in candidates):
            matched = entry
            break

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
```

Add `from dataclasses import dataclass, field` is already at the top of the
module from Task 4 — extend that import rather than duplicating it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_verification_documents_letter.py tests/test_verification_documents_parse.py -q`
Expected: PASS (18 tests).

- [ ] **Step 5: Commit**

```bash
git add app/verification/documents.py tests/test_verification_documents_letter.py
git commit -m "feat(s72): experience-letter forensics — issuer, dates, mill markers"
```

---

### Task 6: Payslip forensics

**Files:**
- Modify: `app/verification/documents.py`
- Test: `tests/test_verification_documents_payslip.py` (create)

**Interfaces:**
- Consumes: `ParsedDocument`, `DocumentAssessment`, `CandidateProfile`.
- Produces: `assess_payslip(parsed, profile, *, at, metadata_skew_days) ->
  DocumentAssessment` and `assess(parsed, profile, doc_type, *, at,
  metadata_skew_days) -> DocumentAssessment` (the dispatcher the service calls).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verification_documents_payslip.py
"""S7.2 payslip forensics. The arithmetic is the signal; the AMOUNTS are not
kept -- comp has its own consented path (S5.2) and this is not a back door."""

from datetime import datetime, timezone

from app.candidates.schema import CandidateProfile, DateRange, ExperienceEntry
from app.verification.documents import ParsedDocument, assess, assess_payslip
from app.verification.schema import (
    ClaimStrength, DocumentType, VerificationStatus,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)

CONSISTENT = """
ACME TECHNOLOGIES PRIVATE LIMITED
Payslip for March 2023
Employee: A Candidate     UAN: 100234567890
Gross Salary: 100000
Total Deductions: 22000
Net Pay: 78000
"""

INCONSISTENT = CONSISTENT.replace("Net Pay: 78000", "Net Pay: 95000")


def _profile(employer="Acme Technologies", start="2021-03", end="2024-01"):
    return CandidateProfile(experience=[ExperienceEntry(
        employer=employer, title="Engineer", dates=DateRange(start=start, end=end))])


def _parsed(text=CONSISTENT):
    return ParsedDocument(text=text, page_count=1, digest="d" * 64, metadata={})


def _ids(a):
    return {f.id for f in a.findings}


def test_a_consistent_payslip_is_documented():
    a = assess_payslip(_parsed(), _profile(), at=NOW, metadata_skew_days=1)
    assert a.status is VerificationStatus.VERIFIED
    assert a.strength is ClaimStrength.DOCUMENTED


def test_arithmetic_that_does_not_add_up_is_hard():
    a = assess_payslip(_parsed(INCONSISTENT), _profile(), at=NOW, metadata_skew_days=1)
    assert "payslip_arithmetic_mismatch" in _ids(a)
    assert a.status is VerificationStatus.FAILED
    assert a.strength is ClaimStrength.NONE


def test_an_employer_absent_from_the_resume_is_hard():
    a = assess_payslip(_parsed(), _profile(employer="Globex Corp"), at=NOW,
                       metadata_skew_days=1)
    assert "employer_not_claimed" in _ids(a)
    assert a.status is VerificationStatus.FAILED


def test_a_pay_period_outside_the_claimed_role_is_hard():
    a = assess_payslip(_parsed(), _profile(start="2015-01", end="2016-01"), at=NOW,
                       metadata_skew_days=1)
    assert "payslip_period_outside_role" in _ids(a)
    assert a.status is VerificationStatus.FAILED


def test_uan_presence_is_recorded_but_the_number_never_is():
    a = assess_payslip(_parsed(), _profile(), at=NOW, metadata_skew_days=1)
    assert "uan_present" in _ids(a)
    blob = " ".join(f.message + str(f.detail) for f in a.findings)
    assert "100234567890" not in blob


def test_no_finding_carries_a_salary_amount():
    """Comp intelligence is consented and k-anonymised (S5.2). A payslip must
    not become a back door into it."""
    for text in (CONSISTENT, INCONSISTENT):
        a = assess_payslip(_parsed(text), _profile(), at=NOW, metadata_skew_days=1)
        blob = " ".join(f.message + str(f.detail) for f in a.findings)
        for amount in ("100000", "78000", "95000", "22000"):
            assert amount not in blob


def test_a_payslip_with_no_recognisable_amounts_is_soft_not_hard():
    a = assess_payslip(_parsed("Payslip for March 2023\nAcme Technologies"),
                       _profile(), at=NOW, metadata_skew_days=1)
    assert "payslip_amounts_unreadable" in _ids(a)
    assert a.status is VerificationStatus.VERIFIED


def test_the_dispatcher_routes_by_document_type():
    letter = assess(_parsed("Employed with Acme Technologies from March 2021 to "
                            "January 2024. Head of Human Resources."),
                    _profile(), DocumentType.EXPERIENCE_LETTER, at=NOW,
                    metadata_skew_days=1)
    slip = assess(_parsed(), _profile(), DocumentType.PAYSLIP, at=NOW,
                  metadata_skew_days=1)
    assert letter.status is VerificationStatus.VERIFIED
    assert "uan_present" in _ids(slip)          # only the payslip path checks UAN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_documents_payslip.py -q`
Expected: FAIL — `ImportError: cannot import name 'assess_payslip'`.

- [ ] **Step 3: Write minimal implementation**

Append to `app/verification/documents.py`:

```python
_AMOUNT_RE = re.compile(
    r"(gross|total deductions|deductions|net pay|net salary)\s*(?:salary)?\s*[:\-]?\s*"
    r"(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
_UAN_RE = re.compile(r"\b(uan|pf\s*(no|number|account))\b", re.IGNORECASE)
_TOLERANCE = 1.0   # rupees; absorbs rounding, not a discrepancy


def _amounts(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for label, amount in _AMOUNT_RE.findall(text):
        key = label.lower()
        key = ("gross" if key.startswith("gross")
               else "net" if key.startswith("net")
               else "deductions")
        try:
            out.setdefault(key, float(amount.replace(",", "")))
        except ValueError:
            continue
    return out


def assess_payslip(
    parsed: ParsedDocument,
    profile: Optional[CandidateProfile],
    *,
    at: datetime,
    metadata_skew_days: int,
) -> DocumentAssessment:
    """Deterministic forensics over a payslip.

    Amounts are read to check that gross - deductions == net and are then
    DISCARDED. No finding may carry a figure: comp intelligence is consented
    and k-anonymised (S5.2), and a payslip must not become a back door into it.
    """
    text = parsed.text
    lowered = text.lower()
    findings: list[DocumentFinding] = []

    if _UAN_RE.search(text):
        findings.append(_f("uan_present", _INFO,
                           "the payslip references a UAN/PF account (number not stored)"))

    findings.extend(_metadata_findings(parsed, metadata_skew_days))

    amounts = _amounts(text)
    if {"gross", "deductions", "net"} <= set(amounts):
        if abs(amounts["gross"] - amounts["deductions"] - amounts["net"]) > _TOLERANCE:
            findings.append(_f("payslip_arithmetic_mismatch", _HARD,
                               "gross minus deductions does not equal net pay"))
            return DocumentAssessment(VerificationStatus.FAILED, ClaimStrength.NONE,
                                      findings)
    else:
        findings.append(_f("payslip_amounts_unreadable", _SOFT,
                           "the payslip's amounts could not be read for a "
                           "consistency check"))

    if profile is None or not profile.experience:
        findings.append(_f("no_profile_to_compare", _INFO,
                           "no resume on file to corroborate the payslip against"))
        return DocumentAssessment(VerificationStatus.VERIFIED,
                                  ClaimStrength.DOCUMENTED, findings)

    matched = None
    for entry in profile.experience:
        name = entry.employer or ""
        canon = entry.employer_canonical or canonicalize_employer(name)
        if any(c and c in lowered for c in {name.lower(), (canon or "").lower()}):
            matched = entry
            break

    if matched is None:
        findings.append(_f("employer_not_claimed", _HARD,
                           "the payslip's employer does not appear in the resume"))
        return DocumentAssessment(VerificationStatus.FAILED, ClaimStrength.NONE,
                                  findings)

    months = _text_months(text)
    interval = narrow_interval(matched.dates, at.date())
    if months and interval and overlap_months((months[0], months[-1]), interval) == 0:
        findings.append(_f("payslip_period_outside_role", _HARD,
                           "the pay period falls outside the claimed role"))
        return DocumentAssessment(VerificationStatus.FAILED, ClaimStrength.NONE,
                                  findings)

    return DocumentAssessment(VerificationStatus.VERIFIED, ClaimStrength.DOCUMENTED,
                              findings)


def assess(
    parsed: ParsedDocument,
    profile: Optional[CandidateProfile],
    doc_type: DocumentType,
    *,
    at: datetime,
    metadata_skew_days: int,
) -> DocumentAssessment:
    """Dispatch to the right forensics. The spine calls only this."""
    if doc_type is DocumentType.PAYSLIP:
        return assess_payslip(parsed, profile, at=at,
                              metadata_skew_days=metadata_skew_days)
    return assess_experience_letter(parsed, profile, at=at,
                                    metadata_skew_days=metadata_skew_days)
```

Add `DocumentType` to the `app.verification.schema` import at the top of the
module.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_verification_documents_payslip.py tests/test_verification_documents_letter.py -q`
Expected: PASS (18 tests).

- [ ] **Step 5: Commit**

```bash
git add app/verification/documents.py tests/test_verification_documents_payslip.py
git commit -m "feat(s72): payslip forensics — arithmetic, period, UAN presence only"
```

---

### Task 7: Concurrent-employment advisory

**Files:**
- Create: `app/verification/moonlighting.py`
- Modify: `app/fabrication/cross_field.py` (expose `ym_label`)
- Test: `tests/test_verification_moonlighting.py` (create)

**Interfaces:**
- Consumes: `narrow_interval`, `overlap_months`, `_primary` logic;
  `CandidateProfile`.
- Produces: `ym_label(idx: int) -> str` (public) in `cross_field.py`;
  `assess_concurrent_employment(profile, *, today, min_months) ->
  Optional[ConcurrentEmployment]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verification_moonlighting.py
"""S7.2 concurrent-employment advisory. Derived from the candidate's OWN
resume intervals, computed at read time, never stored, never an accusation."""

from datetime import date

from app.candidates.schema import CandidateProfile, DateRange, ExperienceEntry
from app.verification.moonlighting import assess_concurrent_employment

TODAY = date(2026, 7, 31)


def _p(*ranges):
    return CandidateProfile(experience=[
        ExperienceEntry(employer=f"Emp{i}", title="Engineer",
                        dates=DateRange(start=s, end=e))
        for i, (s, e) in enumerate(ranges)
    ])


def test_non_overlapping_roles_produce_no_advisory():
    assert assess_concurrent_employment(
        _p(("2020-01", "2021-12"), ("2022-01", "2023-12")), today=TODAY, min_months=12
    ) is None


def test_a_long_overlap_is_surfaced_with_its_period_and_months():
    ce = assess_concurrent_employment(
        _p(("2021-01", "2023-12"), ("2022-01", "2023-12")), today=TODAY, min_months=12
    )
    assert ce is not None
    assert ce.max_overlap_months == 24
    assert ce.periods == ["2022-01..2023-12"]
    assert ce.advisory is True


def test_an_overlap_below_the_threshold_is_ignored():
    """The threshold is deliberately higher than the S2.2 fabrication check:
    a 3-month overlap is a notice period, not a second job."""
    assert assess_concurrent_employment(
        _p(("2021-01", "2022-03"), ("2022-01", "2023-12")), today=TODAY, min_months=12
    ) is None


def test_severity_rises_with_the_length_of_the_overlap():
    short = assess_concurrent_employment(
        _p(("2021-01", "2022-06"), ("2022-01", "2023-12")), today=TODAY, min_months=6)
    long = assess_concurrent_employment(
        _p(("2019-01", "2023-12"), ("2020-01", "2023-12")), today=TODAY, min_months=6)
    assert short.severity == "info"
    assert long.severity == "soft"


def test_internships_and_freelance_do_not_count_as_concurrent_primary_roles():
    from app.candidates.schema import EmploymentType
    profile = CandidateProfile(experience=[
        ExperienceEntry(employer="A", dates=DateRange(start="2021-01", end="2023-12")),
        ExperienceEntry(employer="B", dates=DateRange(start="2021-01", end="2023-12"),
                        employment_type=EmploymentType.INTERNSHIP),
    ])
    assert assess_concurrent_employment(profile, today=TODAY, min_months=12) is None


def test_an_empty_or_undated_profile_is_no_advisory_not_an_error():
    assert assess_concurrent_employment(CandidateProfile(), today=TODAY,
                                        min_months=12) is None
    assert assess_concurrent_employment(
        _p((None, None), (None, None)), today=TODAY, min_months=12) is None


def test_multiple_overlapping_pairs_all_appear():
    ce = assess_concurrent_employment(
        _p(("2020-01", "2023-12"), ("2021-01", "2023-12"), ("2022-01", "2023-12")),
        today=TODAY, min_months=12,
    )
    assert len(ce.periods) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_moonlighting.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.verification.moonlighting'`.

- [ ] **Step 3: Write minimal implementation**

In `app/fabrication/cross_field.py`, add a public alias directly below `_ym`
(leave `_ym` and every existing caller alone):

```python
def ym_label(idx: int) -> str:
    """Public form of the month-index formatter. S7.2's advisory renders the
    same interval arithmetic, and one formatter avoids two notions of "when"."""
    return _ym(idx)
```

Create `app/verification/moonlighting.py`:

```python
"""Concurrent-employment advisory (S7.2).

Derived, never stored. The overlap arithmetic already exists -- S2.2's
`check_timeline_overlaps` has computed it since PI-2 -- so this module reuses
that machinery rather than growing a second notion of "when". Storing the
result would go stale exactly as a stored assurance would.

This is NOT an accusation. Overlapping intervals are consulting, notice
periods, and year-only date imprecision at least as often as dual employment,
so the threshold is deliberately higher than the fabrication check's and the
output tops out at "soft".
"""

from __future__ import annotations

import itertools
from datetime import date
from typing import Optional

from app.candidates.schema import CandidateProfile, EmploymentType
from app.fabrication.cross_field import narrow_interval, overlap_months, ym_label
from app.verification.schema import ConcurrentEmployment

_NON_PRIMARY = {EmploymentType.INTERNSHIP, EmploymentType.FREELANCE}
_SOFT_MONTHS = 24   # two years of concurrency is worth a conversation


def assess_concurrent_employment(
    profile: Optional[CandidateProfile], *, today: date, min_months: int
) -> Optional[ConcurrentEmployment]:
    """Advisory overlap between concurrent PRIMARY roles, or None."""
    if profile is None or not profile.experience:
        return None

    dated = [
        (e, iv)
        for e in profile.experience
        if e.employment_type not in _NON_PRIMARY
        and (iv := narrow_interval(e.dates, today)) is not None
    ]

    periods: list[str] = []
    longest = 0
    for (_, ia), (_, ib) in itertools.combinations(dated, 2):
        months = overlap_months(ia, ib)
        if months < min_months:
            continue
        start, end = max(ia[0], ib[0]), min(ia[1], ib[1])
        label = f"{ym_label(start)}..{ym_label(end)}"
        if label not in periods:
            periods.append(label)
        longest = max(longest, months)

    if not periods:
        return None
    return ConcurrentEmployment(
        periods=periods,
        max_overlap_months=longest,
        severity="soft" if longest >= _SOFT_MONTHS else "info",
    )
```

**Note for the implementer:** confirm `EmploymentType` member names in
`app/candidates/schema.py` before writing `_NON_PRIMARY` — mirror whatever
`cross_field._NON_PRIMARY` uses, so the two modules agree on what "primary"
means. If they differ, the cross_field definition wins.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_verification_moonlighting.py tests/test_cross_field.py -q`
Expected: PASS. The existing cross-field tests must be untouched.

- [ ] **Step 5: Commit**

```bash
git add app/verification/moonlighting.py app/fabrication/cross_field.py tests/test_verification_moonlighting.py
git commit -m "feat(s72): concurrent-employment advisory, derived read-time from S2.2 overlaps"
```

---

### Task 8: `subject`/`claim_ref` columns + migration `0014`

**Files:**
- Modify: `app/verification/models.py`
- Create: `alembic/versions/0014_verification_subject.py`
- Test: `tests/test_verification_models.py` (extend), `tests/test_migrations.py` (extend)

**Interfaces:**
- Consumes: existing `VerificationRow`.
- Produces: `VerificationRow.subject` (String(24), NOT NULL, indexed) and
  `VerificationRow.claim_ref` (String(128), nullable).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_verification_models.py`:

```python
def test_a_verification_row_records_its_subject_and_claim_ref():
    from app.verification.models import VerificationRow
    cols = VerificationRow.__table__.columns
    assert cols["subject"].nullable is False
    assert cols["claim_ref"].nullable is True
    assert cols["subject"].index is True


def test_the_subject_column_defaults_to_identity_for_pre_s72_rows():
    from app.verification.models import VerificationRow
    assert VerificationRow.__table__.columns["subject"].default.arg == "identity"


def test_still_no_column_can_hold_a_document():
    """S7.2 is where the S7.1 structural rule earns its keep: a real document
    is now on the wire and there is still nowhere to put it."""
    from app.verification.models import VerificationChallengeRow, VerificationRow
    for table in (VerificationRow.__table__, VerificationChallengeRow.__table__):
        for col in table.columns:
            assert not isinstance(col.type, (sa.LargeBinary, sa.Text)), col.name
            if isinstance(col.type, sa.String) and col.name != "claim_ref":
                assert (col.type.length or 0) <= 64, col.name
```

Add `import sqlalchemy as sa` to that test file if it is not already imported.

In `tests/test_migrations.py`, the existing drift/index/FK/nullability guards
are metadata-wide and will fail automatically once the model changes and the
migration does not match. Add one explicit test:

```python
def test_0014_backfills_existing_verifications_to_identity():
    """A pre-S7.2 row is an identity verification by definition -- it predates
    the existence of any other subject."""
    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config

    url, cfg = _scratch_config()          # existing helper in this module
    command.upgrade(cfg, "0013_identity_verification")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO candidates (id, full_name, created_at, updated_at) "
            "VALUES ('c1', 'A', '2026-01-01', '2026-01-01')"))
        conn.execute(sa.text(
            "INSERT INTO verifications (id, candidate_id, method, assurance_level,"
            " status, details, requested_at, created_at) VALUES "
            "('v1', 'c1', 'self_attested', 1, 'verified', '{}', "
            "'2026-01-01', '2026-01-01')"))
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        got = conn.execute(sa.text("SELECT subject FROM verifications")).scalar_one()
    assert got == "identity"
```

**Note for the implementer:** `_scratch_config()` is illustrative — use
whatever scratch-DB helper `tests/test_migrations.py` already defines, and
match the existing column list on `candidates` for the INSERT.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_verification_models.py tests/test_migrations.py -q`
Expected: FAIL — `KeyError: 'subject'`.

- [ ] **Step 3: Write minimal implementation**

In `app/verification/models.py`, add to `VerificationRow` after `status`:

```python
    # S7.2: which ladder this row feeds. Pre-S7.2 rows are identity by
    # definition -- they predate the existence of any other subject.
    subject: Mapped[str] = mapped_column(String(24), index=True, default="identity")
    # Which employment claim a document backs (employer label + interval), so
    # two letters for two employers do not collapse into one.
    claim_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
```

Create `alembic/versions/0014_verification_subject.py`:

```python
"""verification subject discriminator + claim_ref (S7.2)

Revision ID: 0014_verification_subject
Revises: 0013_identity_verification
Create Date: 2026-07-31

Existing rows backfill to 'identity': they predate the existence of any other
subject, so that is not a guess. The server_default is added for the backfill
and then dropped, so the application stays the source of truth for new rows --
the 0004 precedent.
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_verification_subject"
down_revision = "0013_identity_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("verifications") as batch:
        batch.add_column(sa.Column("subject", sa.String(length=24), nullable=False,
                                   server_default="identity"))
        batch.add_column(sa.Column("claim_ref", sa.String(length=128), nullable=True))
    op.create_index("ix_verifications_subject", "verifications", ["subject"])
    with op.batch_alter_table("verifications") as batch:
        batch.alter_column("subject", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_verifications_subject", table_name="verifications")
    with op.batch_alter_table("verifications") as batch:
        batch.drop_column("claim_ref")
        batch.drop_column("subject")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_migrations.py tests/test_verification_models.py -q`
Expected: PASS, including the metadata-wide drift/index/nullability guards.

- [ ] **Step 5: Commit**

```bash
git add app/verification/models.py alembic/versions/0014_verification_subject.py tests/test_verification_models.py tests/test_migrations.py
git commit -m "feat(s72): verifications.subject + claim_ref, migration 0014 with backfill"
```

---

### Task 9: Store — subject-aware writes, claim reads, consent-gated org read

**Files:**
- Modify: `app/verification/store.py`
- Test: `tests/test_verification_claim_store.py` (create)

**Interfaces:**
- Consumes: `compute_claim_evidence`, `METHOD_SUBJECT`, `ConcurrentEmployment`.
- Produces: `create_verification(..., subject=..., claim_ref=...)`;
  `claims_for_candidate(candidate_id, *, at=None, concurrent=None) ->
  ClaimEvidence`; `claims_for_org(*, org_id, candidate_id, at=None,
  concurrent=None) -> ClaimEvidence`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verification_claim_store.py
"""S7.2 store: claim rows persist with their subject, and the org read is
consent-gated and audited BOTH ways -- exactly like assurance_for_org."""

from datetime import datetime, timezone

import pytest

from app.candidates.models import CandidateRow
from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError, LedgerStore
from app.verification.schema import (
    ClaimStrength, VerificationMethod, VerificationStatus, VerificationSubject,
)
from app.verification.store import VerificationStore
from tests.conftest import make_candidate_store

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def bundle(settings):
    candidates = make_candidate_store()
    ledger = LedgerStore(candidates._session_factory,
                         default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
                         settings=settings)
    store = VerificationStore(candidates._session_factory, ledger=ledger, settings=settings)
    with candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash="e" * 64)
        s.add(row)
        s.commit()
        cid = row.id
    org = ledger.create_organization(name="Acme")
    return store, ledger, cid, org.id


def _claim_row(store, cid, method=VerificationMethod.EXPERIENCE_LETTER):
    v = store.create_verification(
        candidate_id=cid, method=method,
        subject=VerificationSubject.EMPLOYMENT_CLAIM,
        claim_ref="Acme Technologies|2021-03..2024-01", at=NOW,
    )
    return store.complete_verification(
        v.id, status=VerificationStatus.VERIFIED,
        evidence_digest="a" * 64,
        details={"findings": [{"id": "issuer_domain_unknown", "severity": "soft",
                               "message": "no domain"}]},
        at=NOW,
    )


def test_a_claim_row_round_trips_with_its_subject_and_ref(bundle):
    store, _, cid, _ = bundle
    v = _claim_row(store, cid)
    assert v.subject is VerificationSubject.EMPLOYMENT_CLAIM
    assert v.claim_ref == "Acme Technologies|2021-03..2024-01"
    assert store.get_verification(v.id).subject is VerificationSubject.EMPLOYMENT_CLAIM


def test_identity_rows_still_default_to_the_identity_subject(bundle):
    store, _, cid, _ = bundle
    v = store.create_verification(candidate_id=cid,
                                  method=VerificationMethod.SELF_ATTESTED, at=NOW)
    assert v.subject is VerificationSubject.IDENTITY


def test_claims_for_candidate_folds_only_claim_rows(bundle):
    store, _, cid, _ = bundle
    store.create_verification(candidate_id=cid,
                              method=VerificationMethod.SELF_ATTESTED, at=NOW)
    _claim_row(store, cid)
    ev = store.claims_for_candidate(cid, at=NOW)
    assert ev.strength is ClaimStrength.DOCUMENTED
    assert store.assurance_for_candidate(cid, at=NOW).level == 0   # unlifted


def test_the_org_read_is_refused_without_a_verification_read_grant(bundle):
    store, _, cid, org_id = bundle
    _claim_row(store, cid)
    with pytest.raises(ConsentError):
        store.claims_for_org(org_id=org_id, candidate_id=cid, at=NOW)


def test_the_org_read_succeeds_under_a_grant(bundle):
    store, ledger, cid, org_id = bundle
    _claim_row(store, cid)
    ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ,
                         org_id=org_id)
    ev = store.claims_for_org(org_id=org_id, candidate_id=cid, at=NOW)
    assert ev.strength is ClaimStrength.DOCUMENTED


def test_every_org_attempt_is_audited_allowed_or_denied(bundle):
    store, ledger, cid, org_id = bundle
    _claim_row(store, cid)
    with pytest.raises(ConsentError):
        store.claims_for_org(org_id=org_id, candidate_id=cid, at=NOW)
    ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ,
                         org_id=org_id)
    store.claims_for_org(org_id=org_id, candidate_id=cid, at=NOW)

    queries = [e for e in ledger.audit_for_candidate(cid) if e.action == "claim.query"]
    assert [e.details.get("allowed") for e in queries] == [False, True]


def test_an_unknown_candidate_or_org_is_a_lookup_error(bundle):
    store, _, cid, org_id = bundle
    with pytest.raises(LookupError):
        store.claims_for_org(org_id=org_id, candidate_id="nope", at=NOW)
    with pytest.raises(LookupError):
        store.claims_for_org(org_id="nope", candidate_id=cid, at=NOW)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_claim_store.py -q`
Expected: FAIL — `TypeError: create_verification() got an unexpected keyword
argument 'subject'`.

- [ ] **Step 3: Write minimal implementation**

In `app/verification/store.py`:

Extend `_verification` to carry the new columns:

```python
        subject=VerificationSubject(row.subject),
        claim_ref=row.claim_ref,
```

Extend `create_verification`'s signature with
`subject: VerificationSubject = VerificationSubject.IDENTITY` and
`claim_ref: Optional[str] = None`, pass `subject=subject.value` and
`claim_ref=claim_ref` into `VerificationRow(...)`, and set the audited level
from the right ladder:

```python
            row = VerificationRow(
                id=str(uuid.uuid4()),
                candidate_id=candidate_id,
                method=method.value,
                # Claim methods have no AssuranceLevel by design; the column is
                # the identity ladder and stays 0 for them.
                assurance_level=int(METHOD_LEVEL.get(method, AssuranceLevel.NONE)),
                subject=subject.value,
                claim_ref=claim_ref,
                status=VerificationStatus.PENDING.value,
                consent_id=consent_id,
                details={},
                requested_at=moment,
            )
```

and add `"subject": subject.value` to that call's audit `details`.

Then append the two read methods:

```python
    def claims_for_candidate(
        self,
        candidate_id: str,
        *,
        at: Optional[datetime] = None,
        concurrent: Optional[ConcurrentEmployment] = None,
    ) -> ClaimEvidence:
        moment = as_utc(at) if at else _utcnow()
        return compute_claim_evidence(
            candidate_id, self.verifications_for_candidate(candidate_id),
            at=moment, concurrent=concurrent,
        )

    def claims_for_org(
        self,
        *,
        org_id: str,
        candidate_id: str,
        at: Optional[datetime] = None,
        concurrent: Optional[ConcurrentEmployment] = None,
    ) -> ClaimEvidence:
        """Query-time DPDP gate, mirroring assurance_for_org exactly: an org
        sees claim evidence only under an active VERIFICATION_READ grant, and
        EVERY attempt -- allowed or denied -- is audited in the same
        transaction.

        S7.2 widens VERIFICATION_READ from "identity assurance" to
        "verification disclosure" generally. That is acceptable only because
        the purpose is days old with zero real grants; see LEDGER.md for the
        dated redefinition. Returns the advisory roll-up only -- never the
        evidence digests, never a document.
        """
        moment = as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            grants = self._ledger._grants_for(
                session, candidate_id, ConsentPurpose.VERIFICATION_READ)
            decision = consent_logic.check_consent(
                grants, org_id=org_id, purpose=ConsentPurpose.VERIFICATION_READ,
                at=moment)
            if not decision.allowed:
                self._ledger._audit(
                    session, actor_type="org", actor_id=org_id,
                    action="claim.query", entity_type="candidate",
                    entity_id=candidate_id, candidate_id=candidate_id,
                    details={"allowed": False, "purpose": "verification_read"},
                )
                session.commit()
                raise ConsentError(decision.reason)

            rows = (
                session.execute(
                    select(VerificationRow)
                    .where(VerificationRow.candidate_id == candidate_id)
                    .order_by(VerificationRow.requested_at, VerificationRow.id)
                ).scalars().all()
            )
            evidence = compute_claim_evidence(
                candidate_id, [_verification(r) for r in rows], at=moment,
                concurrent=concurrent,
            )
            self._ledger._audit(
                session, actor_type="org", actor_id=org_id, action="claim.query",
                entity_type="candidate", entity_id=candidate_id,
                candidate_id=candidate_id,
                details={"allowed": True, "consent_id": decision.grant_id,
                         "strength": int(evidence.strength)},
            )
            session.commit()
            return evidence
```

Add the needed imports: `compute_claim_evidence` from
`app.verification.claims`, and `ClaimEvidence`, `ConcurrentEmployment`,
`VerificationSubject` from `app.verification.schema`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_verification_claim_store.py tests/test_verification_store.py -q`
Expected: PASS (both files — the S7.1 store tests must be untouched).

- [ ] **Step 5: Commit**

```bash
git add app/verification/store.py tests/test_verification_claim_store.py
git commit -m "feat(s72): claim writes + consent-gated org claim read, audited both ways"
```

---

### Task 10: Service — `submit_document`, config knobs, wiring

**Files:**
- Modify: `app/verification/service.py`, `app/core/config.py`, `config.yaml`
- Test: `tests/test_verification_claim_service.py` (create),
  `tests/test_config_verification.py` (extend)

**Interfaces:**
- Consumes: `parse_document`, `assess`, `assess_concurrent_employment`,
  `get_adapter`, `VerificationStore`.
- Produces: `VerificationService.submit_document(candidate_id, doc_type,
  content_b64, *, claim_ref=None, at=None) -> tuple[Verification,
  list[DocumentFinding], ClaimEvidence]`; `claims_for_candidate`;
  `claims_for_org`; `DocumentTooLargeError`. New settings:
  `doc_max_b64_chars` (8_000_000), `doc_max_pages` (20),
  `doc_metadata_skew_days` (1), `moonlight_min_overlap_months` (12).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verification_claim_service.py
"""S7.2 orchestration: parse -> assess -> one audited claim row, and the
document does not survive the call."""

import base64
from datetime import datetime, timezone

import pytest

from app.candidates.models import CandidateRow
from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError, LedgerStore
from app.verification.documents import DocumentParseError
from app.verification.schema import (
    AssuranceLevel, ClaimStrength, DocumentType, VerificationMethod,
    VerificationStatus, VerificationSubject,
)
from app.verification.service import (
    DocumentTooLargeError, VerificationService,
)
from app.verification.store import VerificationStore
from tests.conftest import make_candidate_store

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)

LETTER = b"""ACME TECHNOLOGIES PRIVATE LIMITED
hr@acme.com
This is to certify that A Candidate (Employee ID ACM-1) was employed with Acme
Technologies as a Senior Software Engineer from March 2021 to January 2024.
Head of Human Resources
"""


@pytest.fixture
def svc(settings):
    candidates = make_candidate_store()
    ledger = LedgerStore(candidates._session_factory,
                         default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
                         settings=settings)
    store = VerificationStore(candidates._session_factory, ledger=ledger, settings=settings)
    service = VerificationService(store, candidates, ledger, settings=settings)
    with candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash="e" * 64)
        s.add(row)
        s.commit()
        cid = row.id
    return service, ledger, cid


def _b64(data=LETTER):
    return base64.b64encode(data).decode("ascii")


def test_submitting_a_letter_writes_one_claim_verification(svc):
    service, _, cid = svc
    v, findings, evidence = service.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER, _b64(), at=NOW)
    assert v.subject is VerificationSubject.EMPLOYMENT_CLAIM
    assert v.method is VerificationMethod.EXPERIENCE_LETTER
    assert v.status is VerificationStatus.VERIFIED
    assert evidence.strength is ClaimStrength.DOCUMENTED
    assert isinstance(findings, list)


def test_the_evidence_digest_is_stored_and_the_document_is_not(svc):
    service, _, cid = svc
    v, _, _ = service.submit_document(cid, DocumentType.EXPERIENCE_LETTER, _b64(), at=NOW)
    assert v.evidence_digest and len(v.evidence_digest) == 64
    stored = str(service._store.get_verification(v.id).model_dump())
    assert "ACME TECHNOLOGIES" not in stored
    assert "hr@acme.com" not in stored


def test_a_claim_submission_never_lifts_identity_assurance(svc):
    service, _, cid = svc
    service.submit_document(cid, DocumentType.EXPERIENCE_LETTER, _b64(), at=NOW)
    assert service.assurance_for_candidate(cid, at=NOW).level is AssuranceLevel.NONE


def test_a_document_with_hard_findings_fails_but_does_not_lower_anything(svc):
    service, _, cid = svc
    service.submit_document(cid, DocumentType.EXPERIENCE_LETTER, _b64(), at=NOW)
    v, _, evidence = service.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER,
        _b64(b"Employed with Globex Corp as an Engineer. Head of Human Resources."),
        at=NOW)
    assert v.status is VerificationStatus.FAILED
    assert evidence.strength is ClaimStrength.DOCUMENTED   # the good one still holds


def test_an_oversize_body_is_refused_before_it_is_decoded(svc, settings, monkeypatch):
    service, _, cid = svc
    monkeypatch.setattr(settings, "doc_max_b64_chars", 32)
    with pytest.raises(DocumentTooLargeError):
        service.submit_document(cid, DocumentType.EXPERIENCE_LETTER, _b64(), at=NOW)


def test_an_unparseable_body_raises_a_parse_error(svc):
    service, _, cid = svc
    with pytest.raises(DocumentParseError):
        service.submit_document(cid, DocumentType.EXPERIENCE_LETTER, "!!!", at=NOW)


def test_an_unknown_candidate_is_a_lookup_error(svc):
    service, _, _ = svc
    with pytest.raises(LookupError):
        service.submit_document("nope", DocumentType.EXPERIENCE_LETTER, _b64(), at=NOW)


def test_epfo_stays_inert_even_with_an_identity_verify_grant(svc):
    """Same shape as the government_id test. Lawful, but no vendor exists."""
    service, ledger, cid = svc
    ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.IDENTITY_VERIFY,
                         org_id=None)
    with pytest.raises(NotImplementedError):
        service.start(cid, VerificationMethod.EPFO_EMPLOYMENT, at=NOW)
    assert service.claims_for_candidate(cid, at=NOW).strength is ClaimStrength.NONE


def test_the_claim_roll_up_carries_the_concurrent_advisory(svc):
    service, _, cid = svc
    evidence = service.claims_for_candidate(cid, at=NOW)
    assert evidence.concurrent_employment is None   # no resume on file in this fixture
```

Append to `tests/test_config_verification.py`:

```python
def test_s72_document_knobs_have_conservative_defaults(settings):
    assert settings.doc_max_b64_chars == 8_000_000
    assert settings.doc_max_pages == 20
    assert settings.doc_metadata_skew_days == 1
    # Deliberately higher than xf_overlap_months_min (3): a short overlap is a
    # notice period, not a second job.
    assert settings.moonlight_min_overlap_months == 12
    assert settings.moonlight_min_overlap_months > settings.xf_overlap_months_min
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_verification_claim_service.py tests/test_config_verification.py -q`
Expected: FAIL — `ImportError: cannot import name 'DocumentTooLargeError'`.

- [ ] **Step 3: Write minimal implementation**

In `app/core/config.py`, below the S7.1 verification block:

```python
    # --- Document forensics (PI-7, S7.2) --------------------------------------
    # Deterministic and offline. The document itself is never stored; these
    # bound what will be parsed before anything is decoded.
    doc_max_b64_chars: int = Field(default=8_000_000, ge=1024)   # ~6MB decoded
    doc_max_pages: int = Field(default=20, ge=1)
    doc_metadata_skew_days: int = Field(default=1, ge=0)
    # Higher than xf_overlap_months_min on purpose: a three-month overlap is a
    # notice period, not a second job.
    moonlight_min_overlap_months: int = Field(default=12, ge=1)
```

Mirror the same five lines into `config.yaml` under a `# S7.2` comment.

In `app/verification/service.py`, add the exception and the method:

```python
class DocumentTooLargeError(Exception):
    """The submitted body exceeds `doc_max_b64_chars`. Raised BEFORE decoding,
    so an oversize payload is never expanded in memory."""
```

```python
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
        """
        moment = consent_logic.as_utc(at) if at else _utcnow()
        summary = self._candidates.get_candidate(candidate_id)
        if summary is None:
            raise LookupError(f"unknown candidate: {candidate_id}")
        if len(content_b64 or "") > self._settings.doc_max_b64_chars:
            raise DocumentTooLargeError(
                f"document exceeds doc_max_b64_chars={self._settings.doc_max_b64_chars}")

        method = (VerificationMethod.PAYSLIP if doc_type is DocumentType.PAYSLIP
                  else VerificationMethod.EXPERIENCE_LETTER)
        adapter = get_adapter(method)
        if not adapter.self_service:
            raise MethodNotPermittedError(
                f"{method.value} is recorded by an operator, not requested")
        if not adapter.implemented:
            raise NotImplementedError(f"{method.value} verification is not implemented")

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
            candidate_id, at=moment, concurrent=self._concurrent(candidate_id, moment))

    def claims_for_org(
        self, *, org_id: str, candidate_id: str, at: Optional[datetime] = None
    ) -> ClaimEvidence:
        moment = consent_logic.as_utc(at) if at else _utcnow()
        return self._store.claims_for_org(
            org_id=org_id, candidate_id=candidate_id, at=moment,
            concurrent=self._concurrent(candidate_id, moment))

    def _concurrent(self, candidate_id: str, moment: datetime):
        """Derived read-time from the candidate's own resume intervals."""
        return assess_concurrent_employment(
            self._candidates.latest_profile(candidate_id),
            today=moment.date(),
            min_months=self._settings.moonlight_min_overlap_months,
        )
```

Imports to add to `service.py`: `assess`, `parse_document` from
`app.verification.documents`; `assess_concurrent_employment` from
`app.verification.moonlighting`; `ClaimEvidence`, `DocumentFinding`,
`DocumentType`, `VerificationSubject` from `app.verification.schema`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_verification_claim_service.py tests/test_config_verification.py tests/test_verification_service.py -q`
Expected: PASS (all three files).

- [ ] **Step 5: Commit**

```bash
git add app/verification/service.py app/core/config.py config.yaml tests/test_verification_claim_service.py tests/test_config_verification.py
git commit -m "feat(s72): submit_document orchestration + doc_/moonlight_ config knobs"
```

---

### Task 11: API — candidate submit, claims on both planes, `MyData.claims`

**Files:**
- Modify: `app/api/routes.py`, `app/portal/schema.py`, `app/portal/service.py`
- Test: `tests/test_verification_claim_api.py` (create),
  `tests/test_portal_identity.py` (extend)

**Interfaces:**
- Consumes: `services.verification.submit_document` / `claims_for_candidate` /
  `claims_for_org`.
- Produces: `POST /portal/documents`; `claims` on `GET /portal/verifications`;
  `GET /verification/candidates/{id}/claims`; `MyData.claims`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verification_claim_api.py
"""S7.2 routes. Cross-candidate isolation stays structural: the subject is
resolved from the key, never from the body."""

import base64

import pytest
from fastapi.testclient import TestClient

from app.candidates.hashing import contact_hash, normalize_email
from app.candidates.models import CandidateRow
from app.main import create_app
from tests.conftest import make_services

EMAIL = "dev@example.com"
LETTER = (b"ACME TECHNOLOGIES PRIVATE LIMITED\nhr@acme.com\n"
          b"This is to certify that A Candidate (Employee ID ACM-1) was employed "
          b"with Acme Technologies as a Senior Software Engineer from March 2021 "
          b"to January 2024.\nHead of Human Resources\n")


def _candidate(services, email=EMAIL, name="A Candidate"):
    store = services.candidates
    with store._session_factory() as s:
        row = CandidateRow(full_name=name, email_hash=contact_hash(
            normalize_email(email), services.settings.contact_hash_salt))
        s.add(row)
        s.commit()
        cid = row.id
    return cid, store.issue_access_key(cid)


@pytest.fixture
def client(settings):
    services = make_services(settings)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c, services


def _b64(data=LETTER):
    return base64.b64encode(data).decode("ascii")


def test_documents_require_a_candidate_key(client):
    c, _ = client
    assert c.post("/portal/documents", json={"doc_type": "experience_letter",
                                             "content_b64": _b64()}).status_code == 401


def test_submitting_a_letter_returns_the_verification_findings_and_claims(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post("/portal/documents",
               json={"doc_type": "experience_letter", "content_b64": _b64()},
               headers={"X-Candidate-Key": key})
    assert r.status_code == 200
    body = r.json()
    assert body["verification"]["subject"] == "employment_claim"
    assert body["claims"]["strength"] == 2          # DOCUMENTED
    assert isinstance(body["findings"], list)


def test_the_response_never_echoes_the_document(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post("/portal/documents",
               json={"doc_type": "experience_letter", "content_b64": _b64()},
               headers={"X-Candidate-Key": key})
    assert "ACME TECHNOLOGIES" not in r.text
    assert "hr@acme.com" not in r.text


def test_a_claim_does_not_lift_the_identity_level_over_http(client):
    c, services = client
    _, key = _candidate(services)
    h = {"X-Candidate-Key": key}
    c.post("/portal/documents", json={"doc_type": "experience_letter",
                                      "content_b64": _b64()}, headers=h)
    listed = c.get("/portal/verifications", headers=h).json()
    assert listed["assurance"]["level"] == 0
    assert listed["claims"]["strength"] == 2


def test_bad_base64_is_a_400(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post("/portal/documents", json={"doc_type": "experience_letter",
                                          "content_b64": "!!!"},
               headers={"X-Candidate-Key": key})
    assert r.status_code == 400


def test_an_unknown_doc_type_is_a_422(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post("/portal/documents", json={"doc_type": "affidavit",
                                          "content_b64": _b64()},
               headers={"X-Candidate-Key": key})
    assert r.status_code == 422


def test_an_oversize_body_is_a_422(client, settings, monkeypatch):
    c, services = client
    monkeypatch.setattr(services.settings, "doc_max_b64_chars", 32)
    _, key = _candidate(services)
    r = c.post("/portal/documents", json={"doc_type": "experience_letter",
                                          "content_b64": _b64()},
               headers={"X-Candidate-Key": key})
    assert r.status_code == 422


def test_epfo_over_http_is_422_even_after_a_self_granted_consent(client):
    c, services = client
    _, key = _candidate(services)
    h = {"X-Candidate-Key": key}
    assert c.post("/portal/consents", json={"purpose": "identity_verify"},
                  headers=h).status_code == 200
    r = c.post("/portal/verifications", json={"method": "epfo_employment"}, headers=h)
    assert r.status_code == 422
    assert c.get("/portal/verifications", headers=h).json()["claims"]["strength"] == 0


def test_one_candidates_document_cannot_appear_in_anothers_claims(client):
    c, services = client
    _, key_a = _candidate(services)
    _, key_b = _candidate(services, email="other@example.com", name="Other")
    c.post("/portal/documents", json={"doc_type": "experience_letter",
                                      "content_b64": _b64()},
           headers={"X-Candidate-Key": key_a})
    other = c.get("/portal/verifications", headers={"X-Candidate-Key": key_b}).json()
    assert other["claims"]["strength"] == 0
    assert other["verifications"] == []


def _org(services):
    """Same helper tests/test_verification_org_api.py uses."""
    org = services.ledger.create_organization("Acme Corp")
    return org.id, services.ledger.issue_api_key(org.id)


def test_the_org_claims_read_is_consent_gated_and_leaks_no_internals(client):
    from app.ledger.schema import ConsentPurpose

    c, services = client
    cid, key = _candidate(services)
    c.post("/portal/documents", json={"doc_type": "experience_letter",
                                      "content_b64": _b64()},
           headers={"X-Candidate-Key": key})
    org_id, org_key = _org(services)
    org_h = {"X-Org-Key": org_key}
    path = f"/verification/candidates/{cid}/claims"

    assert c.get(path, headers=org_h).status_code == 403

    services.ledger.grant_consent(candidate_id=cid,
                                  purpose=ConsentPurpose.VERIFICATION_READ,
                                  org_id=org_id)
    granted = c.get(path, headers=org_h)
    assert granted.status_code == 200
    assert granted.json()["strength"] == 2
    assert "evidence_digest" not in granted.text
    assert "ACME TECHNOLOGIES" not in granted.text


def test_the_org_claims_read_requires_an_org_key(client):
    c, services = client
    cid, _ = _candidate(services)
    assert c.get(f"/verification/candidates/{cid}/claims").status_code == 401


def test_an_unknown_candidate_is_a_404_for_the_org(client):
    from app.ledger.schema import ConsentPurpose

    c, services = client
    _, org_key = _org(services)
    r = c.get("/verification/candidates/nope/claims", headers={"X-Org-Key": org_key})
    assert r.status_code == 404
```

Append to `tests/test_portal_identity.py`:

```python
def test_my_data_carries_the_claim_roll_up(settings):
    import base64
    from app.verification.schema import DocumentType
    services = make_services(settings)          # existing helper in this file
    cid = _candidate(services)                  # existing helper in this file
    services.verification.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER,
        base64.b64encode(b"Employed with Acme from March 2021 to January 2024. "
                         b"Head of Human Resources.").decode("ascii"))
    data = services.portal.my_data(cid)
    assert data.claims is not None
    assert data.identity is not None            # S7.1 unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_verification_claim_api.py tests/test_portal_identity.py -q`
Expected: FAIL — 404 on `/portal/documents` (route does not exist).

- [ ] **Step 3: Write minimal implementation**

In `app/portal/schema.py`, add to `MyData` beside `identity`:

```python
    claims: Optional[ClaimEvidence] = None  # S7.2 advisory claim evidence
```

and import `ClaimEvidence` from `app.verification.schema`.

In `app/portal/service.py`, beside the `identity` block in `my_data`:

```python
        claims = (
            self._verification.claims_for_candidate(candidate_id)
            if self._verification is not None
            else None
        )
```

and pass `claims=claims` into the `MyData(...)` construction.

In `app/api/routes.py`, import `DocumentType` and the new exceptions, and add
the routes next to the S7.1 verification block:

```python
class SubmitDocumentRequest(BaseModel):
    """`content_b64` is a base64 PDF or plain-text body. It is parsed in memory
    and discarded -- only a sha256 digest and finding CODES are stored."""

    doc_type: DocumentType
    content_b64: str
    claim_ref: str | None = None


@candidate_router.post("/portal/documents")
async def submit_document(
    req: SubmitDocumentRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> dict:
    services = _services(request)
    try:
        verification, findings, claims = services.verification.submit_document(
            candidate_id, req.doc_type, req.content_b64, claim_ref=req.claim_ref)
    except DocumentTooLargeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DocumentParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MethodNotPermittedError as exc:
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


@org_router.get("/verification/candidates/{candidate_id}/claims")
async def org_candidate_claims(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> dict:
    """Consent-gated employment-claim evidence. Every attempt — allowed or
    denied — is audited by the store. Returns the advisory roll-up only: never
    an evidence digest, never a document."""
    try:
        claims = _services(request).verification.claims_for_org(
            org_id=org_id, candidate_id=candidate_id)
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return claims.model_dump(mode="json")
```

and extend the existing `list_verifications` handler's return with
`"claims": _services(request).verification.claims_for_candidate(candidate_id)
.model_dump(mode="json")`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_verification_claim_api.py tests/test_portal_identity.py tests/test_verification_api.py tests/test_verification_org_api.py -q`
Expected: PASS (all four files).

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py app/portal/schema.py app/portal/service.py tests/test_verification_claim_api.py tests/test_portal_identity.py
git commit -m "feat(s72): candidate document submit + claims on portal and org planes"
```

---

### Task 12: Erasure, smoke, docs, roadmap

**Files:**
- Test: `tests/test_verification_erasure.py` (extend)
- Create: `scripts/smoke_s72.py`
- Modify: `VERIFICATION.md`, `LEDGER.md`, `PORTAL.md`, `README.md`,
  `docs/ROADMAP.md`

- [ ] **Step 1: Write the failing erasure test**

Append to `tests/test_verification_erasure.py`:

```python
def test_dpdp_erasure_sweeps_claim_rows_too(settings):
    import base64
    from app.verification.schema import DocumentType
    services = make_services(settings)          # existing helper in this file
    cid = _candidate(services)                  # existing helper in this file
    services.verification.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER,
        base64.b64encode(b"Employed with Acme from March 2021 to January 2024. "
                         b"Head of Human Resources.").decode("ascii"))
    assert services.verification.claims_for_candidate(cid).strength != 0

    services.candidates.delete_candidate(cid)

    from app.verification.models import VerificationRow
    with services.candidates._session_factory() as s:
        assert s.query(VerificationRow).filter_by(candidate_id=cid).count() == 0
```

- [ ] **Step 2: Run it to verify it fails, then passes**

Run: `python -m pytest tests/test_verification_erasure.py -q`
Expected: PASS immediately — the CASCADE from `0013` already covers claim rows,
because they are `verifications` rows. **If it fails, stop and investigate: the
CASCADE is the erasure guarantee and nothing else in S7.2 substitutes for it.**

- [ ] **Step 3: Write the smoke script**

Create `scripts/smoke_s72.py`, modelled on `scripts/smoke_s71.py` (copy its
uvicorn/scratch-DB/`_wait_healthy` scaffolding verbatim, change `PORT = 8072`
and the DB filename). The checks, in order:

1. `claims_start_empty` — new candidate, `GET /portal/verifications` →
   `claims.strength == 0`.
2. `clean_letter_documented` — `POST /portal/documents` with a clean experience
   letter matching the resume → 200, `claims.strength == 2`.
3. `identity_level_still_zero` — `assurance.level == 0`. **This is the check the
   sprint exists to protect.**
4. `mismatched_letter_fails` — a letter naming an employer absent from the
   resume → `verification.status == "failed"`, strength still 2.
5. `payslip_arithmetic_hard_finding` — a payslip whose gross − deductions ≠ net
   → `failed`, a `payslip_arithmetic_mismatch` finding present.
6. `no_document_content_in_any_response` — assert the employer email and the
   employee-id string appear nowhere in any response body.
7. `epfo_422_even_with_self_granted_consent` — `POST /portal/consents`
   `identity_verify`, then `POST /portal/verifications`
   `{"method": "epfo_employment"}` → 422, `claims.strength` unchanged.
8. `concurrent_employment_surfaced` — create a second candidate whose resume has
   two overlapping primary roles ≥ 12 months → `claims.concurrent_employment`
   present with a period label.
9. `org_claims_403_without_consent` → 403.
10. `org_claims_200_with_consent` — grant `verification_read` → 200,
    `strength == 2`.
11. `org_sees_no_evidence_internals` — `"evidence_digest" not in body`.
12. `org_claims_403_after_revoke` → 403.
13. `org_claims_404_after_erase` — `DELETE /portal/me`, then 404.

Run: `python scripts/smoke_s72.py`
Expected: every check `[OK]`, exit 0.

- [ ] **Step 4: Write the docs**

- `VERIFICATION.md`: a new section covering the two subjects, the claim ladder,
  the forensic checks and their severities, the "no content in `details`" rule,
  and the EPFO answer from spec §3 with its "vendor, not legality" conclusion.
- `LEDGER.md`: the **dated** `VERIFICATION_READ` redefinition — "as of
  2026-07-31 this purpose covers verification disclosure generally (identity
  assurance *and* employment-claim evidence); widened while it held zero real
  grants; any further widening requires a new purpose."
- `PORTAL.md`: `POST /portal/documents` contract (200/400/403/404/422), the
  `claims` key on `GET /portal/verifications`, and `MyData.claims`.
- `README.md`: extend the S7.1 verification row of the endpoint table.
- `docs/ROADMAP.md`: flip S7.2 to `[x]` on the status board, rewrite "Current
  state" and "Next action" (→ S7.3), and add a session-log entry.

- [ ] **Step 5: Full verification, then commit**

```bash
python -m pytest -q                 # expect ~927 passed
python -m pyflakes app/verification/*.py app/api/routes.py app/portal/*.py scripts/smoke_s72.py tests/test_verification_*.py
python scripts/smoke_s72.py         # expect exit 0, all checks OK
git add -A
git commit -m "test(s72): erasure + uvicorn smoke; VERIFICATION/LEDGER/PORTAL docs + ROADMAP"
```

---

## Before merging

Run the **whole-branch review** described in `docs/ROADMAP.md` — read the code,
not the branch's own account of it. S7.1's review found two live escalations
that its docs and tests both asserted were impossible. For this branch, the
questions that matter most:

1. Can any claim row reach `IdentityAssurance`? (Try it, don't reason about it.)
2. Can any stored row be made to hold document text, a salary figure, or a UAN?
3. Is `claim.query` audited on the denied path as well as the allowed one?
4. Does any new adapter reach an outcome without declaring how it got there?
5. Is `VERIFICATION_READ`'s widening actually documented where a reader of
   `LEDGER.md` will find it?
