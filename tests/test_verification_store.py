"""S7.1 store: outcomes persist, challenges are consumed, every write is audited."""

import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.candidates.models import CandidateRow
from app.ledger.store import LedgerStore
from app.verification.models import VerificationChallengeRow
from app.verification.schema import (
    AssuranceLevel, VerificationMethod, VerificationStatus,
)
from app.verification.store import ChallengeError, VerificationStore
from tests.conftest import make_candidate_store

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store_bundle(settings):
    candidates = make_candidate_store()
    ledger = LedgerStore(
        candidates._session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        settings=settings,
    )
    store = VerificationStore(candidates._session_factory, ledger=ledger, settings=settings)
    return candidates, ledger, store


def _candidate(candidates, email_hash="e" * 64):
    with candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash=email_hash)
        s.add(row)
        s.commit()
        return row.id


def test_create_verification_persists_and_stamps_the_level(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    assert v.candidate_id == cid
    assert v.status is VerificationStatus.PENDING
    assert v.assurance_level is AssuranceLevel.CONTACT_CONTROL
    assert store.get_verification(v.id).id == v.id


def test_create_verification_rejects_an_unknown_candidate(store_bundle):
    _, _, store = store_bundle
    with pytest.raises(LookupError):
        store.create_verification(
            candidate_id="nope", method=VerificationMethod.SELF_ATTESTED, at=NOW
        )


def test_complete_sets_status_completed_at_and_an_expiry_from_config(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.SELF_ATTESTED, at=NOW
    )
    done = store.complete_verification(v.id, status=VerificationStatus.VERIFIED, at=NOW)
    assert done.status is VerificationStatus.VERIFIED
    assert done.completed_at is not None
    assert done.expires_at is not None  # verif_outcome_ttl_days from NOW


def test_every_mutation_writes_an_audit_row(store_bundle):
    candidates, ledger, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.SELF_ATTESTED, at=NOW
    )
    store.complete_verification(v.id, status=VerificationStatus.VERIFIED, at=NOW)
    actions = [e.action for e in ledger.audit_for_candidate(cid)]
    assert "verification.start" in actions
    assert "verification.complete" in actions


def test_confirm_with_the_right_code_verifies_and_deletes_the_challenge(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    code = store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    done = store.confirm_challenge(v.id, code, at=NOW)
    assert done.status is VerificationStatus.VERIFIED
    with store._session_factory() as s:  # consumed challenges are DELETED
        assert s.execute(select(VerificationChallengeRow)).scalars().all() == []


def test_a_wrong_code_raises_increments_attempts_and_leaves_it_pending(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    code = store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    wrong = "1" * len(code) if code != "1" * len(code) else "2" * len(code)
    with pytest.raises(ChallengeError):
        store.confirm_challenge(v.id, wrong, at=NOW)
    assert store.get_verification(v.id).status is VerificationStatus.PENDING
    with store._session_factory() as s:
        ch = s.execute(select(VerificationChallengeRow)).scalars().one()
        assert ch.attempts == 1


def test_exhausting_attempts_fails_the_verification(store_bundle, settings):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    code = store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    wrong = "1" * len(code) if code != "1" * len(code) else "2" * len(code)
    for _ in range(settings.verif_otp_max_attempts):
        with pytest.raises(ChallengeError):
            store.confirm_challenge(v.id, wrong, at=NOW)
    assert store.get_verification(v.id).status is VerificationStatus.FAILED


def test_an_expired_challenge_is_refused(store_bundle, settings):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    code = store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    later = NOW + timedelta(minutes=settings.verif_otp_ttl_minutes + 1)
    with pytest.raises(ChallengeError):
        store.confirm_challenge(v.id, code, at=later)


def test_a_resend_inside_the_cooldown_is_refused(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    with pytest.raises(ChallengeError):
        store.create_challenge(
            verification_id=v.id, channel="email", destination_hash="e" * 64,
            rng=random.Random(8), at=NOW + timedelta(seconds=5),
        )


def test_a_resend_after_the_cooldown_replaces_the_old_challenge(store_bundle, settings):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    later = NOW + timedelta(seconds=settings.verif_otp_resend_cooldown_seconds + 1)
    code2 = store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(8), at=later,
    )
    with store._session_factory() as s:  # exactly one live challenge, the new one
        rows = s.execute(select(VerificationChallengeRow)).scalars().all()
        assert len(rows) == 1
    assert store.confirm_challenge(v.id, code2, at=later).status is VerificationStatus.VERIFIED


def test_the_cooldown_survives_starting_a_brand_new_verification(store_bundle):
    """Per-verification scoping would be no rate limit at all: the candidate
    plane mints a fresh verification on every start, so a cooldown keyed to one
    row is trivially side-stepped by asking again."""
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    first = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    store.create_challenge(
        verification_id=first.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    second = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    with pytest.raises(ChallengeError):
        store.create_challenge(
            verification_id=second.id, channel="email", destination_hash="e" * 64,
            rng=random.Random(8), at=NOW + timedelta(seconds=5),
        )


def test_one_candidates_cooldown_does_not_block_another(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    other = _candidate(candidates, email_hash="f" * 64)
    mine = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    store.create_challenge(
        verification_id=mine.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    theirs = store.create_verification(
        candidate_id=other, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    assert store.create_challenge(
        verification_id=theirs.id, channel="email", destination_hash="f" * 64,
        rng=random.Random(8), at=NOW + timedelta(seconds=5),
    )


def test_the_raw_code_is_never_persisted(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    code = store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    with store._session_factory() as s:
        ch = s.execute(select(VerificationChallengeRow)).scalars().one()
        assert code not in ch.code_hash
        assert len(ch.code_hash) == 64


def test_assurance_for_candidate_folds_stored_outcomes(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.SELF_ATTESTED, at=NOW
    )
    store.complete_verification(v.id, status=VerificationStatus.VERIFIED, at=NOW)
    a = store.assurance_for_candidate(cid, at=NOW)
    assert a.level is AssuranceLevel.SELF_ATTESTED
    assert a.advisory is True
