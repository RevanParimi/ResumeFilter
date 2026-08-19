"""Orchestration and the three refusals (S9.1, spec 5).

THE REFUSALS ARE THE SPRINT'S CENTRAL CLAIM. PI-9 was gated on real
organisations submitting outcomes, on the grounds that "a harness measuring
test fixtures would have been actively misleading". That is an argument against
a harness which emits a number no matter what it is fed -- so this one cannot.
Below the sample floor, on a one-class sample, or on a signal the label source
cannot score, the result is a ``SignalRefused`` carrying no metric fields at
all.

No boot refusal is added. The eight that exist guard configurations producing a
service that LOOKS healthy while being unsafe or unusable; this is advisory
analysis tooling, and refusing to start over a report nobody has asked for yet
would be a ninth that earns nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.signal_quality.labels import LabeledReport, LabelSource
from app.signal_quality.metrics import (
    auc, brier, calibration_curve, lift_by_band,
)
from app.signal_quality.schema import (
    BandLift, CalibrationBin, LabelKind, MetricKind, Population, RefusalReason,
    SignalMeasured, SignalQualityReport, SignalRefused, SignalResult,
)
from app.signal_quality.signals import SIGNALS, SignalSpec


def _measure_one(
    spec: SignalSpec, labeled: list[LabeledReport], *, min_samples: int,
    source_kind: LabelKind, bins: int,
) -> SignalResult:
    # REFUSAL 3 IS CHECKED FIRST, and the order is deliberate. A depth signal
    # on a fraud source is not "nearly measurable, just short of samples" --
    # it is not measurable at all, and reporting INSUFFICIENT_SAMPLES would
    # invite someone to go and collect more of a label that can never score it.
    if spec.kind is not source_kind:
        return SignalRefused(
            signal=spec.name, reason=RefusalReason.LABEL_KIND_MISMATCH, n=0,
            detail=(
                f"{spec.name} is scored by {spec.kind.value} labels; this run "
                f"used a {source_kind.value} source"
            ),
        )

    pairs = []
    for lr in labeled:
        value = spec.extract(lr.report)
        if value is None:
            continue  # never assessed -- not a zero, and not counted
        pairs.append((value, lr.positive))

    n = len(pairs)
    if n < min_samples:
        return SignalRefused(
            signal=spec.name, reason=RefusalReason.INSUFFICIENT_SAMPLES, n=n,
            detail=f"{n} usable labels, need {min_samples}",
        )

    labels = [p for _, p in pairs]
    positives = sum(1 for p in labels if p)
    if positives == 0 or positives == n:
        return SignalRefused(
            signal=spec.name, reason=RefusalReason.DEGENERATE_CLASS, n=n,
            detail=(
                f"all {n} labels are {'positive' if positives else 'negative'}; "
                "AUC is undefined and a lift baseline is meaningless"
            ),
        )

    if spec.band:
        return SignalMeasured(
            signal=spec.name, n=n, positives=positives,
            lift=tuple(
                BandLift(band=b, n=cnt, positive_rate=rate, lift=lift)
                for b, cnt, rate, lift in lift_by_band(
                    [str(v) for v, _ in pairs], labels
                )
            ),
        )

    values = [float(v) for v, _ in pairs]
    measured = {
        "signal": spec.name, "n": n, "positives": positives,
        "auc": auc(values, labels),
    }
    if MetricKind.BRIER in spec.metrics:
        measured["brier"] = brier(values, labels)
        measured["curve"] = tuple(
            CalibrationBin(
                lower=lo, upper=hi, n=cnt, mean_predicted=mp, observed_rate=obs
            )
            for lo, hi, cnt, mp, obs in calibration_curve(values, labels, bins=bins)
        )
    if MetricKind.LIFT in spec.metrics:
        measured["lift"] = tuple(
            BandLift(band=b, n=cnt, positive_rate=rate, lift=lift)
            for b, cnt, rate, lift in lift_by_band([str(v) for v in values], labels)
        )
    return SignalMeasured(**measured)


def measure(
    label_source: LabelSource, *, min_samples: int, bins: int = 10
) -> SignalQualityReport:
    """Measure every registered signal against one label source.

    Every signal in ``SIGNALS`` appears in the result exactly once, refused or
    measured. A report that quietly dropped a signal would read as "we measured
    everything" while measuring eleven things.
    """
    labeled = label_source.labeled()
    created = [lr.report.created_at for lr in labeled]

    return SignalQualityReport(
        generated_at=datetime.now(timezone.utc),
        population=Population(
            label_source=label_source.name,
            label_kind=label_source.kind,
            include_operator_labels=bool(
                getattr(label_source, "include_operator_labels", False)
            ),
            labels_usable=len(labeled),
            earliest_report=min(created) if created else None,
            latest_report=max(created) if created else None,
        ),
        signals=tuple(
            _measure_one(
                spec, labeled, min_samples=min_samples,
                source_kind=label_source.kind, bins=bins,
            )
            for spec in SIGNALS
        ),
    )
