"""Report store — durable reports + outcome records (FR-6..FR-8, NFR-4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.report import Report
from app.services.report_store import (
    InMemoryReportStore,
    OutcomeLabel,
    OutcomeRecord,
    SqliteReportStore,
    build_report_store,
)


def _report(**overrides) -> Report:
    from app.schemas.report import CoherenceVerdict

    base = Report(
        domain="genai",
        verdicts=[
            CoherenceVerdict(
                claim_id="clm_1",
                claim_text="Fine-tuned Llama 3 on 40k examples",
                claim_type="fine_tuning",
            )
        ],
        summary="test report",
    )
    return base.model_copy(update=overrides)


@pytest.fixture(params=["sqlite", "memory"])
def store(request, tmp_path: Path):
    if request.param == "sqlite":
        return SqliteReportStore(path=str(tmp_path / "reports.db"))
    return InMemoryReportStore()


def test_save_get_roundtrip(store):
    rep = _report()
    store.save(rep)
    got = store.get(rep.id)
    assert got is not None
    assert got.id == rep.id
    assert got.verdicts[0].claim_text == rep.verdicts[0].claim_text
    assert got.human_review_required is True


def test_get_missing_returns_none(store):
    assert store.get("rep_missing") is None


def test_sqlite_survives_restart(tmp_path: Path):
    path = str(tmp_path / "reports.db")
    rep = _report()
    SqliteReportStore(path=path).save(rep)
    # New instance, same file — simulates a process restart.
    got = SqliteReportStore(path=path).get(rep.id)
    assert got is not None and got.id == rep.id


def test_outcome_roundtrip(store):
    rep = _report()
    store.save(rep)
    store.add_outcome(
        OutcomeRecord(
            report_id=rep.id,
            claim_id="clm_1",
            outcome=OutcomeLabel.VERIFIED_GENUINE,
            notes="confirmed in screen",
        )
    )
    store.add_outcome(
        OutcomeRecord(report_id=rep.id, outcome=OutcomeLabel.INCONCLUSIVE)
    )
    outs = store.outcomes(rep.id)
    assert len(outs) == 2
    assert outs[0].claim_id == "clm_1"
    assert outs[0].outcome == OutcomeLabel.VERIFIED_GENUINE
    assert outs[1].claim_id is None
    assert store.outcomes("rep_other") == []


def test_delete_removes_report_and_outcomes(store):
    rep = _report()
    store.save(rep)
    store.add_outcome(OutcomeRecord(report_id=rep.id, outcome=OutcomeLabel.INCONCLUSIVE))
    assert store.delete(rep.id) is True
    assert store.get(rep.id) is None
    assert store.outcomes(rep.id) == []
    assert store.delete(rep.id) is False


def test_build_report_store_uses_settings_path(settings, tmp_path: Path, monkeypatch):
    s = settings.model_copy(update={"report_db_path": str(tmp_path / "r.db")})
    store = build_report_store(s)
    assert isinstance(store, SqliteReportStore)
    rep = _report()
    store.save(rep)
    assert (tmp_path / "r.db").exists()
