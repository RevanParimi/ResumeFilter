from app.core.config import Settings


def _settings() -> Settings:
    return Settings(_env_file=None, openrouter_api_key="")


def test_match_knob_defaults():
    s = _settings()
    assert s.match_default_limit == 25
    assert s.match_skill_weight == 3.0
    assert s.match_years_weight == 1.0
    assert s.match_degree_weight == 1.0
    assert s.match_notice_weight == 1.0
    assert s.match_location_weight == 1.0
    assert s.match_nice_to_have_fraction == 0.3


def test_match_nice_fraction_bounded():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None, openrouter_api_key="", match_nice_to_have_fraction=1.5)
