"""Consent-gated org disclosure. A NEW purpose, not a widening of
VERIFICATION_READ -- and every attempt, allowed or denied, is audited, because
surveillance must itself be observable."""

from datetime import datetime, timedelta, timezone

import pytest

from app.candidates.schema import (
    CandidateProfile, DateRange, ExperienceEntry, ExtractionResult, SkillItem,
)
from app.interview.schema import InterviewStatus
from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError
from tests.conftest import make_services

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)

ANSWER = (
    "I rebuilt the ingestion path at Acme myself: the nightly PyTorch job kept "
    "failing on 8 GPUs, I traced it to a tokenizer change and cut p99 latency "
    "from 900 ms to 220 ms"
)


def _ingest(candidates) -> str:
    profile = CandidateProfile(
        experience=[ExperienceEntry(employer="Acme Technologies",
                                    employer_canonical="Acme", title="ML Engineer",
                                    dates=DateRange(start="2021-03", end="2024-01"))],
        skills=[SkillItem(name="PyTorch", canonical="pytorch"),
                SkillItem(name="Spark", canonical="apache_spark")],
    )
    outcome = candidates.ingest(
        ExtractionResult(profile=profile, method="heuristic"), "resume text")
    return outcome.candidate_id


async def _completed_session(services, cid):
    session = services.interview.start(cid, at=NOW)
    following = services.interview.next_question(session)
    moment = NOW
    while following is not None:
        moment += timedelta(seconds=60)
        session, following = await services.interview.answer(
            cid, session.id, question_id=following.id, text=ANSWER, at=moment
        )
    return session


@pytest.fixture
def wiring(settings):
    services = make_services(settings)
    cid = _ingest(services.candidates)
    org = services.ledger.create_organization("Globex Talent")
    return services, cid, org.id


def _grant(services, cid, org_id, purpose):
    # `now=NOW`, not wall-clock: the S7.2 review found tests that granted at the
    # real clock and asserted at a pinned NOW, which began failing the moment
    # the day passed that instant. Clock injection exists for exactly this.
    return services.ledger.grant_consent(
        candidate_id=cid, purpose=purpose, org_id=org_id, now=NOW
    )


def test_no_grant_is_refused(wiring):
    services, cid, org_id = wiring
    with pytest.raises(ConsentError):
        services.interview.assessments_for_org(
            org_id=org_id, candidate_id=cid, at=NOW)


def test_a_denied_read_is_still_audited(wiring):
    services, cid, org_id = wiring
    with pytest.raises(ConsentError):
        services.interview.assessments_for_org(
            org_id=org_id, candidate_id=cid, at=NOW)
    entries = [e for e in services.ledger.audit_for_candidate(cid)
               if e.action == "interview.query"]
    assert entries and entries[-1].details["allowed"] is False
    assert entries[-1].actor_id == org_id


async def test_a_grant_allows_it_and_the_allowed_read_is_audited(wiring):
    services, cid, org_id = wiring
    await _completed_session(services, cid)
    _grant(services, cid, org_id, ConsentPurpose.INTERVIEW_READ)

    summaries = services.interview.assessments_for_org(
        org_id=org_id, candidate_id=cid, at=NOW)
    assert len(summaries) == 1
    entries = [e for e in services.ledger.audit_for_candidate(cid)
               if e.action == "interview.query"]
    assert entries[-1].details["allowed"] is True
    assert entries[-1].details["sessions"] == 1


async def test_a_verification_read_grant_does_not_unlock_interviews(wiring):
    """The whole reason INTERVIEW_READ exists as its own purpose."""
    services, cid, org_id = wiring
    await _completed_session(services, cid)
    _grant(services, cid, org_id, ConsentPurpose.VERIFICATION_READ)

    with pytest.raises(ConsentError):
        services.interview.assessments_for_org(
            org_id=org_id, candidate_id=cid, at=NOW)


async def test_revocation_closes_it_again(wiring):
    services, cid, org_id = wiring
    await _completed_session(services, cid)
    grant = _grant(services, cid, org_id, ConsentPurpose.INTERVIEW_READ)
    assert services.interview.assessments_for_org(
        org_id=org_id, candidate_id=cid, at=NOW)

    services.ledger.revoke_consent(grant.id)
    with pytest.raises(ConsentError):
        services.interview.assessments_for_org(
            org_id=org_id, candidate_id=cid, at=NOW)


async def test_only_completed_sessions_are_disclosed(wiring):
    services, cid, org_id = wiring
    await _completed_session(services, cid)
    # A second, unfinished session: real to the candidate, not an attempt yet.
    live = services.interview.start(cid, at=NOW + timedelta(hours=4))
    _grant(services, cid, org_id, ConsentPurpose.INTERVIEW_READ)

    org_view = services.interview.assessments_for_org(
        org_id=org_id, candidate_id=cid, at=NOW + timedelta(hours=4))
    assert len(org_view) == 1
    assert live.id not in {s.id for s in org_view}

    mine = services.interview.list_for_candidate(cid, at=NOW + timedelta(hours=4))
    assert len(mine) == 2
    assert {s.status for s in mine} == {
        InterviewStatus.COMPLETED, InterviewStatus.IN_PROGRESS}


async def test_the_org_payload_carries_no_transcript(wiring):
    services, cid, org_id = wiring
    await _completed_session(services, cid)
    _grant(services, cid, org_id, ConsentPurpose.INTERVIEW_READ)

    summaries = services.interview.assessments_for_org(
        org_id=org_id, candidate_id=cid, at=NOW)
    blob = str([s.model_dump(mode="json") for s in summaries])
    assert ANSWER not in blob
    assert "transcript" not in blob
    # But the advisory numbers an employer is entitled to ARE there.
    assert summaries[0].dimensions and summaries[0].proxy_band


def test_unknown_org_or_candidate_is_a_lookup_error(wiring):
    services, cid, org_id = wiring
    with pytest.raises(LookupError):
        services.interview.assessments_for_org(
            org_id="nope", candidate_id=cid, at=NOW)
    with pytest.raises(LookupError):
        services.interview.assessments_for_org(
            org_id=org_id, candidate_id="nope", at=NOW)
