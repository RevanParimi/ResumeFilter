from datetime import datetime, timezone

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.materialize import materialize_candidate
from app.features.store import FeatureStore
from app.ledger.store import LedgerStore
from app.services.report_store import InMemoryReportStore
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
    ls, rs = LedgerStore(cs._session_factory), InMemoryReportStore()
    fs = FeatureStore(cs._session_factory)
    cid, view, mv = _make_mv(cs, ls, rs)
    fs.upsert_vector(mv)
    got = fs.get_vector(cid, view_name=view.name, view_version=view.version, as_of=T)
    assert got is not None
    assert got.vector.values == mv.vector.values
    assert got.consent_state["allowed"] is False


def test_upsert_is_idempotent_on_same_cut():
    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), InMemoryReportStore()
    fs = FeatureStore(cs._session_factory)
    cid, view, mv = _make_mv(cs, ls, rs)
    fs.upsert_vector(mv)
    fs.upsert_vector(mv)
    assert len(fs.vectors_for_view(view.name, view.version)) == 1


def test_delete_candidate_cascades_vectors():
    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), InMemoryReportStore()
    fs = FeatureStore(cs._session_factory)
    cid, view, mv = _make_mv(cs, ls, rs)
    fs.upsert_vector(mv)
    cs.delete_candidate(cid)
    assert fs.get_vector(cid, view_name=view.name, view_version=view.version, as_of=T) is None
