"""Feature snapshot instants must survive the database session timezone."""

from datetime import datetime, timedelta, timezone
import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.candidates.models import CandidateRow
from app.candidates.store import CandidateStore
from app.core.db import Base, make_engine, make_session_factory
from app.features.materialize import MaterializedVector
from app.features.schema import FeatureVector
from app.features.store import FeatureStore


@pytest.fixture(params=["sqlite", "UTC", "Asia/Calcutta"])
def feature_database(request, tmp_path):
    bootstrap = None
    schema = None
    if request.param == "sqlite":
        engine = make_engine("sqlite:///" + (tmp_path / "features.db").as_posix())
    else:
        url = os.environ.get("DEE_TEST_DB_URL", "").strip()
        if not url:
            pytest.skip("Disposable PostgreSQL DEE_TEST_DB_URL not configured")
        schema = "r1_feature_" + uuid.uuid4().hex
        bootstrap = create_engine(url)
        with bootstrap.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={
            "options": f"-csearch_path={schema} -ctimezone={request.param}",
        })
    try:
        Base.metadata.create_all(engine)
        factory = make_session_factory(engine)
        with factory() as session:
            session.add_all([CandidateRow(id="a"), CandidateRow(id="b")])
            session.commit()
        yield FeatureStore(factory), CandidateStore(factory)
    finally:
        engine.dispose()
        if bootstrap is not None:
            with bootstrap.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            bootstrap.dispose()


T = datetime(2026, 6, 1, 0, 0, 0, 123456, tzinfo=timezone.utc)
OFFSET = timezone(timedelta(hours=5, minutes=30))


def _vector(candidate, cut, materialized_at):
    return MaterializedVector(
        vector=FeatureVector(candidate_id=candidate, as_of=cut, view_name="test",
                             view_version=1, values={}, missing=()),
        consent_state={"allowed": False}, materialized_at=materialized_at,
    )


def test_equivalent_instants_roundtrip_and_upsert_one_cut(feature_database):
    fs, _ = feature_database
    written = T + timedelta(minutes=3)
    row_ids = []
    # Naive inputs retain the existing UTC convention; offsets are instants,
    # not wall-clock keys. Microseconds must also survive persistence.
    for cut, at in [(T, written), (T.astimezone(OFFSET), written.astimezone(OFFSET)),
                    (T.replace(tzinfo=None), written.replace(tzinfo=None))]:
        row_ids.append(fs.upsert_vector(_vector("a", cut, at)))
        got = fs.get_vector("a", view_name="test", view_version=1, as_of=cut)
        assert got is not None
        assert got.vector.as_of == T
        assert got.materialized_at == written
        assert got.consent_state == {"allowed": False}
    assert len(set(row_ids)) == 1
    assert len(fs.vectors_for_view("test", 1)) == 1
    # Reusing a returned timestamp must address the same persisted row.
    latest = fs.latest_as_of("test", 1)
    assert latest == T
    assert len(fs.vectors_for_view("test", 1, as_of=latest)) == 1


def test_partial_refresh_historical_cut_and_erasure(feature_database):
    fs, cs = feature_database
    later = T + timedelta(hours=1)
    future = later + timedelta(hours=1)
    for cid, cut in [("a", T), ("b", T), ("b", later), ("a", future)]:
        fs.upsert_vector(_vector(cid, cut, cut))
    assert fs.latest_as_of("test", 1) == future
    for cutoff in (later, later.astimezone(OFFSET), later.replace(tzinfo=None)):
        pool = fs.latest_vectors_for_view("test", 1, as_of=cutoff)
        assert {m.vector.candidate_id: m.vector.as_of for m in pool} == {"a": T, "b": later}
        exact = fs.vectors_for_view("test", 1, as_of=cutoff)
        assert [(m.vector.candidate_id, m.vector.as_of) for m in exact] == [("b", later)]
    assert fs.latest_vectors_for_view("test", 1, as_of=T - timedelta(microseconds=1)) == []
    assert cs.delete_candidate("a")
    assert {m.vector.candidate_id for m in fs.vectors_for_view("test", 1)} == {"b"}
    assert fs.latest_as_of("test", 1) == later
