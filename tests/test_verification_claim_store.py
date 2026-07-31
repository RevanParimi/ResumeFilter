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


def test_a_claim_row_carries_no_assurance_level(bundle):
    """The identity ladder column stays 0 for a claim: there is no METHOD_LEVEL
    entry to read, and inventing one is how a payslip would become an L2."""
    store, _, cid, _ = bundle
    from app.verification.schema import AssuranceLevel
    assert _claim_row(store, cid).assurance_level is AssuranceLevel.NONE


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
                         org_id=org_id, now=NOW)
    ev = store.claims_for_org(org_id=org_id, candidate_id=cid, at=NOW)
    assert ev.strength is ClaimStrength.DOCUMENTED


def test_a_revoked_grant_closes_the_org_read_again(bundle):
    store, ledger, cid, org_id = bundle
    _claim_row(store, cid)
    grant = ledger.grant_consent(candidate_id=cid,
                                 purpose=ConsentPurpose.VERIFICATION_READ, org_id=org_id, now=NOW)
    store.claims_for_org(org_id=org_id, candidate_id=cid, at=NOW)
    ledger.revoke_consent(grant.id, now=NOW)
    with pytest.raises(ConsentError):
        store.claims_for_org(org_id=org_id, candidate_id=cid, at=NOW)


def test_an_identity_verify_grant_does_not_unlock_the_claim_read(bundle):
    """Purposes are not interchangeable: the read gate is VERIFICATION_READ and
    nothing else opens it."""
    store, ledger, cid, org_id = bundle
    _claim_row(store, cid)
    ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.IDENTITY_VERIFY,
                         org_id=org_id, now=NOW)
    with pytest.raises(ConsentError):
        store.claims_for_org(org_id=org_id, candidate_id=cid, at=NOW)


def test_every_org_attempt_is_audited_allowed_or_denied(bundle):
    store, ledger, cid, org_id = bundle
    _claim_row(store, cid)
    with pytest.raises(ConsentError):
        store.claims_for_org(org_id=org_id, candidate_id=cid, at=NOW)
    ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ,
                         org_id=org_id, now=NOW)
    store.claims_for_org(org_id=org_id, candidate_id=cid, at=NOW)

    queries = [e for e in ledger.audit_for_candidate(cid) if e.action == "claim.query"]
    assert [e.details.get("allowed") for e in queries] == [False, True]


def test_the_denied_audit_row_survives_the_refusal(bundle):
    """The refusal raises; the trail of the attempt must still be committed --
    surveillance that fails is still surveillance."""
    store, ledger, cid, org_id = bundle
    with pytest.raises(ConsentError):
        store.claims_for_org(org_id=org_id, candidate_id=cid, at=NOW)
    denied = [e for e in ledger.audit_for_candidate(cid)
              if e.action == "claim.query" and e.details.get("allowed") is False]
    assert len(denied) == 1
    assert denied[0].actor_type == "org" and denied[0].actor_id == org_id


def test_the_org_read_never_returns_evidence_internals(bundle):
    store, ledger, cid, org_id = bundle
    _claim_row(store, cid)
    ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ,
                         org_id=org_id, now=NOW)
    dumped = str(store.claims_for_org(org_id=org_id, candidate_id=cid, at=NOW)
                 .model_dump())
    assert "a" * 64 not in dumped              # the evidence digest
    assert "claim_ref" not in dumped


def test_a_method_subject_mismatch_is_unrepresentable(bundle):
    """REVIEW. The route gate stops a claim method reaching the identity start
    path; this makes the bad row impossible to write at all, from any caller.
    METHOD_SUBJECT is the single source of truth for which ladder a method
    feeds, so the store refuses to contradict it."""
    store, _, cid, _ = bundle
    with pytest.raises(ValueError):
        store.create_verification(
            candidate_id=cid, method=VerificationMethod.EXPERIENCE_LETTER,
            subject=VerificationSubject.IDENTITY, at=NOW)
    with pytest.raises(ValueError):
        store.create_verification(
            candidate_id=cid, method=VerificationMethod.SELF_ATTESTED,
            subject=VerificationSubject.EMPLOYMENT_CLAIM, at=NOW)
    assert store.verifications_for_candidate(cid) == []


def test_an_unknown_candidate_or_org_is_a_lookup_error(bundle):
    store, _, cid, org_id = bundle
    with pytest.raises(LookupError):
        store.claims_for_org(org_id=org_id, candidate_id="nope", at=NOW)
    with pytest.raises(LookupError):
        store.claims_for_org(org_id="nope", candidate_id=cid, at=NOW)
