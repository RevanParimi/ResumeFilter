"""Verification schema regressions, grouped by behavior."""

from app.ledger.schema import ConsentPurpose
from app.verification.schema import (
    METHOD_LEVEL,
    AssuranceLevel,
    IdentityAssurance,
    Verification,
    VerificationMethod,
    VerificationStatus,
    METHOD_SUBJECT,
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


def test_only_identity_methods_map_to_an_assurance_level():
    """A claim method has no AssuranceLevel -- that is what keeps a payslip out
    of the identity number."""
    for method, subject in METHOD_SUBJECT.items():
        if subject is VerificationSubject.IDENTITY:
            assert method in METHOD_LEVEL
        else:
            assert method not in METHOD_LEVEL


def test_document_types_are_the_two_shipped():
    assert {d.value for d in DocumentType} == {"experience_letter", "payslip"}
