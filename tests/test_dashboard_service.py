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


def test_board_cross_org_is_none(services):
    a = _org(services, "A")
    b = _org(services, "B")
    req = services.jobs.create_requisition(a, JobRequisitionInput(
        title="A-req", must_have_skills=("python",)))
    assert services.dashboard.board(b, req.id) is None


def test_board_composes_req_comp_and_empty_match(services):
    org_id = _org(services)
    req = services.jobs.create_requisition(org_id, JobRequisitionInput(
        title="Senior Backend Engineer", must_have_skills=("python",),
        min_years_experience=7, location_tiers=("metro",),
        comp_band={"ctc_min": 800000, "ctc_max": 900000},
    ))
    board = services.dashboard.board(org_id, req.id)
    assert board is not None
    assert board.requisition.id == req.id
    assert board.comp.advisory is True                 # comp benchmark composed
    assert board.match.pool_size == 0                  # nothing materialized -> empty
    assert board.match.ranked == ()
    assert board.advisory is True


from datetime import timedelta

from app.ledger.schema import ConsentPurpose, InterviewOutcome, InterviewStage


def _candidate(services, name="Ann", email="ann@x.io"):
    saved = services.candidates.ingest(
        ExtractionResult(
            profile=CandidateProfile(
                full_name=ExtractedStr(value=name),
                contact=ContactInfo(email=ExtractedStr(value=email)),
                skills=[SkillItem(name="python", canonical="python")],
            ),
            method="heuristic",
        ),
        resume_text=email,
    )
    return saved.candidate_id


def test_card_all_sections_consent_required_without_grant(services):
    org_id = _org(services)
    cand_id = _candidate(services)
    card = services.dashboard.card(org_id, cand_id)
    assert card.candidate_id == cand_id
    assert card.reputation.status == SectionStatus.CONSENT_REQUIRED
    assert card.coding_rounds.status == SectionStatus.CONSENT_REQUIRED
    assert card.records.status == SectionStatus.CONSENT_REQUIRED
    assert card.reputation.data is None


def test_card_sections_available_after_read_grant(services):
    org_id = _org(services)
    cand_id = _candidate(services)
    # A submitted interview record needs a write grant; reading needs a read grant.
    services.ledger.grant_consent(
        candidate_id=cand_id, purpose=ConsentPurpose.LEDGER_WRITE, org_id=org_id,
        expires_at=NOW + timedelta(days=90))
    services.ledger.submit_interview_record(
        org_id=org_id, candidate_id=cand_id, stage=InterviewStage.TECH,
        outcome=InterviewOutcome.ADVANCED, interviewed_at=NOW)
    services.ledger.grant_consent(
        candidate_id=cand_id, purpose=ConsentPurpose.LEDGER_READ, org_id=org_id,
        expires_at=NOW + timedelta(days=90))

    card = services.dashboard.card(org_id, cand_id)
    assert card.records.status == SectionStatus.AVAILABLE
    assert len(card.records.data) == 1
    # No coding rounds submitted -> granted but empty -> no_data.
    assert card.coding_rounds.status == SectionStatus.NO_DATA
    # Reputation reads the one record; with consent it is AVAILABLE (has observations).
    assert card.reputation.status == SectionStatus.AVAILABLE


def test_card_unknown_candidate_raises_lookuperror(services):
    import pytest
    org_id = _org(services)
    with pytest.raises(LookupError):
        services.dashboard.card(org_id, "no-such-candidate")
