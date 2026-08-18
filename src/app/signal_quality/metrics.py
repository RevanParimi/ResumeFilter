"""Pure metric functions (S9.1).

THIS MODULE IMPORTS NOTHING FROM ``app/``. That is deliberate: the numbers here
are the sprint's entire deliverable, so every one of them is asserted against a
fixture computed by hand, and a unit test of this module is a unit test in the
strict sense.

No numpy, no scipy, no scikit-learn -- and not merely to avoid a dependency.
AUC's TIE POLICY is the reason. Resume signals tie constantly (every ``*_band``
ties by construction), and a library that picks a tie rule silently produces a
number that looks computed and is arbitrary. Averaged ranks are written out
below so the rule is readable and testable.
"""

from __future__ import annotations

from typing import Optional, Sequence


class DegenerateClass(ValueError):
    """Raised when one class is absent, which makes AUC undefined.

    Deliberately an exception and not a sentinel return: 0.5 is a real AUC
    value meaning "separates nothing", and returning it here would conflate a
    measured null result with an impossible measurement.
    """


def average_ranks(values: Sequence[float]) -> list[float]:
    """1-based ranks, ties sharing their mean rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def auc(scores: Sequence[float], labels: Sequence[bool]) -> float:
    """Area under the ROC curve, via the Mann-Whitney U identity.

    AUC = (sum of positive ranks - n_pos*(n_pos+1)/2) / (n_pos * n_neg)
    """
    if len(scores) != len(labels):
        raise ValueError(f"length mismatch: {len(scores)} scores, {len(labels)} labels")
    n_pos = sum(1 for x in labels if x)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise DegenerateClass(
            f"AUC undefined: {n_pos} positive and {n_neg} negative labels"
        )
    ranks = average_ranks(scores)
    rank_sum = sum(r for r, lab in zip(ranks, labels) if lab)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def brier(scores: Sequence[float], labels: Sequence[bool]) -> float:
    """Mean squared error against the 0/1 label. Lower is better.

    Only meaningful for a score already constrained to [0,1] -- which every
    signal routed here is, by its own ``Field(ge=0.0, le=1.0)``. An unbounded
    count has no Brier score, and ``signals.py`` is what stops one being asked
    for.
    """
    if len(scores) != len(labels):
        raise ValueError(f"length mismatch: {len(scores)} scores, {len(labels)} labels")
    if not scores:
        raise ValueError("brier requires at least one observation")
    return sum((s - (1.0 if lab else 0.0)) ** 2 for s, lab in zip(scores, labels)) / len(scores)


def calibration_curve(
    scores: Sequence[float], labels: Sequence[bool], *, bins: int = 10
) -> list[tuple[float, float, int, Optional[float], Optional[float]]]:
    """Reliability curve over fixed-width bins.

    Returns ``(lower, upper, n, mean_predicted, observed_rate)`` per bin --
    plain tuples, because this module imports nothing from ``app/``, including
    our own schema. The service maps these onto ``CalibrationBin``.

    AN EMPTY BIN REPORTS ``None``, NOT ``0.0``. Zero is a real observed rate
    meaning "none of these were positive"; an empty bin means "nothing was
    predicted here". Collapsing them draws a point on a chart where no data
    exists. No smoothing and no interpolation for the same reason.
    """
    if len(scores) != len(labels):
        raise ValueError(f"length mismatch: {len(scores)} scores, {len(labels)} labels")
    if bins < 1:
        raise ValueError("bins must be >= 1")

    width = 1.0 / bins
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for s, lab in zip(scores, labels):
        idx = int(s / width)
        # A score of exactly 1.0 computes to idx == bins. Half-open bins would
        # drop it, and a silently discarded sample is worse than a wrong one.
        idx = min(max(idx, 0), bins - 1)
        buckets[idx].append((s, lab))

    out: list[tuple[float, float, int, Optional[float], Optional[float]]] = []
    for i, bucket in enumerate(buckets):
        lower, upper = i * width, (i + 1) * width
        if not bucket:
            out.append((lower, upper, 0, None, None))
            continue
        mean_pred = sum(s for s, _ in bucket) / len(bucket)
        observed = sum(1 for _, lab in bucket if lab) / len(bucket)
        out.append((lower, upper, len(bucket), mean_pred, observed))
    return out


def lift_by_band(
    bands: Sequence[str], labels: Sequence[bool]
) -> list[tuple[str, int, float, Optional[float]]]:
    """Positive rate per band against the overall base rate.

    Returns ``(band, n, positive_rate, lift)`` ordered by band NAME, not by
    rate: a stable order is what makes two runs diffable, and the natural
    ordinal order of a band enum is not knowable here (this module imports
    nothing from ``app/``).

    ``lift`` is ``None`` when the base rate is 0 -- returning 0.0 would read as
    "this band underperforms" when the truth is that nothing was positive
    anywhere.
    """
    if len(bands) != len(labels):
        raise ValueError(f"length mismatch: {len(bands)} bands, {len(labels)} labels")
    if not bands:
        raise ValueError("lift_by_band requires at least one observation")

    base = sum(1 for x in labels if x) / len(labels)
    grouped: dict[str, list[bool]] = {}
    for band, lab in zip(bands, labels):
        grouped.setdefault(band, []).append(lab)

    out: list[tuple[str, int, float, Optional[float]]] = []
    for band in sorted(grouped):
        members = grouped[band]
        rate = sum(1 for x in members if x) / len(members)
        out.append((band, len(members), rate, (rate / base) if base > 0 else None))
    return out
