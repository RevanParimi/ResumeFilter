import pytest

from app.signal_quality.metrics import DegenerateClass, auc, average_ranks


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
