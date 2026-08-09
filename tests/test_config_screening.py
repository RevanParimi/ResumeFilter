"""S8.4 Phase B knobs. The values are bounds on cost and blast radius, so the
floors matter: a zero-item process call would spin, and an unbounded batch is a
denial-of-service against a synchronous pipeline."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _s(**kw) -> Settings:
    return Settings(_env_file=None, openrouter_api_key="", **kw)


def test_screening_defaults():
    s = _s()
    assert s.screening_max_batch_items == 500
    assert s.screening_max_items_per_call == 5
    assert s.screening_claim_timeout_seconds == 900
    assert s.ret_batch_item_days == 90
    assert s.page_default_limit == 50
    assert s.page_max_limit == 200
    assert s.materialize_max_candidates == 1000


def test_page_default_never_exceeds_page_max():
    """A default above the cap would make the UNPARAMETERIZED call the one that
    gets refused -- the shape nobody tests."""
    s = _s()
    assert s.page_default_limit <= s.page_max_limit


@pytest.mark.parametrize(
    "kw",
    [
        {"screening_max_batch_items": 0},
        {"screening_max_items_per_call": 0},
        {"screening_claim_timeout_seconds": 0},
        {"ret_batch_item_days": 0},
        {"page_default_limit": 0},
        {"page_max_limit": 0},
        {"materialize_max_candidates": 0},
    ],
)
def test_floors_are_enforced(kw):
    with pytest.raises(ValidationError):
        _s(**kw)


def test_config_yaml_matches_the_code_defaults():
    """The hermetic test Settings bypasses config.yaml, so a drift between the
    two means the suite proves one number and the deploy runs another."""
    import yaml

    raw = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    s = _s()
    for key in (
        "screening_max_batch_items", "screening_max_items_per_call",
        "screening_claim_timeout_seconds", "ret_batch_item_days",
        "page_default_limit", "page_max_limit", "materialize_max_candidates",
    ):
        assert raw[key] == getattr(s, key), f"{key} drifted between config.yaml and Settings"
