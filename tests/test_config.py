"""Config knob presence + env-override sanity (S5.2 comp_* additions)."""

from app.core.config import Settings


def test_comp_defaults_present():
    s = Settings()
    assert s.comp_min_observations == 5
    assert s.comp_prior_strength == 8.0
    assert s.comp_confidence_floor == 0.30
    assert s.comp_confidence_cap == 0.90
    assert (s.comp_mid_years, s.comp_senior_years, s.comp_lead_years) == (2.0, 5.0, 9.0)
    assert s.comp_benchmark_tolerance == 0.10
    assert s.comp_currency_default == "INR"
    assert s.comp_bands_path is None


def test_comp_env_override(monkeypatch):
    monkeypatch.setenv("DEE_COMP_MIN_OBSERVATIONS", "3")
    assert Settings().comp_min_observations == 3
