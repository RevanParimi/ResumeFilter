"""Controlled interview writes across erasure, using real database connections."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.interview.models import InterviewSessionRow, InterviewTurnRow
from app.interview.schema import AnswerChannel, InterviewAssessment, ProxyRisk, TurnScore
from app.interview.store import InterviewStore
from app.ledger.models import AuditLogRow
from app.ledger.store import LedgerStore
from app.main import create_app
from tests.conftest import ADMIN_HEADERS
from tests.test_interview_erasure import _candidate, ANSWER
from tests.test_interview_store import NOW, _questions
from tests.test_report_erasure_concurrency import database  # shared isolated backend fixture


def _start(store, candidate_id):
    return store.create_session(candidate_id=candidate_id, domain="genai",
                                report_id=None, questions=_questions(),
                                assurance_level=0, at=NOW)


def _turn(store, sid):
    return store.add_turn(sid, question=_questions()[0], channel=AnswerChannel.TEXT,
                          transcript="synthetic private transcript sentinel",
                          word_count=5, audio_digest=None, audio_duration_seconds=None,
                          score=TurnScore(), asked_at=NOW, answered_at=NOW)


def _complete(store, sid):
    return store.complete_session(sid, assessment=InterviewAssessment(
        session_id=sid, candidate_id="a", questions_answered=1, questions_planned=2,
        proxy=ProxyRisk(),
    ), at=NOW)


@pytest.mark.parametrize("operation", ["start", "turn", "complete"])
@pytest.mark.parametrize("order", ["erase_first", "write_first"])
def test_interview_write_erasure_order(database, settings, operation, order, log_output):
    engine, factory = database
    ledger = LedgerStore(factory, settings=settings)
    store = InterviewStore(factory, ledger=ledger, settings=settings)
    b = _start(store, "b")
    _turn(store, b.id)
    a = _start(store, "a") if operation != "start" else None
    writer_factory = make_session_factory(engine)
    writer = InterviewStore(writer_factory, ledger=ledger, settings=settings)
    write = {"start": lambda: _start(writer, "a"),
             "turn": lambda: _turn(writer, a.id),
             "complete": lambda: _complete(writer, a.id)}[operation]
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20), "writer was not released"

    hook = "before_flush" if order == "erase_first" else "after_commit"
    event.listen(writer_factory, hook, pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(write)
            try:
                assert ready.wait(20), "writer did not reach transaction boundary"
                assert CandidateStore(factory).delete_candidate("a")
            finally:
                release.set()
            if order == "erase_first":
                with pytest.raises(LookupError):
                    pending.result(timeout=20)
            else:
                pending.result(timeout=20)
    finally:
        event.remove(writer_factory, hook, pause)
    with pytest.raises(LookupError):
        write()
    assert store.sessions_for_candidate("a") == []
    assert ledger.audit_for_candidate("a") == []
    kept = store.get_session(b.id)
    assert len(kept.turns) == 1
    assert kept.turns[0].transcript == "synthetic private transcript sentinel"
    with factory() as s:
        assert list(s.scalars(select(InterviewSessionRow.id))) == [b.id]
        assert list(s.scalars(select(InterviewTurnRow.session_id))) == [b.id]
    for private in ("synthetic private", "INSERT INTO", "UPDATE interview"):
        assert private not in log_output.text


def test_unrelated_integrity_failure_is_not_missing_interview(database, settings, monkeypatch):
    _, factory = database
    ledger = LedgerStore(factory, settings=settings)
    store = InterviewStore(factory, ledger=ledger, settings=settings)

    def invalid_audit(session, **kwargs):
        session.add(AuditLogRow(actor_type=None, action="interview.start",
                                entity_type="interview_session", entity_id="synthetic"))

    monkeypatch.setattr(ledger, "_audit", invalid_audit)
    with pytest.raises(IntegrityError):
        _start(store, "a")
    assert store.sessions_for_candidate("a") == []
    assert CandidateStore(factory).get_candidate("a") is not None


@pytest.mark.parametrize("operation", ["start", "turn", "complete", "reload",
                                       "start_flush", "turn_flush", "complete_flush"])
def test_api_erasure_after_authorization(services, monkeypatch, operation, log_output):
    at_flush = operation.endswith("_flush")
    operation = operation.removesuffix("_flush")
    cid, key = _candidate(services)
    bid, bkey = _candidate(services, "Other Candidate")
    store = services.interview._store
    with TestClient(create_app(services), headers=ADMIN_HEADERS,
                    raise_server_exceptions=False) as client:
        headers = {"X-Candidate-Key": key}
        b = client.post("/portal/interviews", json={},
                        headers={"X-Candidate-Key": bkey}).json()["session"]
        if operation != "start":
            a = client.post("/portal/interviews", json={}, headers=headers).json()
            sid = a["session"]["id"]
        method = {"start": "create_session", "turn": "add_turn",
                  "complete": "complete_session", "reload": "add_turn"}[operation]
        original = getattr(store, method)

        def erase_then_write(*args, **kwargs):
            if at_flush:
                # Separate factory keeps erasure's own flush out of this hook.
                writer_factory = make_session_factory(services.candidates._session_factory.kw["bind"])
                monkeypatch.setattr(store, "_session_factory", writer_factory)
                event.listen(writer_factory, "before_flush",
                             lambda *_: services.portal.erase(cid), once=True)
                return original(*args, **kwargs)
            if operation == "reload":
                result = original(*args, **kwargs)
            assert services.portal.erase(cid)["deleted"]
            return result if operation == "reload" else original(*args, **kwargs)

        monkeypatch.setattr(store, method, erase_then_write)
        if operation == "start":
            response = client.post("/portal/interviews", json={}, headers=headers)
        elif operation == "complete":
            response = client.post(f"/portal/interviews/{sid}/finish", headers=headers)
        else:
            response = client.post(f"/portal/interviews/{sid}/answers", headers=headers,
                                   json={"question_id": a["next_question"]["id"], "text": ANSWER})
        assert response.status_code == 404, response.text
        assert ANSWER not in response.text
        assert store.sessions_for_candidate(cid) == []
        assert services.ledger.audit_for_candidate(cid) == []
        assert store.get_session(b["id"]).candidate_id == bid
    for private in (ANSWER, "INSERT INTO", "UPDATE interview"):
        assert private not in log_output.text
