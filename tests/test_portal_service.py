from datetime import datetime, timezone

import pytest

from app.candidates.models import CandidateRow
from app.ledger.schema import (
    ConsentPurpose, InterviewOutcome, InterviewStage,
)
from app.portal.schema import ConsentState
from app.portal.service import PortalService
from app.schemas.report import Report
from tests.conftest import make_services


def _cid(services) -> str:
    with services.candidates._session_factory() as s:
        row = CandidateRow(full_name="Meera")
        s.add(row)
        s.commit()
        return row.id


def _portal(services) -> PortalService:
    return services.portal


def test_my_data_composes_reports_as_refs_only(settings):
    services = make_services(settings)
    cid = _cid(services)
    services.report_store.save(Report(candidate_id=cid, domain="genai"))
    md = _portal(services).my_data(cid)
    assert md.candidate_id == cid
    assert len(md.reports) == 1
    dumped = md.reports[0].model_dump()
    assert set(dumped) == {"report_id", "domain", "created_at"}  # no internals
    # retention posture present for every class
    assert {w.data_class for w in md.retention.windows}  # non-empty
    assert md.retention.sweep_active is False


def test_my_data_unknown_candidate_raises(settings):
    services = make_services(settings)
    with pytest.raises(LookupError):
        _portal(services).my_data("nope")


def test_access_log_projects_audit_with_org_name_newest_first(settings):
    services = make_services(settings)
    cid = _cid(services)
    org = services.ledger.create_organization("Acme")
    # write + read consent so a disclosure gets audited
    services.ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org.id)
    services.ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ, org_id=org.id)
    services.ledger.submit_interview_record(
        org_id=org.id, candidate_id=cid, stage=InterviewStage.TECH,
        outcome=InterviewOutcome.ADVANCED, interviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    services.ledger.query_records_for_org(org_id=org.id, candidate_id=cid)  # allowed read
    log = _portal(services).access_log(cid)
    assert log, "expected audit entries"
    actions = {e.action for e in log}
    assert "record.query" in actions and "record.submit" in actions
    q = next(e for e in log if e.action == "record.query")
    assert q.actor_type == "org" and q.actor_name == "Acme" and q.allowed is True
    # newest first
    ats = [e.at for e in log]
    assert ats == sorted(ats, reverse=True)


def test_consents_labels_states(settings):
    services = make_services(settings)
    cid = _cid(services)
    g_active = services.ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ)
    g_revoked = services.ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE)
    services.ledger.revoke_consent(g_revoked.id)
    views = {v.grant.id: v.state for v in _portal(services).consents(cid)}
    assert views[g_active.id] == ConsentState.ACTIVE
    assert views[g_revoked.id] == ConsentState.REVOKED


def test_grant_writes_first_party_consent(settings):
    services = make_services(settings)
    cid = _cid(services)
    g = _portal(services).grant(cid, purpose=ConsentPurpose.LEDGER_READ)
    assert g.candidate_id == cid
    # audited as actor_type="candidate"
    audit = services.ledger.audit_for_candidate(cid)
    grant_rows = [a for a in audit if a.action == "consent.grant"]
    assert grant_rows and grant_rows[-1].actor_type == "candidate"


def test_revoke_is_ownership_enforced(settings):
    services = make_services(settings)
    a = _cid(services)
    b = _cid(services)
    g_b = services.ledger.grant_consent(candidate_id=b, purpose=ConsentPurpose.LEDGER_READ)
    # candidate A cannot revoke candidate B's grant
    with pytest.raises(LookupError):
        _portal(services).revoke(a, g_b.id)
    assert services.ledger.get_grant(g_b.id).revoked_at is None  # untouched
    # owner can
    assert _portal(services).revoke(b, g_b.id) is True
    assert services.ledger.get_grant(g_b.id).revoked_at is not None
