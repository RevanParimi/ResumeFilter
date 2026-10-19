"""Controlled lifecycle interleavings on separate SQLite/PostgreSQL connections."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import event, text

from app.core.db import make_session_factory
from app.candidates.store import CandidateStore
from app.interview.schema import InterviewAssessment
from app.interview.service import SessionConflictError
from app.interview.store import InterviewStore
from app.ledger.store import LedgerStore
from tests.test_interview_erasure_concurrency import _start, _turn
from tests.test_interview_store import NOW
from tests.test_report_erasure_concurrency import database  # noqa: F401


def store(factory, settings):
    return InterviewStore(factory, ledger=LedgerStore(factory, settings=settings), settings=settings)


def assessment(snapshot):
    return InterviewAssessment(session_id=snapshot.id, candidate_id=snapshot.candidate_id,
        questions_planned=len(snapshot.questions), questions_answered=len(snapshot.turns))


def finish(s, sid):
    return s.complete_session(sid, assess=assessment, at=NOW)


def attempt(job):
    try:
        return "ok", job()
    except SessionConflictError as exc:
        return "refused", str(exc)
    except LookupError as exc:
        return "missing", str(exc)


def race(engine, settings, first_job, second_job, *, before_release=None):
    first, second = make_session_factory(engine), make_session_factory(engine)
    ready, release, boundary = Event(), Event(), Event()
    pids = {}

    def paused(session, *_):
        if engine.dialect.name == "postgresql":
            pids["first"] = session.connection().scalar(text("SELECT pg_backend_pid()"))
        ready.set()
        assert release.wait(20), "first writer was not released"

    def began(session, transaction, connection):
        connection.info["interview_race_second"] = True
        if engine.dialect.name == "postgresql":
            pids["second"] = connection.scalar(text("SELECT pg_backend_pid()"))

    def lock_entered(connection, cursor, statement, *_):
        sql = statement.upper()
        if connection.info.get("interview_race_second") and (
            sql.startswith(("UPDATE CANDIDATES", "DELETE FROM CANDIDATES"))
            or ("FROM CANDIDATES" in sql and "FOR UPDATE" in sql)):
            boundary.set()

    event.listen(first, "before_flush", paused, once=True)
    event.listen(second, "after_begin", began, once=True)
    event.listen(engine, "before_cursor_execute", lock_entered)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            a = executor.submit(attempt, lambda: first_job(store(first, settings)))
            try:
                assert ready.wait(20)
                b = executor.submit(attempt, lambda: second_job(store(second, settings)))
                b.add_done_callback(lambda _: boundary.set())
                assert boundary.wait(20)
                if engine.dialect.name == "postgresql" and not b.done():
                    with engine.connect() as observer:
                        deadline = monotonic() + 15
                        while monotonic() < deadline:
                            if pids["first"] in observer.scalar(text("SELECT pg_blocking_pids(:pid)"), {"pid": pids["second"]}):
                                break
                        else:
                            pytest.fail("candidate lock did not serialize competing interview writes")
                if before_release:
                    before_release()
            finally:
                release.set()
            return a.result(timeout=20), b.result(timeout=20)
    finally:
        event.remove(engine, "before_cursor_execute", lock_entered)
        with engine.connect() as connection:
            connection.info.pop("interview_race_second", None)


def test_competing_starts_create_one_session_and_audit(database, settings):
    engine, factory = database
    results = race(engine, settings, lambda s: _start(s, "a"), lambda s: _start(s, "a"))
    assert [r[0] for r in results] == ["ok", "refused"]
    assert len(store(factory, settings).sessions_for_candidate("a")) == 1
    assert len([a for a in LedgerStore(factory).audit_for_candidate("a") if a.action == "interview.start"]) == 1


def test_competing_answers_record_the_current_question_once(database, settings):
    engine, factory = database
    s = store(factory, settings)
    sid = _start(s, "a").id
    results = race(engine, settings, lambda s: _turn(s, sid), lambda s: _turn(s, sid))
    assert [r[0] for r in results] == ["ok", "refused"]
    saved = s.get_session(sid)
    assert len(saved.turns) == 1 and saved.turns[0].sequence == 1


@pytest.mark.parametrize("answer_first", [False, True])
def test_finish_and_answer_use_the_committed_turns(database, settings, answer_first):
    engine, factory = database
    s = store(factory, settings)
    sid = _start(s, "a").id
    a, b = (lambda s: _turn(s, sid)), (lambda s: finish(s, sid))
    results = race(engine, settings, *( (a, b) if answer_first else (b, a) ))
    assert [r[0] for r in results] == (["ok", "ok"] if answer_first else ["ok", "refused"])
    saved = s.get_session(sid)
    assert saved.status.value == "completed"
    assert saved.assessment.questions_answered == len(saved.turns) == int(answer_first)


def test_competing_finishes_preserve_one_assessment_and_audit(database, settings):
    engine, factory = database
    s = store(factory, settings)
    sid = _start(s, "a").id
    results = race(engine, settings, lambda s: finish(s, sid), lambda s: finish(s, sid))
    assert [r[0] for r in results] == ["ok", "refused"]
    assert s.get_session(sid).assessment.questions_answered == 0
    assert len([a for a in LedgerStore(factory).audit_for_candidate("a") if a.action == "interview.complete"]) == 1


def test_expiry_is_rechecked_after_lock_wait(database, settings, monkeypatch):
    engine, factory = database
    s = store(factory, settings)
    sid = _start(s, "a").id
    clock = [NOW]
    monkeypatch.setattr("app.interview.store._utcnow", lambda: clock[0])
    results = race(engine, settings, lambda s: _turn(s, sid),
        lambda s: s.complete_session(sid, assess=assessment),
        before_release=lambda: clock.__setitem__(0, NOW + timedelta(days=1)))
    assert [r[0] for r in results] == ["ok", "refused"]
    assert s.get_session(sid).assessment is None


@pytest.mark.parametrize("operation", ["start", "turn", "finish"])
def test_erasure_waits_for_locked_write_then_removes_everything(database, settings, operation):
    engine, factory = database
    s = store(factory, settings)
    sid = _start(s, "a").id if operation != "start" else None
    job = {"start": lambda s: _start(s, "a"), "turn": lambda s: _turn(s, sid),
           "finish": lambda s: finish(s, sid)}[operation]
    results = race(engine, settings, job,
        lambda s: CandidateStore(s._session_factory).delete_candidate("a"))
    assert [r[0] for r in results] == ["ok", "ok"]
    assert s.sessions_for_candidate("a") == []
    assert LedgerStore(factory).audit_for_candidate("a") == []
