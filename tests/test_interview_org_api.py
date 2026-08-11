"""The org plane over HTTP, plus the portal's my-data integration. The line the
tests defend: an org sees numbers, the candidate sees words."""

import pytest
from fastapi.testclient import TestClient

from app.candidates.schema import (
    CandidateProfile, DateRange, ExperienceEntry, ExtractedStr, ExtractionResult,
    SkillItem,
)
from app.ledger.schema import ConsentPurpose
from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services

ANSWER = (
    "I rebuilt the ingestion path at Acme myself: the nightly PyTorch job kept "
    "failing on 8 GPUs, I traced it to a tokenizer change and cut p99 latency "
    "from 900 ms to 220 ms"
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


@pytest.fixture
def wiring(settings):
    services = make_services(settings)
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as client:
        cid, key = _candidate(services)
        org = services.ledger.create_organization("Globex Talent")
        org_key = services.ledger.issue_api_key(org.id)
        yield client, services, cid, key, org.id, org_key


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


def test_org_read_is_403_without_a_grant_then_200_after_it(wiring):
    client, services, cid, key, org_id, org_key = wiring
    _complete_an_interview(client, key)
    path = f"/interview/candidates/{cid}/assessments"

    assert client.get(path, headers={"X-Org-Key": org_key}).status_code == 403

    services.ledger.grant_consent(candidate_id=cid,
                                  purpose=ConsentPurpose.INTERVIEW_READ,
                                  org_id=org_id)
    resp = client.get(path, headers={"X-Org-Key": org_key})
    assert resp.status_code == 200
    body = resp.json()
    assert body["attempts"] == 1
    assert body["assessments"][0]["band"]
    assert body["assessments"][0]["advisory"] is True


def test_the_org_payload_never_contains_the_candidates_words(wiring):
    client, services, cid, key, org_id, org_key = wiring
    _complete_an_interview(client, key)
    services.ledger.grant_consent(candidate_id=cid,
                                  purpose=ConsentPurpose.INTERVIEW_READ,
                                  org_id=org_id)
    resp = client.get(f"/interview/candidates/{cid}/assessments",
                      headers={"X-Org-Key": org_key})
    assert ANSWER not in resp.text
    assert "transcript" not in resp.text


def test_revocation_closes_the_org_read(wiring):
    client, services, cid, key, org_id, org_key = wiring
    _complete_an_interview(client, key)
    grant = services.ledger.grant_consent(candidate_id=cid,
                                          purpose=ConsentPurpose.INTERVIEW_READ,
                                          org_id=org_id)
    path = f"/interview/candidates/{cid}/assessments"
    assert client.get(path, headers={"X-Org-Key": org_key}).status_code == 200

    services.ledger.revoke_consent(grant.id)
    assert client.get(path, headers={"X-Org-Key": org_key}).status_code == 403


def test_org_read_requires_an_org_key_and_404s_on_an_unknown_candidate(wiring):
    client, services, cid, key, org_id, org_key = wiring
    assert client.get(f"/interview/candidates/{cid}/assessments").status_code == 401
    assert client.get("/interview/candidates/nope/assessments",
                      headers={"X-Org-Key": org_key}).status_code == 404


def test_the_access_log_shows_the_org_query_with_its_name_resolved(wiring):
    client, services, cid, key, org_id, org_key = wiring
    _complete_an_interview(client, key)
    services.ledger.grant_consent(candidate_id=cid,
                                  purpose=ConsentPurpose.INTERVIEW_READ,
                                  org_id=org_id)
    client.get(f"/interview/candidates/{cid}/assessments",
               headers={"X-Org-Key": org_key})

    log = client.get("/portal/access-log", headers={"X-Candidate-Key": key}).json()
    queries = [e for e in log if e["action"] == "interview.query"]
    assert queries and queries[0]["actor_name"] == "Globex Talent"
    assert queries[0]["allowed"] is True


def test_my_data_lists_interviews_as_summaries_with_a_retention_window(wiring):
    client, services, cid, key, org_id, org_key = wiring
    _complete_an_interview(client, key)

    resp = client.get("/portal/me", headers={"X-Candidate-Key": key})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["interviews"]) == 1
    assert body["interviews"][0]["status"] == "completed"
    assert ANSWER not in resp.text            # summaries, not transcripts

    windows = {w["data_class"]: w for w in body["retention"]["windows"]}
    assert windows["interviews"]["ttl_days"] == 1095
    assert windows["interviews"]["oldest_item_at"] is not None
    # TRUE since S8.3 Phase B: the interview session rows this window covers
    # are now genuinely swept.
    assert body["retention"]["sweep_active"] is True
