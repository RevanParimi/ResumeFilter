"""S7.1 adapter seam: every method resolves; government_id is declared but inert."""

import pytest

from app.verification.methods import ADAPTERS, get_adapter
from app.verification.schema import AssuranceLevel, VerificationMethod


def test_every_method_has_an_adapter():
    assert set(ADAPTERS) == set(VerificationMethod)


def test_adapter_levels_agree_with_the_method_level_map():
    from app.verification.schema import METHOD_LEVEL
    for method, adapter in ADAPTERS.items():
        assert adapter.level is METHOD_LEVEL[method]
        assert adapter.method is method


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
