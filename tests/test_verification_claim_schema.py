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
