import csv
import importlib.util
from datetime import datetime, timezone

import pytest

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.core.config import Settings
from app.features import default_view, get_feature_registry
from app.features.export import ParquetUnavailable, export_view_csv, export_view_parquet
from app.features.materialize import materialize_candidate
from app.ledger.store import LedgerStore
from app.services.report_store import InMemoryReportStore
from tests.conftest import make_candidate_store, set_extraction_created_at

RESUME = "Jane Rao\nML Engineer\nSkills: Python, SQL\nEmail: jane@example.com\n"
T = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _settings():
    return Settings(_env_file=None, openrouter_api_key="")


def _mv():
    cs = make_candidate_store()
    ls, rs = LedgerStore(cs._session_factory), InMemoryReportStore()
    reg = get_feature_registry()
    view = default_view(reg, settings=_settings())
    cid = cs.ingest(ExtractionResult(profile=heuristic_profile(RESUME), method="heuristic"),
                    resume_text=RESUME).candidate_id
    set_extraction_created_at(cs, cid, datetime(2026, 1, 1, tzinfo=timezone.utc))
    mv = materialize_candidate(cid, view=view, registry=reg, as_of=T,
                               candidate_store=cs, report_store=rs, ledger_store=ls)
    return reg, view, mv, cid


def test_csv_header_is_wide_and_in_view_order(tmp_path):
    reg, view, mv, cid = _mv()
    path = tmp_path / "features.csv"
    export_view_csv([mv], view=view, path=str(path))
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    assert header[:4] == ["candidate_id", "as_of", "view_name", "view_version"]
    assert header[4:] == [name for name, _ in view.members]
    assert len(rows) == 2  # header + one data row


def test_csv_masks_consent_cell_and_keeps_first_party(tmp_path):
    reg, view, mv, cid = _mv()
    path = tmp_path / "features.csv"
    export_view_csv([mv], view=view, path=str(path))
    with open(path, newline="", encoding="utf-8") as f:
        header, row = list(csv.reader(f))
    col = {name: row[i] for i, name in enumerate(header)}
    assert col["candidate_id"] == cid
    assert col["ledger.interview_record_count"] == ""      # consent-withheld -> empty
    assert col["candidate.num_skills"] != ""               # first-party present


def test_parquet_guarded(tmp_path):
    reg, view, mv, cid = _mv()
    path = tmp_path / "features.parquet"
    if importlib.util.find_spec("pyarrow") is None:
        with pytest.raises(ParquetUnavailable):
            export_view_parquet([mv], view=view, registry=reg, path=str(path))
    else:
        export_view_parquet([mv], view=view, registry=reg, path=str(path))
        assert path.exists()
