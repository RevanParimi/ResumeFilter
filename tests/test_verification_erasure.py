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
