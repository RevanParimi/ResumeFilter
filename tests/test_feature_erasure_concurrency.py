"""Feature persistence refuses erased subjects across real connections."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.candidates.store import CandidateStore
from app.core.db import make_session_factory
from app.features.models import FeatureVectorRow
from app.features.store import FeatureStore
from app.main import create_app
from tests.conftest import ADMIN_HEADERS
from tests.test_feature_timestamps import T, _vector
from tests.test_interview_erasure import _candidate
from tests.test_report_erasure_concurrency import database


def vector(cid, value):
    mv = _vector(cid, T, T)
    return replace(mv, vector=mv.vector.model_copy(update={"values": {"sentinel": value}}))


@pytest.mark.parametrize("operation", ["insert", "update"])
@pytest.mark.parametrize("order", ["erase_first", "write_first"])
def test_vector_erasure_order(database, operation, order, log_output):
    engine, factory = database
    store = FeatureStore(factory)
    kept = vector("b", "synthetic kept feature")
    store.upsert_vector(kept)
    if operation == "update":
        store.upsert_vector(vector("a", "old"))
    stale = vector("a", "synthetic private feature")
    writer_factory = make_session_factory(engine)
    writer = FeatureStore(writer_factory)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20), "writer was not released"

    hook = "before_flush" if order == "erase_first" else "after_commit"
    event.listen(writer_factory, hook, pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(writer.upsert_vector, stale)
            try:
                assert ready.wait(20), "writer did not reach transaction boundary"
                assert CandidateStore(factory).delete_candidate("a")
            finally:
                release.set()
            result = pending.result(timeout=20)
            assert (result is None) if order == "erase_first" else isinstance(result, str)
    finally:
        event.remove(writer_factory, hook, pause)
    assert writer.upsert_vector(stale) is None
    assert store.get_vector("a", view_name="test", view_version=1, as_of=T) is None
    assert store.get_vector("b", view_name="test", view_version=1, as_of=T) == kept
    with factory() as session:
        assert list(session.scalars(select(FeatureVectorRow.candidate_id))) == ["b"]
    for private in ("synthetic private feature", "INSERT INTO", "UPDATE ml_feature_vectors"):
        assert private not in log_output.text


@pytest.mark.parametrize("failure", ["integrity", "stale"])
def test_unrelated_failure_propagates(database, failure):
    engine, factory = database
    store = FeatureStore(factory)
    if failure == "integrity":
        # Actual NOT NULL failure with a still-present parent.
        def invalid_row(session, *_):
            for row in session.new:
                if isinstance(row, FeatureVectorRow):
                    row.view_name = None

        event.listen(factory, "before_flush", invalid_row)
        try:
            with pytest.raises(IntegrityError):
                store.upsert_vector(vector("a", "private"))
        finally:
            event.remove(factory, "before_flush", invalid_row)
    else:
        # Independent vector deletion is not candidate erasure.
        store.upsert_vector(vector("a", "old"))
        writer_factory = make_session_factory(engine)

        def delete_vector(*_):
            with factory() as session:
                row = session.scalar(select(FeatureVectorRow).where(
                    FeatureVectorRow.candidate_id == "a"))
                session.delete(row)
                session.commit()

        event.listen(writer_factory, "before_flush", delete_vector, once=True)
        with pytest.raises(StaleDataError):
            FeatureStore(writer_factory).upsert_vector(vector("a", "new"))
    assert CandidateStore(factory).get_candidate("a") is not None
    assert store.upsert_vector(vector("a", "recovered"))


@pytest.mark.parametrize("operation", ["insert", "update"])
@pytest.mark.parametrize("door", ["admin", "portal"])
def test_materialize_api_skips_erased_vector(services, monkeypatch, operation, door, log_output):
    cid, _ = _candidate(services)
    bid, _ = _candidate(services, "Other Candidate")
    body = {"candidate_ids": [cid, "missing", bid]}
    with TestClient(create_app(services), headers=ADMIN_HEADERS,
                    raise_server_exceptions=False) as client:
        initial = client.post("/features/materialize", json=body)
        assert initial.status_code == 200
        assert initial.json()["materialized"] == 2
        if operation == "update":
            body["as_of"] = initial.json()["as_of"]
        factory = make_session_factory(services.candidates._session_factory.kw["bind"])
        monkeypatch.setattr(services.features, "_session_factory", factory)

        def erase(*_):
            if door == "portal":
                assert services.portal.erase(cid)["deleted"]
            else:
                assert services.candidates.delete_candidate(cid)

        event.listen(factory, "before_flush", erase, once=True)
        response = client.post("/features/materialize", json=body)
        assert response.status_code == 200, response.text
        assert response.json()["materialized"] == 1
        assert response.json()["skipped"] == 2
        retry = client.post("/features/materialize", json=body)
        assert retry.status_code == 200
        assert retry.json()["materialized"] == 1
        assert retry.json()["skipped"] == 2
        with services.candidates._session_factory() as session:
            assert set(session.scalars(select(FeatureVectorRow.candidate_id))) == {bid}
        assert services.ledger.audit_for_candidate(cid) == []
    assert "INSERT INTO" not in response.text
    assert "UPDATE ml_feature_vectors" not in log_output.text
