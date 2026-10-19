from datetime import datetime, timezone

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.materialize import MaterializedVector, materialize_candidate
from app.features.serving import current_consent_vectors
from app.features.store import FeatureStore
from app.ledger.schema import ConsentPurpose
from app.ledger.store import LedgerStore
from app.reports.store import SqlReportStore
from tests.conftest import make_candidate_store, set_extraction_created_at

RESUME = "Jane Rao\nSenior ML Engineer\nSkills: Python, Spark, SQL\nEmail: jane@example.com\n"
T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _settings():
    return Settings(_env_file=None, openrouter_api_key="")


def _setup():
    cs = make_candidate_store()
    ls = LedgerStore(cs._session_factory)
    rs = SqlReportStore(cs._session_factory)
    cid = cs.ingest(ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
                    resume_text=RESUME).candidate_id
    set_extraction_created_at(cs, cid, datetime(2026, 1, 1, tzinfo=timezone.utc))
    return cs, ls, rs, cid


def _view_reg():
    reg = get_feature_registry()
    return reg, default_view(reg, settings=_settings())


def test_absent_candidate_returns_none():
    cs, ls, rs, cid = _setup()
    reg, view = _view_reg()
    assert materialize_candidate("nope", view=view, registry=reg, as_of=T,
                                 candidate_store=cs, report_store=rs, ledger_store=ls) is None


def test_masks_consent_features_when_withheld():
    cs, ls, rs, cid = _setup()
    reg, view = _view_reg()
    mv = materialize_candidate(cid, view=view, registry=reg, as_of=T,
                               candidate_store=cs, report_store=rs, ledger_store=ls)
    assert isinstance(mv, MaterializedVector)
    assert mv.consent_state["allowed"] is False
    assert mv.vector.values["ledger.interview_record_count"] is None
    assert mv.vector.values["reputation.band"] is None
    assert "ledger.interview_record_count" in mv.vector.missing
    assert mv.vector.values["candidate.num_skills"] is not None  # first-party intact


def test_keeps_consent_features_when_granted():
    cs, ls, rs, cid = _setup()
    reg, view = _view_reg()
    org = ls.create_organization("Org A")
    ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ, org_id=org.id,
                     now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    mv = materialize_candidate(cid, view=view, registry=reg, as_of=T,
                               candidate_store=cs, report_store=rs, ledger_store=ls)
    assert mv.consent_state["allowed"] is True and mv.consent_state["consent_id"]
    assert mv.vector.values["ledger.interview_record_count"] == 0   # present, not masked
    assert mv.vector.values["reputation.band"] == "insufficient_data"


def test_current_serving_does_not_rewrite_historical_materialization(monkeypatch):
    cs, ls, rs, cid = _setup()
    reg, view = _view_reg()
    org = ls.create_organization("History")
    grant = ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ,
                            org_id=org.id, now=T, expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc))
    mv = materialize_candidate(cid, view=view, registry=reg, as_of=T,
                               candidate_store=cs, report_store=rs, ledger_store=ls)
    store = FeatureStore(cs._session_factory)
    store.upsert_vector(mv)
    current = datetime(2026, 7, 1, tzinfo=timezone.utc)
    ls.revoke_consent(grant.id, now=current)
    monkeypatch.setattr("app.features.serving._utcnow", lambda: current)
    raw = store.get_vector(cid, view_name=view.name, view_version=view.version, as_of=T)
    served = current_consent_vectors([raw.vector], registry=reg, ledger_store=ls, org_id=org.id)[0]
    assert served.values["reputation.band"] is None
    assert served.values["candidate.num_skills"] == raw.vector.values["candidate.num_skills"]
    assert served.as_of == T and served.candidate_id == cid
    # In-memory and persisted historical evidence retain the original permission.
    assert raw.vector.values["reputation.band"] == "insufficient_data"
    assert store.get_vector(cid, view_name=view.name, view_version=view.version, as_of=T) == mv
    historical = materialize_candidate(cid, view=view, registry=reg, as_of=T,
                                        candidate_store=cs, report_store=rs, ledger_store=ls)
    assert historical.consent_state["allowed"] is True
    assert historical.vector == mv.vector


def test_current_grant_does_not_fill_historically_withheld_values(monkeypatch):
    cs, ls, rs, cid = _setup()
    reg, view = _view_reg()
    mv = materialize_candidate(cid, view=view, registry=reg, as_of=T,
                               candidate_store=cs, report_store=rs, ledger_store=ls)
    current = datetime(2026, 7, 1, tzinfo=timezone.utc)
    ls.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ,
                     now=current, expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr("app.features.serving._utcnow", lambda: current)
    served = current_consent_vectors([mv.vector], registry=reg, ledger_store=ls)[0]
    assert served.values["reputation.band"] is None
    assert "reputation.band" in served.missing
    assert served.values["candidate.num_skills"] is not None
