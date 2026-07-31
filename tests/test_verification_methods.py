"""S7.1 adapter seam: every method resolves; government_id is declared but inert."""

import pytest

from app.verification.methods import ADAPTERS, get_adapter
from app.verification.schema import AssuranceLevel, VerificationMethod


def test_every_method_has_an_adapter():
    assert set(ADAPTERS) == set(VerificationMethod)


def test_adapter_levels_agree_with_the_method_level_map():
    """Identity adapters carry the level their method maps to. S7.2's claim
    adapters are absent from METHOD_LEVEL by design and must pin level to NONE,
    so nothing about them can lift the identity ladder."""
    from app.verification.schema import METHOD_LEVEL
    for method, adapter in ADAPTERS.items():
        assert adapter.method is method
        if method in METHOD_LEVEL:
            assert adapter.level is METHOD_LEVEL[method]
        else:
            assert adapter.level is AssuranceLevel.NONE


def test_first_party_methods_are_not_third_party():
    for method in (
        VerificationMethod.SELF_ATTESTED,
        VerificationMethod.OTP_EMAIL,
        VerificationMethod.OTP_PHONE,
        VerificationMethod.MANUAL_REVIEW,
    ):
        assert get_adapter(method).third_party is False


def test_government_id_is_third_party_so_the_spine_gates_it_on_consent():
    adapter = get_adapter(VerificationMethod.GOVERNMENT_ID)
    assert adapter.third_party is True
    assert adapter.level is AssuranceLevel.GOVERNMENT_ID


def test_government_id_is_declared_but_unimplemented():
    with pytest.raises(NotImplementedError):
        get_adapter(VerificationMethod.GOVERNMENT_ID).start()


def test_government_id_declares_itself_unimplemented_to_the_spine():
    """The spine reads this flag; a raise inside the adapter is not enough,
    because the spine never calls the adapter to perform the work."""
    assert get_adapter(VerificationMethod.GOVERNMENT_ID).implemented is False
    for method in (
        VerificationMethod.SELF_ATTESTED,
        VerificationMethod.OTP_EMAIL,
        VerificationMethod.OTP_PHONE,
        VerificationMethod.MANUAL_REVIEW,
    ):
        assert get_adapter(method).implemented is True


def test_manual_review_is_the_only_method_a_candidate_may_not_initiate():
    """An operator-attested level cannot be self-service, or the candidate
    simply awards it to themselves."""
    not_self_service = {m for m, a in ADAPTERS.items() if not a.self_service}
    assert not_self_service == {VerificationMethod.MANUAL_REVIEW}


def test_only_assertion_or_assessment_completes_instantly():
    """The spine refuses to mark a method verified on request unless the
    adapter says assertion or assessment IS the evidence. S7.2's document
    methods qualify -- forensics have already run by the time the row is
    written -- so this widened; it did not weaken."""
    instant = {m for m, a in ADAPTERS.items() if a.instant}
    assert instant == {
        VerificationMethod.SELF_ATTESTED,
        VerificationMethod.EXPERIENCE_LETTER,
        VerificationMethod.PAYSLIP,
    }


def test_only_otp_methods_are_challenge_based():
    challenge = {m for m, a in ADAPTERS.items() if a.challenge_based}
    assert challenge == {VerificationMethod.OTP_EMAIL, VerificationMethod.OTP_PHONE}


def test_otp_adapters_declare_their_channel_and_contact_hash_field():
    assert get_adapter(VerificationMethod.OTP_EMAIL).channel == "email"
    assert get_adapter(VerificationMethod.OTP_EMAIL).contact_hash_field == "email_hash"
    assert get_adapter(VerificationMethod.OTP_PHONE).channel == "phone"
    assert get_adapter(VerificationMethod.OTP_PHONE).contact_hash_field == "phone_hash"


def test_get_adapter_rejects_an_unknown_method():
    with pytest.raises(KeyError):
        get_adapter("not_a_method")  # type: ignore[arg-type]


# ── S7.2 employment-claim adapters ──────────────────────────────────────────


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


def test_epfo_raises_from_the_adapter_as_a_backstop():
    with pytest.raises(NotImplementedError):
        get_adapter(VerificationMethod.EPFO_EMPLOYMENT).start()


def test_only_document_methods_are_document_based():
    based = {m for m, a in ADAPTERS.items() if a.document_based}
    assert based == {VerificationMethod.EXPERIENCE_LETTER, VerificationMethod.PAYSLIP}
