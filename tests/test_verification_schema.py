"""Verification schema regressions, grouped by behavior."""

import pytest
from app.ledger.schema import ConsentPurpose
from app.verification.schema import (
    METHOD_LEVEL,
    AssuranceLevel,
    IdentityAssurance,
    Verification,
    VerificationMethod,
    VerificationStatus,
    METHOD_CLAIM_STRENGTH,
    METHOD_SUBJECT,
    ClaimEvidence,
    ClaimStrength,
    ConcurrentEmployment,
    DocumentFinding,
    DocumentType,
    VerificationSubject,
)


# Verification schema

def test_assurance_levels_are_ordered_so_highest_held_is_a_max():
    # IntEnum: ordering is semantic here -- "highest level held" must be a max().
    assert AssuranceLevel.NONE < AssuranceLevel.SELF_ATTESTED
    assert AssuranceLevel.SELF_ATTESTED < AssuranceLevel.CONTACT_CONTROL
    assert AssuranceLevel.CONTACT_CONTROL < AssuranceLevel.REVIEWED
    assert AssuranceLevel.REVIEWED < AssuranceLevel.GOVERNMENT_ID
    assert max([AssuranceLevel.SELF_ATTESTED, AssuranceLevel.REVIEWED]) is AssuranceLevel.REVIEWED


def test_every_method_maps_to_a_level():
    """Every IDENTITY method, that is. S7.2 added employment-claim methods that
    deliberately hold no AssuranceLevel -- their absence from METHOD_LEVEL is
    what keeps a payslip out of the identity number. Derived from METHOD_SUBJECT
    rather than hard-coded, so a new identity method still has to declare one."""
    from app.verification.schema import METHOD_SUBJECT, VerificationSubject

    identity = {
        m for m, s in METHOD_SUBJECT.items() if s is VerificationSubject.IDENTITY
    }
    assert set(METHOD_LEVEL) == identity
    assert METHOD_LEVEL[VerificationMethod.SELF_ATTESTED] is AssuranceLevel.SELF_ATTESTED
    assert METHOD_LEVEL[VerificationMethod.OTP_EMAIL] is AssuranceLevel.CONTACT_CONTROL
    assert METHOD_LEVEL[VerificationMethod.OTP_PHONE] is AssuranceLevel.CONTACT_CONTROL
    assert METHOD_LEVEL[VerificationMethod.MANUAL_REVIEW] is AssuranceLevel.REVIEWED
    assert METHOD_LEVEL[VerificationMethod.GOVERNMENT_ID] is AssuranceLevel.GOVERNMENT_ID


def test_verification_defaults_carry_no_artifact_fields():
    # The DPDP posture is structural: the ONLY evidence field is a digest.
    fields = set(Verification.model_fields)
    assert "evidence_digest" in fields
    for banned in ("document", "image", "raw", "artifact", "biometric", "file"):
        assert banned not in fields


def test_identity_assurance_is_advisory_and_defaults_to_none_level():
    a = IdentityAssurance(candidate_id="c1")
    assert a.advisory is True
    assert a.level is AssuranceLevel.NONE
    assert a.methods == [] and a.expired_methods == []


def test_verification_status_vocabulary_is_closed():
    assert {s.value for s in VerificationStatus} == {"pending", "verified", "failed", "expired"}


def test_two_new_consent_purposes_exist_without_disturbing_the_old_ones():
    assert ConsentPurpose.IDENTITY_VERIFY.value == "identity_verify"
    assert ConsentPurpose.VERIFICATION_READ.value == "verification_read"
    # S3.1 purposes must keep their exact wire values -- stored grants reference them.
    assert ConsentPurpose.LEDGER_WRITE.value == "ledger_write"
    assert ConsentPurpose.LEDGER_READ.value == "ledger_read"


# Verification claim schema

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
