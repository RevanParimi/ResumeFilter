"""The sweeper and the portal must name the same classes -- S8.3 spec §7.1."""

from app.candidates.models import ResumeRow
from app.core.config import Settings
from app.portal.retention import RETENTION_KNOBS
from app.retention.plan import (
    TARGETS, SweepMode, SweepTarget, data_classes, ttl_days,
)


def _settings():
    return Settings(_env_file=None, openrouter_api_key="")


def test_every_declared_window_has_a_sweep_target_and_vice_versa():
    """Set equality in BOTH directions. One direction leaves a promise nothing
    enforces; the other leaves a deletion nobody was told about."""
    assert data_classes() == set(RETENTION_KNOBS)


def test_every_target_names_a_real_settings_knob():
    s = _settings()
    for t in TARGETS:
        assert hasattr(s, t.knob), f"{t.data_class} names a knob that does not exist"
        assert ttl_days(t, s) >= 1


def test_every_target_names_a_real_column_on_its_model():
    for t in TARGETS:
        assert hasattr(t.model, t.timestamp_column), t.data_class
        if t.mode is SweepMode.CLEAR:
            assert t.clear_column and hasattr(t.model, t.clear_column), t.data_class
        else:
            assert t.clear_column is None, t.data_class


def test_a_target_naming_an_undeclared_class_cannot_even_be_ASKED_for_its_knob():
    """The plan called for a test that every target's knob matches the one its
    data class declares. `SweepTarget.knob` READS RETENTION_KNOBS, so that
    assertion cannot fail -- and a test that cannot fail is the shape this repo
    keeps catching in its own checks.

    What is worth pinning is the failure mode the derivation buys: a target for
    a class nobody declared raises rather than sweeping on some default.
    """
    import pytest

    orphan = SweepTarget("not_a_declared_class", ResumeRow, "created_at",
                         SweepMode.DELETE)
    with pytest.raises(KeyError):
        orphan.knob


def test_login_state_is_one_class_over_two_tables():
    """The reason the guard compares a SET and not a length."""
    tables = sorted(
        t.model.__tablename__ for t in TARGETS if t.data_class == "login_state"
    )
    assert tables == ["auth_sessions", "login_challenges"]


def test_batch_item_text_clears_and_never_deletes():
    """The org's record of what it screened outlives the text it screened --
    the same reasoning as batch_items.candidate_id being SET NULL."""
    t = next(t for t in TARGETS if t.data_class == "batch_item_text")
    assert t.mode is SweepMode.CLEAR
    assert t.clear_column == "raw_text"
