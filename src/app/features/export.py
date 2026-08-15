"""Export materialized feature vectors to wide CSV / parquet (PI-4 / S4.2).

The 'wide' deliverable is a pivot: fixed columns then one column per feature in
view.members order. Values are already consent-masked at materialization, so an
exported file can never leak a consent-withheld value. CSV uses the stdlib;
parquet requires pyarrow (optional) and raises ParquetUnavailable if absent.
"""

from __future__ import annotations

import csv
from typing import Iterable

from app.features.materialize import MaterializedVector
from app.features.registry import FeatureRegistry
from app.features.schema import FeatureDType, FeatureVector, FeatureView
from app.features.training_schema import TrainingExample, TrainingLabel
from app.ledger.consent import as_utc

_FIXED = ("candidate_id", "as_of", "view_name", "view_version")


class ParquetUnavailable(RuntimeError):
    """pyarrow is not installed; parquet export is unavailable."""


def feature_columns(view: FeatureView) -> list[str]:
    """The per-feature column names in view.members order (no fixed columns)."""
    return [name for name, _ in view.members]


def _columns(view: FeatureView) -> list[str]:
    return list(_FIXED) + feature_columns(view)


def vector_cells(vector: FeatureVector, view: FeatureView, null_token) -> list:
    """Fixed + feature cells for one FeatureVector, in _columns order. Shared by
    the S4.2 feature export and the S4.4 training export."""
    fixed = {
        "candidate_id": vector.candidate_id,
        "as_of": as_utc(vector.as_of).isoformat(),
        "view_name": vector.view_name,
        "view_version": vector.view_version,
    }
    cells = []
    for col in _columns(view):
        if col in fixed:
            cells.append(fixed[col])
        else:
            val = vector.values.get(col)
            cells.append(null_token if val is None else val)
    return cells


def export_view_csv(
    rows: Iterable[MaterializedVector], *, view: FeatureView, path: str, null_token: str = ""
) -> None:
    columns = _columns(view)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for mv in rows:
            writer.writerow(vector_cells(mv.vector, view, null_token))


def _pa_type(pa, dtype: FeatureDType):
    if dtype is FeatureDType.NUMERIC:
        return pa.float64()
    if dtype is FeatureDType.INTEGER:
        return pa.int64()
    if dtype is FeatureDType.BOOLEAN:
        return pa.bool_()
    return pa.string()  # categorical / ordinal


def export_view_parquet(
    rows: Iterable[MaterializedVector], *, view: FeatureView, registry: FeatureRegistry, path: str
) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # optional dependency
        raise ParquetUnavailable(
            "parquet export needs pyarrow; install it (optional extra) or use export_view_csv"
        ) from exc

    rows = list(rows)
    columns = _columns(view)
    specs = {rf.spec.name: rf.spec for rf in view.resolve(registry)}
    data: dict[str, list] = {c: [] for c in columns}
    for mv in rows:
        for col, cell in zip(columns, vector_cells(mv.vector, view, None)):
            data[col].append(cell)

    arrays = {}
    for col in columns:
        if col == "view_version":
            arrays[col] = pa.array(data[col], type=pa.int64())
        elif col in ("candidate_id", "as_of", "view_name"):
            arrays[col] = pa.array(data[col], type=pa.string())
        else:
            arrays[col] = pa.array(data[col], type=_pa_type(pa, specs[col].dtype))
    pq.write_table(pa.table(arrays), path)


# -- S4.4 training export: wide feature pivot + appended label columns ---------

_LABEL_COLUMNS = (
    "label_hired", "label_outcome", "label_coding_best_percentile",
    "label_event_at", "label_lag_days", "label_observed", "label_withheld",
)


def _label_cells(label: TrainingLabel, null_token) -> list:
    def cell(v):
        return null_token if v is None else v

    ev = null_token if label.event_at is None else as_utc(label.event_at).isoformat()
    return [
        cell(label.hired),
        cell(label.outcome),
        cell(label.coding_best_percentile),
        ev,
        cell(label.lag_days),
        label.observed,
        label.withheld,
    ]


def export_training_csv(
    examples: Iterable[TrainingExample], *, view: FeatureView, path: str, null_token: str = ""
) -> None:
    columns = _columns(view) + list(_LABEL_COLUMNS)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for ex in examples:
            writer.writerow(
                vector_cells(ex.vector, view, null_token) + _label_cells(ex.label, null_token)
            )


def export_training_parquet(
    examples: Iterable[TrainingExample], *, view: FeatureView, registry: FeatureRegistry, path: str
) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # optional dependency
        raise ParquetUnavailable(
            "parquet export needs pyarrow; install it (optional extra) or use export_training_csv"
        ) from exc

    examples = list(examples)
    feat_cols = _columns(view)
    specs = {rf.spec.name: rf.spec for rf in view.resolve(registry)}

    fdata: dict[str, list] = {c: [] for c in feat_cols}
    ldata: dict[str, list] = {c: [] for c in _LABEL_COLUMNS}
    for ex in examples:
        for col, cell in zip(feat_cols, vector_cells(ex.vector, view, None)):
            fdata[col].append(cell)
        for col, cell in zip(_LABEL_COLUMNS, _label_cells(ex.label, None)):
            ldata[col].append(cell)

    arrays = {}
    for col in feat_cols:
        if col == "view_version":
            arrays[col] = pa.array(fdata[col], type=pa.int64())
        elif col in ("candidate_id", "as_of", "view_name"):
            arrays[col] = pa.array(fdata[col], type=pa.string())
        else:
            arrays[col] = pa.array(fdata[col], type=_pa_type(pa, specs[col].dtype))

    _label_arrow = {
        "label_hired": pa.bool_(), "label_outcome": pa.string(),
        "label_coding_best_percentile": pa.float64(), "label_event_at": pa.string(),
        "label_lag_days": pa.float64(), "label_observed": pa.bool_(), "label_withheld": pa.bool_(),
    }
    for col in _LABEL_COLUMNS:
        arrays[col] = pa.array(ldata[col], type=_label_arrow[col])

    ordered = feat_cols + list(_LABEL_COLUMNS)
    pq.write_table(pa.table({c: arrays[c] for c in ordered}), path)
