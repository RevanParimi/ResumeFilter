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
from app.features.schema import FeatureDType, FeatureView
from app.ledger.consent import as_utc

_FIXED = ("candidate_id", "as_of", "view_name", "view_version")


class ParquetUnavailable(RuntimeError):
    """pyarrow is not installed; parquet export is unavailable."""


def _columns(view: FeatureView) -> list[str]:
    return list(_FIXED) + [name for name, _ in view.members]


def _row_cells(mv: MaterializedVector, view: FeatureView, null_token):
    v = mv.vector
    fixed = {
        "candidate_id": v.candidate_id,
        "as_of": as_utc(v.as_of).isoformat(),
        "view_name": v.view_name,
        "view_version": v.view_version,
    }
    cells = []
    for col in _columns(view):
        if col in fixed:
            cells.append(fixed[col])
        else:
            val = v.values.get(col)
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
            writer.writerow(_row_cells(mv, view, null_token))


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
        for col, cell in zip(columns, _row_cells(mv, view, None)):
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
