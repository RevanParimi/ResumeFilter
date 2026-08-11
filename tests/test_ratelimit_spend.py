"""S8.3 Phase A: bounded per CALL is not bounded per CALLER.

`process` is capped at screening_max_items_per_call, which bounds ONE request
and says nothing at all about a client in a loop -- and every call bills a
model. The S8.5 wiring session named this gap when it made ANY error stop the
browser's driver loop, because there was no limiter to stop it properly.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def _key(services, name="Agency A"):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def _register(c, key, texts, name="Q3"):
    return c.post("/screening/batches", headers={"X-Org-Key": key},
                  json={"name": name, "domain": "genai",
                        "items": [{"resume_text": t} for t in texts]})


def test_process_is_refused_past_the_per_org_hourly_limit(
    settings, fake_github, flywheel, genuine_resume
):
    tuned = settings.model_copy(update={"rate_limit_process_per_hour_per_org": 2})
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume, genuine_resume]).json()["id"]
        for _ in range(2):
            assert c.post(f"/screening/batches/{bid}/process",
                          headers={"X-Org-Key": key}).status_code == 200
        refused = c.post(f"/screening/batches/{bid}/process",
                         headers={"X-Org-Key": key})
    assert refused.status_code == 429
    assert refused.json()["detail"] == "rate_limited"
    assert int(refused.headers["Retry-After"]) > 0


def test_one_org_s_spend_does_not_limit_another(
    settings, fake_github, flywheel, genuine_resume
):
    """The scope is the ORG. A global counter would let one noisy customer stop
    every other customer's screening -- a denial of service we would be
    inflicting on ourselves."""
    tuned = settings.model_copy(update={"rate_limit_process_per_hour_per_org": 1})
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        bid_a = _register(c, key_a, [genuine_resume]).json()["id"]
        assert c.post(f"/screening/batches/{bid_a}/process",
                      headers={"X-Org-Key": key_a}).status_code == 200
        # A is now at its limit for the hour...
        bid_a2 = _register(c, key_a, [genuine_resume], name="Q4").json()["id"]
        assert c.post(f"/screening/batches/{bid_a2}/process",
                      headers={"X-Org-Key": key_a}).status_code == 429
        # ...and B is entirely unaffected.
        bid_b = _register(c, key_b, [genuine_resume]).json()["id"]
        assert c.post(f"/screening/batches/{bid_b}/process",
                      headers={"X-Org-Key": key_b}).status_code == 200


def test_the_limit_is_checked_before_any_item_is_claimed(
    settings, fake_github, flywheel, genuine_resume
):
    """A refused call must not leave items stuck in `processing` waiting out a
    claim timeout -- the S8.4 Phase B finding (4) shape: a bound that runs
    AFTER the work it bounds."""
    tuned = settings.model_copy(update={
        "rate_limit_process_per_hour_per_org": 1,
        "screening_max_items_per_call": 1,
    })
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume, genuine_resume]).json()["id"]
        assert c.post(f"/screening/batches/{bid}/process",
                      headers={"X-Org-Key": key}).status_code == 200
        assert c.post(f"/screening/batches/{bid}/process",
                      headers={"X-Org-Key": key}).status_code == 429
        detail = c.get(f"/screening/batches/{bid}",
                       headers={"X-Org-Key": key}).json()
    assert detail["counts"].get("processing", 0) == 0
    assert detail["counts"].get("pending", 0) == 1


def test_an_unlimited_org_is_unaffected_when_the_limiter_is_off(
    settings, fake_github, flywheel, genuine_resume
):
    tuned = settings.model_copy(update={
        "rate_limit_enabled": False, "rate_limit_process_per_hour_per_org": 1,
    })
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        for _ in range(4):
            assert c.post(f"/screening/batches/{bid}/process",
                          headers={"X-Org-Key": key}).status_code == 200


# ── the OTHER spend path: ASR ────────────────────────────────────────────────
#
# `asr_transcribe` was the sprint's fourth rule and the only one with no
# behavioural test at all -- tests/test_ratelimit_service.py named it in a list
# of rules that resolve, which proves the config table is populated and nothing
# about whether a transcription is ever refused. It is also the rule that spends
# money per second of audio, and the one the S7.3 review named as the open
# spend surface.

import base64  # noqa: E402

from app.candidates.schema import (  # noqa: E402
    CandidateProfile, DateRange, ExperienceEntry, ExtractedStr, ExtractionResult,
    SkillItem,
)
from tests.conftest import FakeSpeech  # noqa: E402

AUDIO_B64 = base64.b64encode(b"not-really-audio-but-valid-base64").decode()
TYPED = (
    "I rebuilt the ingestion path at Acme myself: the nightly job kept failing "
    "on 8 GPUs and I traced it to a tokenizer change, then cut p99 latency from "
    "900 ms to 220 ms after the rollback"
)


def _candidate_key(services, name="A Candidate"):
    profile = CandidateProfile(
        full_name=ExtractedStr(value=name),
        experience=[ExperienceEntry(
            employer="Acme Technologies", employer_canonical="Acme",
            title="ML Engineer", dates=DateRange(start="2021-03", end="2024-01"),
        )],
        skills=[SkillItem(name="PyTorch", canonical="pytorch"),
                SkillItem(name="Spark", canonical="apache_spark")],
    )
    outcome = services.candidates.ingest(
        ExtractionResult(profile=profile, method="heuristic"), f"resume for {name}")
    return services.candidates.issue_access_key(outcome.candidate_id)


def _start_interview(c, key) -> dict:
    resp = c.post("/portal/interviews", json={}, headers={"X-Candidate-Key": key})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _answer(c, key, session_id, question_id, **body):
    return c.post(
        f"/portal/interviews/{session_id}/answers",
        json={"question_id": question_id, **body},
        headers={"X-Candidate-Key": key},
    )


def _asr_services(settings, flywheel, limit=1):
    tuned = settings.model_copy(update={
        "rate_limit_asr_per_hour_per_candidate": limit,
    })
    speech = FakeSpeech(text=TYPED, settings=tuned)
    return make_services(tuned, flywheel=flywheel, speech=speech), speech


def test_audio_answers_are_refused_past_the_per_candidate_limit(settings, flywheel):
    services, speech = _asr_services(settings, flywheel, limit=1)
    with _client(services) as c:
        key = _candidate_key(services)
        body = _start_interview(c, key)
        sid = body["session"]["id"]
        first = _answer(c, key, sid, body["next_question"]["id"],
                        audio_b64=AUDIO_B64, mime="audio/wav")
        assert first.status_code == 200, first.text
        refused = _answer(c, key, sid, first.json()["next_question"]["id"],
                          audio_b64=AUDIO_B64, mime="audio/wav")

    assert refused.status_code == 429
    assert refused.json()["detail"] == "rate_limited"
    assert int(refused.headers["Retry-After"]) > 0
    # AND THE VENDOR WAS NEVER CALLED. A limiter that refuses after paying for
    # the transcription bounds the response and not the bill, which is the only
    # thing this rule exists to bound.
    assert len(speech.calls) == 1


def test_a_typed_answer_never_consumes_the_transcription_budget(settings, flywheel):
    """The rule fires only when audio is present. A candidate who types every
    answer must never be refused by a rule about speech-to-text."""
    services, speech = _asr_services(settings, flywheel, limit=1)
    with _client(services) as c:
        key = _candidate_key(services)
        body = _start_interview(c, key)
        sid = body["session"]["id"]
        typed = _answer(c, key, sid, body["next_question"]["id"], text=TYPED)
        assert typed.status_code == 200, typed.text
        # The budget is untouched, so the FIRST audio answer still goes through.
        audio = _answer(c, key, sid, typed.json()["next_question"]["id"],
                        audio_b64=AUDIO_B64, mime="audio/wav")
        assert audio.status_code == 200, audio.text
    assert len(speech.calls) == 1


def test_one_candidate_s_transcription_spend_does_not_limit_another(
    settings, flywheel
):
    """The scope is the CANDIDATE. A global counter would let one person's
    interview stop everybody else's."""
    services, _ = _asr_services(settings, flywheel, limit=1)
    with _client(services) as c:
        key_a = _candidate_key(services, "Candidate A")
        key_b = _candidate_key(services, "Candidate B")

        body_a = _start_interview(c, key_a)
        sid_a = body_a["session"]["id"]
        first = _answer(c, key_a, sid_a, body_a["next_question"]["id"],
                        audio_b64=AUDIO_B64, mime="audio/wav")
        assert first.status_code == 200
        assert _answer(c, key_a, sid_a, first.json()["next_question"]["id"],
                       audio_b64=AUDIO_B64, mime="audio/wav").status_code == 429

        body_b = _start_interview(c, key_b)
        assert _answer(c, key_b, body_b["session"]["id"],
                       body_b["next_question"]["id"],
                       audio_b64=AUDIO_B64, mime="audio/wav").status_code == 200


def test_an_asr_denial_is_counted_in_metrics(settings, flywheel):
    """The pairing this sprint is built on, for the rule that had neither half
    tested. Before the S8.3 review the production container built the interview
    limiter with metrics=None, so this counter stayed empty in the one place it
    mattered -- see tests/test_ratelimit_wiring.py."""
    services, _ = _asr_services(settings, flywheel, limit=1)
    with _client(services) as c:
        key = _candidate_key(services)
        body = _start_interview(c, key)
        sid = body["session"]["id"]
        first = _answer(c, key, sid, body["next_question"]["id"],
                        audio_b64=AUDIO_B64, mime="audio/wav")
        _answer(c, key, sid, first.json()["next_question"]["id"],
                audio_b64=AUDIO_B64, mime="audio/wav")
        text = c.get("/metrics", headers=ADMIN_HEADERS).text

    assert 'rule="asr_transcribe"' in text
    assert 'scope="candidate"' in text
    assert 'decision="denied"' in text
