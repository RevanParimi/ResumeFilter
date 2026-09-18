from datetime import datetime, timezone

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate
from app.features.store import FeatureStore
from app.ledger.store import LedgerStore
from app.reports.store import SqlReportStore
from tests.conftest import make_candidate_store, set_extraction_created_at

RESUME = "Jane Rao\nML Engineer\nSkills: Python, SQL\nEmail: jane@example.com\n"
T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _settings():
    return Settings(_env_file=None, openrouter_api_key="")


def _make_mv(cs, ls, rs):
    reg = get_feature_registry()
    view = default_view(reg, settings=_settings())
    cid = cs.ingest(ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
                    resume_text=RESUME).candidate_id
    set_extraction_created_at(cs, cid, datetime(2026, 1, 1, tzinfo=timezone.utc))
    mv = materialize_candidate(cid, view=view, registry=reg, as_of=T,
                               candidate_store=cs, report_store=rs, ledger_store=ls)
    return cid, view, mv


def test_upsert_and_get_roundtrip():
    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), SqlReportStore(cs._session_factory)
    fs = FeatureStore(cs._session_factory)
    cid, view, mv = _make_mv(cs, ls, rs)
    fs.upsert_vector(mv)
    got = fs.get_vector(cid, view_name=view.name, view_version=view.version, as_of=T)
    assert got is not None
    assert got.vector.values == mv.vector.values
    assert got.consent_state["allowed"] is False


def test_upsert_is_idempotent_on_same_cut():
    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), SqlReportStore(cs._session_factory)
    fs = FeatureStore(cs._session_factory)
    cid, view, mv = _make_mv(cs, ls, rs)
    fs.upsert_vector(mv)
    fs.upsert_vector(mv)
    assert len(fs.vectors_for_view(view.name, view.version)) == 1


def test_delete_candidate_cascades_vectors():
    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), SqlReportStore(cs._session_factory)
    fs = FeatureStore(cs._session_factory)
    cid, view, mv = _make_mv(cs, ls, rs)
    fs.upsert_vector(mv)
    cs.delete_candidate(cid)
    assert fs.get_vector(cid, view_name=view.name, view_version=view.version, as_of=T) is None


def test_latest_as_of_returns_newest_cut_or_none():
    from datetime import timedelta
    from app.features.materialize import MaterializedVector
    from app.features.schema import FeatureVector

    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), SqlReportStore(cs._session_factory)
    fs = FeatureStore(cs._session_factory)
    cid, view, _ = _make_mv(cs, ls, rs)  # persists a candidate row (FK satisfied)
    assert fs.latest_as_of(view.name, view.version) is None

    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = t1 + timedelta(days=30)
    for t in (t1, t2):
        fs.upsert_vector(MaterializedVector(
            vector=FeatureVector(candidate_id=cid, as_of=t, view_name=view.name,
                                 view_version=view.version, values={}, missing=()),
            consent_state={"allowed": True}, materialized_at=t))
    assert fs.latest_as_of(view.name, view.version) == t2


def test_latest_pool_keeps_partial_refresh_and_respects_historical_cut():
    from datetime import timedelta
    from app.features.materialize import MaterializedVector
    from app.features.schema import FeatureVector

    cs = make_candidate_store()
    fs = FeatureStore(cs._session_factory)
    ids = [cs.ingest(ExtractionResult(profile=heuristic_profile(text), method="heuristic"),
                     resume_text=text).candidate_id for text in (RESUME, "Another person")]
    later = T + timedelta(days=1)
    future = later + timedelta(days=1)
    for cid, at, name, version in [
        (ids[0], T, "test", 1), (ids[1], T, "test", 1),
        (ids[1], later, "test", 1), (ids[0], future, "test", 1),
        (ids[0], later, "other", 1), (ids[0], later, "test", 2),
    ]:
        fs.upsert_vector(MaterializedVector(vector=FeatureVector(
            candidate_id=cid, as_of=at, view_name=name, view_version=version,
            values={}, missing=()), consent_state={}, materialized_at=at))
    pool = fs.latest_vectors_for_view("test", 1, as_of=later)
    assert {m.vector.candidate_id: m.vector.as_of for m in pool} == {ids[0]: T, ids[1]: later}
    assert len(fs.latest_vectors_for_view("test", 1, as_of=T)) == 2
    assert fs.latest_vectors_for_view("test", 1, as_of=T - timedelta(seconds=1)) == []
    assert len(fs.vectors_for_view("test", 1, as_of=later)) == 1  # exact-cut export unchanged


def test_default_materialization_batch_uses_one_snapshot_time(services):
    from app.features.materialize import materialize_all

    ids = [services.candidates.ingest(
        ExtractionResult(profile=heuristic_profile(text), method="heuristic"),
        resume_text=text).candidate_id for text in (RESUME, "Another person")]
    registry = get_feature_registry()
    result = materialize_all(ids, view=default_view(registry, settings=services.settings),
                             registry=registry, candidate_store=services.candidates,
                             report_store=services.report_store, ledger_store=services.ledger)
    assert len(result) == 2
    assert len({m.vector.as_of for m in result}) == 1
