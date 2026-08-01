"""DPDP erasure sweeps an interview whole, through the CASCADEs alone. S7.3
adds NO new erasure path -- if this file needed one, the migration would be
wrong."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.candidates.schema import (
    CandidateProfile, DateRange, ExperienceEntry, ExtractedStr, ExtractionResult,
    SkillItem,
)
from app.interview.models import InterviewSessionRow, InterviewTurnRow
from app.ledger.schema import ConsentPurpose
from app.main import create_app
from tests.conftest import make_services

ANSWER = (
    "I rebuilt the ingestion path at Acme myself: the nightly PyTorch job kept "
    "failing on 8 GPUs, I traced it to a tokenizer change and cut p99 latency"
)


def _candidate(services, name="A Candidate"):
    profile = CandidateProfile(
        full_name=ExtractedStr(value=name),
        experience=[ExperienceEntry(employer="Acme Technologies",
                                    employer_canonical="Acme", title="ML Engineer",
                                    dates=DateRange(start="2021-03", end="2024-01"))],
        skills=[SkillItem(name="PyTorch", canonical="pytorch"),
                SkillItem(name="Spark", canonical="apache_spark")],
    )
    outcome = services.candidates.ingest(
        ExtractionResult(profile=profile, method="heuristic"), f"resume for {name}")
    return outcome.candidate_id, services.candidates.issue_access_key(
        outcome.candidate_id)


def _counts(services) -> tuple[int, int]:
    with services.candidates._session_factory() as s:
        sessions = s.execute(
            select(func.count()).select_from(InterviewSessionRow)).scalar_one()
        turns = s.execute(
            select(func.count()).select_from(InterviewTurnRow)).scalar_one()
    return sessions, turns


def _complete_an_interview(client, key) -> None:
    body = client.post("/portal/interviews", json={},
                       headers={"X-Candidate-Key": key}).json()
    sid, following = body["session"]["id"], body["next_question"]
    while following is not None:
        out = client.post(
            f"/portal/interviews/{sid}/answers",
            json={"question_id": following["id"], "text": ANSWER},
            headers={"X-Candidate-Key": key},
        ).json()
        following = out["next_question"]


@pytest.fixture
def wiring(settings):
    services = make_services(settings)
    with TestClient(create_app(services)) as client:
        cid, key = _candidate(services)
        org = services.ledger.create_organization("Globex Talent")
        org_key = services.ledger.issue_api_key(org.id)
        yield client, services, cid, key, org.id, org_key


def test_deleting_a_candidate_removes_their_sessions_and_turns(wiring):
    client, services, cid, key, _, _ = wiring
    _complete_an_interview(client, key)
    sessions, turns = _counts(services)
    assert sessions == 1 and turns >= 1

    assert client.delete("/portal/me",
                         headers={"X-Candidate-Key": key}).status_code == 200
    assert _counts(services) == (0, 0)


def test_the_org_read_404s_after_erasure_rather_than_returning_empty(wiring):
    client, services, cid, key, org_id, org_key = wiring
    _complete_an_interview(client, key)
    services.ledger.grant_consent(candidate_id=cid,
                                  purpose=ConsentPurpose.INTERVIEW_READ,
                                  org_id=org_id)
    path = f"/interview/candidates/{cid}/assessments"
    assert client.get(path, headers={"X-Org-Key": org_key}).status_code == 200

    client.delete("/portal/me", headers={"X-Candidate-Key": key})
    # 404, not an empty 200: the subject is gone, not merely uninteresting.
    assert client.get(path, headers={"X-Org-Key": org_key}).status_code == 404


def test_one_candidates_erasure_leaves_anothers_interview_intact(wiring):
    client, services, cid, key, _, _ = wiring
    _complete_an_interview(client, key)
    other_id, other_key = _candidate(services, name="Someone Else")
    _complete_an_interview(client, other_key)
    assert _counts(services)[0] == 2

    client.delete("/portal/me", headers={"X-Candidate-Key": key})
    assert _counts(services)[0] == 1
    kept = client.get("/portal/interviews",
                      headers={"X-Candidate-Key": other_key}).json()
    assert len(kept["interviews"]) == 1
