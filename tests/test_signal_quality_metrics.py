import pytest

from app.signal_quality.metrics import (
    DegenerateClass,
    auc,
    average_ranks,
    brier,
    calibration_curve,
    lift_by_band,
)


def test_average_ranks_are_1_based_and_average_ties():
    assert average_ranks([0.1, 0.2, 0.3]) == [1.0, 2.0, 3.0]
    # Two values tied for ranks 1 and 2 -> both get 1.5.
    assert average_ranks([0.5, 0.5]) == [1.5, 1.5]
    # Three-way tie across ranks 2,3,4 -> all get 3.0.
    assert average_ranks([0.1, 0.7, 0.7, 0.7]) == [1.0, 3.0, 3.0, 3.0]


def test_auc_perfect_separation_is_one():
    """Hand-computable: ranks 1,2,3,4; positives hold 3+4=7.
    (7 - 2*3/2) / (2*2) = 4/4 = 1.0"""
    assert auc([0.1, 0.2, 0.3, 0.4], [False, False, True, True]) == 1.0


def test_auc_perfect_inversion_is_zero():
    assert auc([0.1, 0.2, 0.3, 0.4], [True, True, False, False]) == 0.0


def test_auc_all_tied_is_one_half():
    """THE TIE POLICY, PINNED. Every score identical means the signal
    separates nothing, and averaged ranks are what make that come out at
    exactly 0.5. A sort-based implementation returns 0.0 or 1.0 here
    depending on sort stability -- silently, and only on real data."""
    assert auc([0.5, 0.5, 0.5, 0.5], [True, False, True, False]) == 0.5
    assert auc([0.5, 0.5], [True, False]) == 0.5


def test_auc_partial_tie_hand_computed():
    """scores 0.2, 0.4, 0.4, 0.9  labels F, T, F, T
    ranks: 1, 2.5, 2.5, 4  -> positives hold 2.5 + 4 = 6.5
    (6.5 - 2*3/2) / (2*2) = 3.5/4 = 0.875"""
    assert auc([0.2, 0.4, 0.4, 0.9], [False, True, False, True]) == 0.875


def test_auc_refuses_a_degenerate_class():
    """AUC is UNDEFINED with one class present. Libraries variously return
    0.5, nan, or raise -- and 0.5 reads as 'no signal' when the truth is
    'no measurement'."""
    with pytest.raises(DegenerateClass):
        auc([0.1, 0.2, 0.3], [True, True, True])
    with pytest.raises(DegenerateClass):
        auc([0.1, 0.2, 0.3], [False, False, False])


def test_auc_refuses_mismatched_lengths():
    with pytest.raises(ValueError):
        auc([0.1, 0.2], [True])


def test_brier_is_mean_squared_error():
    assert brier([0.0, 1.0], [False, True]) == 0.0
    assert brier([1.0, 0.0], [False, True]) == 1.0
    assert brier([0.5, 0.5], [False, True]) == 0.25
    # (0.2-0)^2 + (0.6-1)^2 = 0.04 + 0.16 = 0.20, over 2 -> 0.10
    assert brier([0.2, 0.6], [False, True]) == pytest.approx(0.10)


def test_brier_refuses_mismatched_lengths():
    with pytest.raises(ValueError):
        brier([0.1], [True, False])


def test_calibration_curve_bins_are_half_open_and_carry_n():
    # 4 bins of width 0.25. Scores 0.1 | 0.3 | 0.6, 0.7 | (none)
    curve = calibration_curve(
        [0.1, 0.3, 0.6, 0.7], [False, True, True, True], bins=4
    )
    assert len(curve) == 4
    assert [b[2] for b in curve] == [1, 1, 2, 0]
    assert curve[0][:2] == (0.0, 0.25)
    # bin 2 holds 0.6 and 0.7 -> mean predicted 0.65, both positive -> 1.0
    assert curve[2][3] == pytest.approx(0.65)
    assert curve[2][4] == pytest.approx(1.0)


def test_an_empty_bin_reports_none_not_zero():
    """An empty bin is NOT a bin whose observed rate is 0. Reporting 0.0
    would draw a point on a reliability chart where no data exists."""
    curve = calibration_curve([0.1], [True], bins=4)
    assert curve[3][2] == 0
    assert curve[3][3] is None
    assert curve[3][4] is None


def test_score_of_exactly_one_lands_in_the_last_bin():
    """Half-open bins would drop 1.0 entirely, and a silently discarded
    sample is worse than a wrong one."""
    curve = calibration_curve([1.0], [True], bins=4)
    assert [b[2] for b in curve] == [0, 0, 0, 1]


def test_lift_is_band_rate_over_base_rate():
    """4 samples, 2 positive -> base rate 0.5.
    'high': 2 samples both positive -> rate 1.0, lift 2.0
    'low':  2 samples none positive -> rate 0.0, lift 0.0"""
    rows = lift_by_band(
        ["high", "high", "low", "low"], [True, True, False, False]
    )
    assert rows == [("high", 2, 1.0, 2.0), ("low", 2, 0.0, 0.0)]


def test_bands_are_ordered_by_name_for_stable_output():
    rows = lift_by_band(["z", "a"], [True, False])
    assert [r[0] for r in rows] == ["a", "z"]


def test_lift_is_none_when_the_base_rate_is_zero():
    """Division by zero has no useful answer here, and 0.0 would read as
    'this band underperforms' when nothing was positive anywhere."""
    rows = lift_by_band(["a", "b"], [False, False])
    assert [r[3] for r in rows] == [None, None]
    assert [r[2] for r in rows] == [0.0, 0.0]


def test_lift_refuses_mismatched_lengths():
    with pytest.raises(ValueError):
        lift_by_band(["a"], [True, False])
