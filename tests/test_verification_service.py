"""S7.1 orchestration: destination binding, the third-party consent gate, isolation."""

import random
from datetime import datetime, timezone

import pytest

from app.candidates.hashing import contact_hash, normalize_email
from app.candidates.models import CandidateRow
from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError, LedgerStore
from app.verification.schema import (
    AssuranceLevel, VerificationMethod, VerificationStatus,
)
from app.verification.service import (
    DestinationError, MethodNotPermittedError, VerificationService,
)
from app.verification.store import VerificationStore
from tests.conftest import make_candidate_store

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
EMAIL = "dev@example.com"


@pytest.fixture
def svc(settings):
    candidates = make_candidate_store()
    ledger = LedgerStore(
        candidates._session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        settings=settings,
    )
    store = VerificationStore(candidates._session_factory, ledger=ledger, settings=settings)
    service = VerificationService(store, candidates, ledger, settings=settings)
    with candidates._session_factory() as s:
        row = CandidateRow(
            full_name="A Candidate",
            email_hash=contact_hash(normalize_email(EMAIL), settings.contact_hash_salt),
        )
        s.add(row)
        s.commit()
        cid = row.id
    return service, ledger, cid


class _FakeThirdPartyAdapter:
    """Stands in for a real KYC vendor so the SPINE's consent gate is testable
    without shipping an external integration."""

    method = VerificationMethod.SELF_ATTESTED  # reuse a routable method value
    level = AssuranceLevel.GOVERNMENT_ID
    third_party = True
    challenge_based = False
    channel = None
    contact_hash_field = None
    # A real vendor adapter declares these too: it is candidate-initiated, it
    # is built, and it resolves in one step once the vendor answers.
    self_service = True
    implemented = True
    instant = True


def test_self_attest_completes_immediately(svc):
    service, _, cid = svc
    v, code = service.start(cid, VerificationMethod.SELF_ATTESTED, at=NOW)
    assert code is None
    assert v.status is VerificationStatus.VERIFIED
    assert v.assurance_level is AssuranceLevel.SELF_ATTESTED


def test_otp_start_requires_a_destination(svc):
    service, _, cid = svc
    with pytest.raises(DestinationError):
        service.start(cid, VerificationMethod.OTP_EMAIL, at=NOW)


def test_otp_start_rejects_a_destination_that_is_not_the_one_on_file(svc):
    service, _, cid = svc
    with pytest.raises(DestinationError):
        service.start(
            cid, VerificationMethod.OTP_EMAIL, destination="someone.else@example.com",
            rng=random.Random(3), at=NOW,
        )


def test_otp_start_accepts_the_contact_on_file_and_returns_a_code(svc):
    service, _, cid = svc
    v, code = service.start(
        cid, VerificationMethod.OTP_EMAIL, destination=EMAIL, rng=random.Random(3), at=NOW
    )
    assert v.status is VerificationStatus.PENDING
    assert code is not None and code.isdigit()


def test_destination_matching_is_normalized_before_hashing(svc):
    # "  DEV@Example.COM " and "dev@example.com" are the same contact.
    service, _, cid = svc
    v, code = service.start(
        cid, VerificationMethod.OTP_EMAIL, destination="  DEV@Example.COM ",
        rng=random.Random(3), at=NOW,
    )
    assert code is not None


def test_a_candidate_with_no_contact_hash_of_that_type_is_refused(svc):
    service, _, _ = svc
    candidates = service._candidates
    with candidates._session_factory() as s:
        row = CandidateRow(full_name="No Phone", email_hash="e" * 64)
        s.add(row)
        s.commit()
        other = row.id
    with pytest.raises(DestinationError):
        service.start(
            other, VerificationMethod.OTP_PHONE, destination="+919876543210",
            rng=random.Random(3), at=NOW,
        )


def test_confirm_verifies_and_lifts_the_assurance_level(svc):
    service, _, cid = svc
    v, code = service.start(
        cid, VerificationMethod.OTP_EMAIL, destination=EMAIL, rng=random.Random(3), at=NOW
    )
    done = service.confirm(cid, v.id, code, at=NOW)
    assert done.status is VerificationStatus.VERIFIED
    _, assurance = service.list_for_candidate(cid, at=NOW)
    assert assurance.level is AssuranceLevel.CONTACT_CONTROL


def test_a_third_party_method_without_identity_verify_consent_is_refused(svc, monkeypatch):
    """The gate lives in the SPINE, keyed off adapter.third_party."""
    service, _, cid = svc
    from app.verification import methods as methods_mod

    monkeypatch.setitem(
        methods_mod.ADAPTERS, VerificationMethod.SELF_ATTESTED, _FakeThirdPartyAdapter()
    )
    with pytest.raises(ConsentError):
        service.start(cid, VerificationMethod.SELF_ATTESTED, at=NOW)


def test_a_third_party_method_with_consent_proceeds_and_stamps_the_grant(svc, monkeypatch):
    service, ledger, cid = svc
    from app.verification import methods as methods_mod

    monkeypatch.setitem(
        methods_mod.ADAPTERS, VerificationMethod.SELF_ATTESTED, _FakeThirdPartyAdapter()
    )
    grant = ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.IDENTITY_VERIFY, org_id=None, now=NOW)
    v, _ = service.start(cid, VerificationMethod.SELF_ATTESTED, at=NOW)
    assert v.consent_id == grant.id


def test_confirm_refuses_a_verification_owned_by_another_candidate(svc):
    service, _, cid = svc
    candidates = service._candidates
    with candidates._session_factory() as s:
        row = CandidateRow(full_name="Other", email_hash="f" * 64)
        s.add(row)
        s.commit()
        other = row.id
    v, code = service.start(
        cid, VerificationMethod.OTP_EMAIL, destination=EMAIL, rng=random.Random(3), at=NOW
    )
    # Indistinguishable from "does not exist" -- no probing for someone else's ids.
    with pytest.raises(LookupError):
        service.confirm(other, v.id, code, at=NOW)


def test_record_manual_review_records_a_reviewed_outcome(svc):
    service, _, cid = svc
    v = service.record_manual_review(cid, outcome=VerificationStatus.VERIFIED, at=NOW)
    assert v.assurance_level is AssuranceLevel.REVIEWED
    assert v.status is VerificationStatus.VERIFIED
    _, assurance = service.list_for_candidate(cid, at=NOW)
    assert assurance.level is AssuranceLevel.REVIEWED


def test_an_operator_review_is_not_logged_as_the_candidates_own_action(svc):
    """The access log is a DPDP transparency surface: it must not tell the
    candidate they started something an operator started."""
    service, ledger, cid = svc
    service.record_manual_review(cid, outcome=VerificationStatus.VERIFIED, at=NOW)
    starts = [
        e for e in ledger.audit_for_candidate(cid) if e.action == "verification.start"
    ]
    assert starts and all(e.actor_type == "system" for e in starts)
    assert all(e.actor_id is None for e in starts)


def test_a_candidate_cannot_start_a_manual_review_for_themselves(svc):
    """`start` is the candidate-initiated entry point. manual_review means an
    OPERATOR checked something; letting a candidate call it hands them L3."""
    service, _, cid = svc
    with pytest.raises(MethodNotPermittedError):
        service.start(cid, VerificationMethod.MANUAL_REVIEW, at=NOW)
    _, assurance = service.list_for_candidate(cid, at=NOW)
    assert assurance.level is AssuranceLevel.NONE


def test_government_id_stays_inert_in_the_spine_even_with_consent(svc):
    """Consent is necessary, never sufficient: there is no adapter behind
    government_id, so the spine must refuse rather than record an outcome."""
    service, ledger, cid = svc
    ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.IDENTITY_VERIFY, org_id=None, now=NOW)
    with pytest.raises(NotImplementedError):
        service.start(cid, VerificationMethod.GOVERNMENT_ID, at=NOW)
    _, assurance = service.list_for_candidate(cid, at=NOW)
    assert assurance.level is AssuranceLevel.NONE


def test_start_rejects_an_unknown_candidate(svc):
    service, _, _ = svc
    with pytest.raises(LookupError):
        service.start("nope", VerificationMethod.SELF_ATTESTED, at=NOW)


def test_services_container_exposes_verification(settings):
    from tests.conftest import make_services
    services = make_services(settings)
    assert services.verification is not None
    assert hasattr(services.verification, "start")
