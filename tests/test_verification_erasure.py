"""S7.1 DPDP: erasing the candidate sweeps every verification artifact."""

import pytest
from sqlalchemy import select

from app.candidates.models import CandidateRow
from app.ledger.schema import ConsentPurpose
from app.verification.models import VerificationChallengeRow, VerificationRow
from app.verification.schema import VerificationMethod
from tests.conftest import make_services


def _candidate(services):
    with services.candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash="e" * 64)
        s.add(row)
        s.commit()
        return row.id


def test_erasure_removes_verifications_and_challenges(settings):
    services = make_services(settings)
    cid = _candidate(services)
    services.verification.start(cid, VerificationMethod.SELF_ATTESTED)

    assert services.candidates.delete_candidate(cid) is True

    with services.candidates._session_factory() as s:
        assert s.execute(select(VerificationRow)).scalars().all() == []
        assert s.execute(select(VerificationChallengeRow)).scalars().all() == []


def test_after_erasure_the_org_read_404s_rather_than_disclosing(settings):
    services = make_services(settings)
    cid = _candidate(services)
    org = services.ledger.create_organization("Acme Corp")
    services.verification.start(cid, VerificationMethod.SELF_ATTESTED)
    services.ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=org.id
    )
    services.verification.assurance_for_org(org_id=org.id, candidate_id=cid)

    services.candidates.delete_candidate(cid)
    with pytest.raises(LookupError):
        services.verification.assurance_for_org(org_id=org.id, candidate_id=cid)


def test_dpdp_erasure_sweeps_claim_rows_too(settings):
    """S7.2 adds no erasure path: claim rows ARE verifications rows, so the
    0013 candidate CASCADE already covers them. If this ever fails, the CASCADE
    is the erasure guarantee and nothing in S7.2 substitutes for it."""
    import base64

    from app.verification.schema import DocumentType

    services = make_services(settings)
    cid = _candidate(services)
    services.verification.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER,
        base64.b64encode(b"Employed with Acme from March 2021 to January 2024. "
                         b"Head of Human Resources.").decode("ascii"))
    assert services.verification.claims_for_candidate(cid).strength != 0

    services.candidates.delete_candidate(cid)

    with services.candidates._session_factory() as s:
        rows = s.execute(
            select(VerificationRow).where(VerificationRow.candidate_id == cid)
        ).scalars().all()
    assert rows == []


def test_after_erasure_the_org_claim_read_404s_rather_than_disclosing(settings):
    import base64

    from app.verification.schema import DocumentType

    services = make_services(settings)
    cid = _candidate(services)
    org = services.ledger.create_organization("Acme Corp")
    services.verification.submit_document(
        cid, DocumentType.EXPERIENCE_LETTER,
        base64.b64encode(b"Employed with Acme from March 2021 to January 2024. "
                         b"Head of Human Resources.").decode("ascii"))
    services.ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=org.id
    )
    services.verification.claims_for_org(org_id=org.id, candidate_id=cid)

    services.candidates.delete_candidate(cid)
    with pytest.raises(LookupError):
        services.verification.claims_for_org(org_id=org.id, candidate_id=cid)
