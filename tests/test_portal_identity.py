"""S7.1: the DPDP access view surfaces identity assurance + its retention window."""

from app.candidates.models import CandidateRow
from app.verification.schema import AssuranceLevel, VerificationMethod
from tests.conftest import make_services


def _candidate(services):
    with services.candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash="e" * 64)
        s.add(row)
        s.commit()
        return row.id


def test_my_data_reports_identity_assurance(settings):
    services = make_services(settings)
    cid = _candidate(services)
    services.verification.start(cid, VerificationMethod.SELF_ATTESTED)
    data = services.portal.my_data(cid)
    assert data.identity is not None
    assert data.identity.level is AssuranceLevel.SELF_ATTESTED


def test_my_data_reports_level_none_before_any_verification(settings):
    services = make_services(settings)
    cid = _candidate(services)
    assert services.portal.my_data(cid).identity.level is AssuranceLevel.NONE


def test_retention_policy_includes_the_verifications_window(settings):
    services = make_services(settings)
    cid = _candidate(services)
    classes = {w.data_class for w in services.portal.my_data(cid).retention.windows}
    assert "verifications" in classes
