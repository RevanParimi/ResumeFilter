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
