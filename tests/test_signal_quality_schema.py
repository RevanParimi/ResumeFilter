import pytest
from pydantic import ValidationError

from app.signal_quality.schema import (
    LabelKind,
    MetricKind,
    RefusalReason,
    SignalMeasured,
    SignalRefused,
)


def test_a_refusal_cannot_carry_a_metric():
    """The whole point of two types instead of one optional-field type."""
    refused = SignalRefused(
        signal="fabrication_risk.score",
        reason=RefusalReason.INSUFFICIENT_SAMPLES,
        n=3,
        detail="3 usable labels, need 30",
    )
    assert refused.sufficient is False
    assert not hasattr(refused, "auc")
    with pytest.raises(ValidationError):
        SignalRefused(
            signal="x", reason=RefusalReason.DEGENERATE_CLASS, n=0,
            detail="", auc=0.9,
        )


def test_measured_carries_n_and_positives():
    m = SignalMeasured(signal="fabrication_risk.score", n=40, positives=12, auc=0.71)
    assert m.sufficient is True
    assert (m.n, m.positives) == (40, 12)
    assert m.brier is None


def test_results_are_frozen():
    m = SignalMeasured(signal="s", n=1, positives=1)
    with pytest.raises(ValidationError):
        m.auc = 0.5


def test_label_kinds_are_distinct():
    assert LabelKind.FRAUD != LabelKind.HIRE
    assert set(MetricKind) == {MetricKind.AUC, MetricKind.BRIER, MetricKind.LIFT}
    assert RefusalReason.LABEL_KIND_MISMATCH.value == "label_kind_mismatch"
