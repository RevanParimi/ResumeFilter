"""S7.3 routes. Cross-candidate isolation stays structural: the subject is
resolved from the key, never from a path or body param."""

import base64

import pytest
from fastapi.testclient import TestClient

from app.candidates.models import CandidateRow
from app.candidates.schema import (
    CandidateProfile, DateRange, ExperienceEntry, ExtractedStr, ExtractionResult,
    SkillItem,
)
from app.main import create_app
from tests.conftest import ADMIN_HEADERS, FakeSpeech, make_services

ANSWER = (
    "I rebuilt the ingestion path at Acme myself: the nightly PyTorch job kept "
    "failing on 8 GPUs, I traced it to a tokenizer change and cut p99 latency "
    "from 900 ms to 220 ms after the rollback"
)
AUDIO_B64 = base64.b64encode(b"not-really-audio-but-valid-base64").decode()


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
def app_client(settings):
    services = make_services(settings)
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as client:
        yield client, services


def _start(client, key) -> dict:
    resp = client.post("/portal/interviews", json={}, headers={"X-Candidate-Key": key})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _answer(client, key, session_id, question_id, **body) -> "object":
    return client.post(
        f"/portal/interviews/{session_id}/answers",
        json={"question_id": question_id, **body},
        headers={"X-Candidate-Key": key},
    )


def test_start_returns_a_session_and_a_first_question(app_client):
    client, services = app_client
    _, key = _candidate(services)
    body = _start(client, key)
    assert body["session"]["status"] == "in_progress"
    assert body["next_question"]["sequence"] == 1
    assert body["session"]["assurance_level_at_start"] == 0


def test_start_is_422_when_there_is_nothing_to_ask(app_client):
    client, services = app_client
    with services.candidates._session_factory() as s:
        s.add(CandidateRow(id="bare_1"))
        s.commit()
    key = services.candidates.issue_access_key("bare_1")
    resp = client.post("/portal/interviews", json={},
                       headers={"X-Candidate-Key": key})
    assert resp.status_code == 422


def test_a_second_start_while_one_is_live_is_409(app_client):
    client, services = app_client
    _, key = _candidate(services)
    _start(client, key)
    resp = client.post("/portal/interviews", json={},
                       headers={"X-Candidate-Key": key})
    assert resp.status_code == 409


def test_every_route_requires_the_candidate_key(app_client):
    client, services = app_client
    _, key = _candidate(services)
    sid = _start(client, key)["session"]["id"]
    for method, path, body in (
        ("post", "/portal/interviews", {}),
        ("get", "/portal/interviews", None),
        ("get", f"/portal/interviews/{sid}", None),
        ("post", f"/portal/interviews/{sid}/answers", {"question_id": "x", "text": "y"}),
        ("post", f"/portal/interviews/{sid}/finish", {}),
    ):
        call = getattr(client, method)
        kwargs = {} if body is None else {"json": body}
        assert call(path, **kwargs).status_code == 401
        assert call(path, headers={"X-Candidate-Key": "wrong"},
                    **kwargs).status_code == 401


def test_another_candidates_session_is_404_not_403(app_client):
    client, services = app_client
    _, key_one = _candidate(services, name="One")
    _, key_two = _candidate(services, name="Two")
    sid = _start(client, key_one)["session"]["id"]

    assert client.get(f"/portal/interviews/{sid}",
                      headers={"X-Candidate-Key": key_two}).status_code == 404
    assert _answer(client, key_two, sid, "whatever", text=ANSWER).status_code == 404


def test_a_text_answer_is_scored_and_advances(app_client):
    client, services = app_client
    _, key = _candidate(services)
    body = _start(client, key)
    sid, qid = body["session"]["id"], body["next_question"]["id"]

    resp = _answer(client, key, sid, qid, text=ANSWER)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert len(out["session"]["turns"]) == 1
    assert out["session"]["turns"][0]["score"]["dimensions"]
    assert out["next_question"]["sequence"] == 2


def test_the_wrong_question_id_is_409(app_client):
    client, services = app_client
    _, key = _candidate(services)
    body = _start(client, key)
    sid = body["session"]["id"]
    later = body["session"]["questions"][1]["id"]
    assert _answer(client, key, sid, later, text=ANSWER).status_code == 409


def test_audio_with_no_provider_is_422_speech_unavailable(app_client):
    client, services = app_client
    _, key = _candidate(services)
    body = _start(client, key)
    resp = _answer(client, key, body["session"]["id"], body["next_question"]["id"],
                   audio_b64=AUDIO_B64, mime="audio/wav")
    assert resp.status_code == 422
    assert "speech_unavailable" in resp.json()["detail"]


def test_audio_is_transcribed_when_a_provider_exists(settings):
    services = make_services(settings, speech=FakeSpeech(text=ANSWER,
                                                         settings=settings))
    with TestClient(create_app(services), headers=ADMIN_HEADERS) as client:
        _, key = _candidate(services)
        body = _start(client, key)
        resp = _answer(client, key, body["session"]["id"],
                       body["next_question"]["id"],
                       audio_b64=AUDIO_B64, mime="audio/wav")
        assert resp.status_code == 200, resp.text
        turn = resp.json()["session"]["turns"][0]
        assert turn["channel"] == "audio"
        assert turn["transcript"] == ANSWER
        assert len(turn["audio_digest"]) == 64
        assert AUDIO_B64 not in resp.text        # the payload never comes back


def test_oversize_answers_are_422(app_client):
    client, services = app_client
    _, key = _candidate(services)
    body = _start(client, key)
    sid, qid = body["session"]["id"], body["next_question"]["id"]

    huge_text = "x " * services.settings.interview_max_answer_chars
    assert _answer(client, key, sid, qid, text=huge_text).status_code == 422
    huge_audio = "A" * (services.settings.interview_max_audio_b64_chars + 1)
    assert _answer(client, key, sid, qid,
                   audio_b64=huge_audio, mime="audio/wav").status_code == 422


def test_an_answer_with_no_body_is_400(app_client):
    client, services = app_client
    _, key = _candidate(services)
    body = _start(client, key)
    resp = _answer(client, key, body["session"]["id"], body["next_question"]["id"])
    assert resp.status_code == 400


def test_completing_every_question_returns_an_advisory_assessment(app_client):
    client, services = app_client
    _, key = _candidate(services)
    body = _start(client, key)
    sid = body["session"]["id"]
    following = body["next_question"]
    while following is not None:
        out = _answer(client, key, sid, following["id"], text=ANSWER).json()
        following = out["next_question"]

    session = out["session"]
    assert session["status"] == "completed"
    assessment = session["assessment"]
    assert assessment["advisory"] is True
    assert assessment["human_review_required"] is True
    assert assessment["band"]
    assert assessment["proxy"]["band"] in ("low", "moderate", "elevated")
    assert assessment["proxy"]["assurance_level_at_start"] == 0


def test_finish_completes_early(app_client):
    client, services = app_client
    _, key = _candidate(services)
    body = _start(client, key)
    sid = body["session"]["id"]
    _answer(client, key, sid, body["next_question"]["id"], text=ANSWER)

    resp = client.post(f"/portal/interviews/{sid}/finish",
                       headers={"X-Candidate-Key": key})
    assert resp.status_code == 200
    assert resp.json()["session"]["status"] == "completed"
    # A second finish is a conflict, not a silent no-op.
    assert client.post(f"/portal/interviews/{sid}/finish",
                       headers={"X-Candidate-Key": key}).status_code == 409


def test_the_detail_view_shows_the_candidate_their_own_transcripts(app_client):
    client, services = app_client
    _, key = _candidate(services)
    body = _start(client, key)
    sid = body["session"]["id"]
    _answer(client, key, sid, body["next_question"]["id"], text=ANSWER)

    resp = client.get(f"/portal/interviews/{sid}", headers={"X-Candidate-Key": key})
    assert resp.status_code == 200
    assert ANSWER in resp.text


def test_the_list_view_carries_no_transcripts(app_client):
    client, services = app_client
    _, key = _candidate(services)
    body = _start(client, key)
    _answer(client, key, body["session"]["id"], body["next_question"]["id"],
            text=ANSWER)

    resp = client.get("/portal/interviews", headers={"X-Candidate-Key": key})
    assert resp.status_code == 200
    assert ANSWER not in resp.text
    assert "transcript" not in resp.text
    assert len(resp.json()["interviews"]) == 1
