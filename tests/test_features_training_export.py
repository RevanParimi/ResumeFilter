import csv
import importlib.util
from datetime import datetime, timezone

import pytest

from app.features.schema import FeatureVector
from app.features.training_schema import TrainingExample, TrainingLabel
from app.features.export import (
    ParquetUnavailable, export_training_csv, export_training_parquet, feature_columns,
)
from app.features import default_view, get_feature_registry

T = datetime(2026, 6, 1, tzinfo=timezone.utc)
LABELS = ["label_hired", "label_outcome", "label_coding_best_percentile",
          "label_event_at", "label_lag_days", "label_observed", "label_withheld"]


def _example(cid, values, label):
    fv = FeatureVector(candidate_id=cid, as_of=T, view_name="core_v1", view_version=1,
                       values=values, missing=())
    return TrainingExample(vector=fv, label=label)


def _fixture():
    reg = get_feature_registry()
    view = default_view(reg)
    cols = feature_columns(view)
    labeled = _example("a", {c: None for c in cols},
                       TrainingLabel(hired=True, outcome="hired", coding_best_percentile=88.0,
                                     event_at=T, lag_days=30.0, observed=True))
    withheld = _example("c", {c: None for c in cols}, TrainingLabel(withheld=True))
    return reg, view, [labeled, withheld]


def test_training_csv_header_appends_label_columns(tmp_path):
    reg, view, examples = _fixture()
    path = tmp_path / "train.csv"
    export_training_csv(examples, view=view, path=str(path))
    with open(path, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header[:4] == ["candidate_id", "as_of", "view_name", "view_version"]
    assert header[4:4 + len(feature_columns(view))] == feature_columns(view)
    assert header[-7:] == LABELS


def test_training_csv_rows_render_label_values_and_nulls(tmp_path):
    reg, view, examples = _fixture()
    path = tmp_path / "train.csv"
    export_training_csv(examples, view=view, path=str(path))
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    a = next(r for r in rows if r["candidate_id"] == "a")
    assert a["label_hired"] == "True" and a["label_outcome"] == "hired"
    assert a["label_coding_best_percentile"] == "88.0" and a["label_observed"] == "True"
    c = next(r for r in rows if r["candidate_id"] == "c")
    assert c["label_withheld"] == "True" and c["label_hired"] == "" and c["label_outcome"] == ""


def test_training_parquet_guarded(tmp_path):
    reg, view, examples = _fixture()
    path = tmp_path / "train.parquet"
    if importlib.util.find_spec("pyarrow") is None:
        with pytest.raises(ParquetUnavailable):
            export_training_parquet(examples, view=view, registry=reg, path=str(path))
    else:
        export_training_parquet(examples, view=view, registry=reg, path=str(path))
        assert path.exists()
