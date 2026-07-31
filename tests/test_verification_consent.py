"""S7.1 org-plane disclosure: gated on VERIFICATION_READ, audited either way."""

from datetime import datetime, timezone

import pytest

from app.candidates.models import CandidateRow
from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError, LedgerStore
from app.verification.schema import (
    AssuranceLevel, VerificationMethod, VerificationStatus,
)
from app.verification.store import VerificationStore
from tests.conftest import make_candidate_store

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def bundle(settings):
    candidates = make_candidate_store()
    ledger = LedgerStore(
        candidates._session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        settings=settings,
    )
    store = VerificationStore(candidates._session_factory, ledger=ledger, settings=settings)
    with candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash="e" * 64)
        s.add(row)
        s.commit()
        cid = row.id
    org = ledger.create_organization("Acme Corp")
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.SELF_ATTESTED, at=NOW
    )
    store.complete_verification(v.id, status=VerificationStatus.VERIFIED, at=NOW)
    return candidates, ledger, store, cid, org.id


def test_without_a_grant_the_read_is_refused(bundle):
    _, _, store, cid, org_id = bundle
    with pytest.raises(ConsentError):
        store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)


def test_a_ledger_read_grant_does_not_unlock_verification(bundle):
    # The whole point of a separate purpose: an existing grant must not silently
    # widen to cover identity assurance.
    _, ledger, store, cid, org_id = bundle
    ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ, org_id=org_id
    )
    with pytest.raises(ConsentError):
        store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)


def test_with_a_verification_read_grant_the_assurance_is_disclosed(bundle):
    _, ledger, store, cid, org_id = bundle
    ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=org_id
    )
    a = store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)
    assert a.level is AssuranceLevel.SELF_ATTESTED
    assert a.advisory is True


def test_revocation_closes_the_disclosure_again(bundle):
    _, ledger, store, cid, org_id = bundle
    grant = ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=org_id
    )
    store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)
    ledger.revoke_consent(grant.id)
    with pytest.raises(ConsentError):
        store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)


def test_both_allowed_and_denied_attempts_are_audited(bundle):
    _, ledger, store, cid, org_id = bundle
    with pytest.raises(ConsentError):
        store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)
    ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=org_id
    )
    store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)

    queries = [e for e in ledger.audit_for_candidate(cid) if e.action == "verification.query"]
    assert len(queries) == 2
    assert [q.details.get("allowed") for q in queries] == [False, True]
    assert all(q.actor_type == "org" and q.actor_id == org_id for q in queries)


def test_unknown_org_and_unknown_candidate_raise_lookup_error(bundle):
    _, _, store, cid, org_id = bundle
    with pytest.raises(LookupError):
        store.assurance_for_org(org_id="nope", candidate_id=cid, at=NOW)
    with pytest.raises(LookupError):
        store.assurance_for_org(org_id=org_id, candidate_id="nope", at=NOW)


def test_a_wildcard_grant_covers_any_org(bundle):
    _, ledger, store, cid, org_id = bundle
    ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=None
    )
    assert store.assurance_for_org(
        org_id=org_id, candidate_id=cid, at=NOW
    ).level is AssuranceLevel.SELF_ATTESTED
