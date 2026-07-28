from app.dashboard.schema import (
    CandidateCard, CodingRoundsSection, DashboardOverview, RecordsSection,
    ReputationSection, RequisitionSummary, SectionStatus,
)
from app.matching.schema import RequisitionStatus


def test_section_status_values():
    assert SectionStatus.AVAILABLE == "available"
    assert SectionStatus.CONSENT_REQUIRED == "consent_required"
    assert SectionStatus.NO_DATA == "no_data"


def test_overview_defaults_and_shape():
    ov = DashboardOverview(total_requisitions=0, by_status={})
    assert ov.advisory is True
    assert ov.requisitions == ()


def test_requisition_summary_flags():
    from datetime import datetime, timezone
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    rs = RequisitionSummary(
        id="r1", title="BE", status=RequisitionStatus.OPEN, must_have_skill_count=2,
        has_comp_band=True, has_skill_coverage_gate=False, created_at=now, updated_at=now,
    )
    assert rs.has_comp_band is True and rs.has_skill_coverage_gate is False


def test_card_sections_default_empty():
    card = CandidateCard(
        candidate_id="c1",
        reputation=ReputationSection(status=SectionStatus.CONSENT_REQUIRED),
        coding_rounds=CodingRoundsSection(status=SectionStatus.NO_DATA),
        records=RecordsSection(status=SectionStatus.NO_DATA),
    )
    assert card.advisory is True
    assert card.reputation.data is None
    assert card.coding_rounds.data == ()
    assert card.records.data == ()
