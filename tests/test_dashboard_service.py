from datetime import datetime, timezone

from app.candidates.schema import (
    CandidateProfile, ContactInfo, ExtractedStr, ExtractionResult, SkillItem,
)
from app.matching.schema import JobRequisitionInput, RequisitionStatus
from app.dashboard.schema import SectionStatus

NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)


def _org(services, name="Acme"):
    return services.ledger.create_organization(name).id


def test_overview_counts_and_flags(services):
    org_id = _org(services)
    services.jobs.create_requisition(org_id, JobRequisitionInput(
        title="Open BE", must_have_skills=("python", "django"),
        min_skill_coverage=0.5, comp_band={"ctc_min": 800000, "ctc_max": 900000},
    ))
    services.jobs.create_requisition(org_id, JobRequisitionInput(
        title="Closed FE", status=RequisitionStatus.CLOSED, must_have_skills=("react",),
    ))

    ov = services.dashboard.overview(org_id)
    assert ov.total_requisitions == 2
    assert ov.by_status == {"open": 1, "closed": 1}
    assert ov.advisory is True
    open_row = next(r for r in ov.requisitions if r.title == "Open BE")
    assert open_row.must_have_skill_count == 2
    assert open_row.has_comp_band is True
    assert open_row.has_skill_coverage_gate is True
    closed_row = next(r for r in ov.requisitions if r.title == "Closed FE")
    assert closed_row.has_comp_band is False
    assert closed_row.has_skill_coverage_gate is False


def test_overview_scoped_to_org(services):
    a = _org(services, "A")
    b = _org(services, "B")
    services.jobs.create_requisition(a, JobRequisitionInput(
        title="A-req", must_have_skills=("python",)))
    assert services.dashboard.overview(b).total_requisitions == 0
