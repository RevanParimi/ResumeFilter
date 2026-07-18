"""S2.4 fusion math: component construction, fusion, banding — pure and offline."""

from app.fabrication.risk import build_components
from app.schemas.fabrication import (
    AIGenerationAssessment,
    AILikelihoodBand,
    ConsistencyBand,
    CrossFieldAssessment,
    DuplicationBand,
    ResumeFarmAssessment,
)


def _ai(band: AILikelihoodBand, conf: float = 0.75) -> AIGenerationAssessment:
    return AIGenerationAssessment(likelihood=0.6, confidence=conf, band=band)


def _xf(band: ConsistencyBand, conf: float = 0.75) -> CrossFieldAssessment:
    return CrossFieldAssessment(score=0.5, confidence=conf, band=band)


def _rf(band: DuplicationBand, conf: float = 0.70) -> ResumeFarmAssessment:
    return ResumeFarmAssessment(score=0.85, confidence=conf, band=band, corpus_size=3)


def test_settings_expose_fr_knobs(settings):
    assert settings.fr_moderate_threshold == 0.30
    assert settings.fr_elevated_threshold == 0.60
    assert settings.fr_min_confidence == 0.50
    assert settings.fr_weight_ai == 1.0
    assert settings.fr_weight_cross_field == 1.0
    assert settings.fr_weight_farm == 1.0


def test_one_component_per_evaluable_assessment(settings):
    comps = build_components(
        _ai(AILikelihoodBand.POSSIBLE), _xf(ConsistencyBand.CONSISTENT),
        _rf(DuplicationBand.NEAR_DUPLICATE), settings=settings,
    )
    assert [c.id for c in comps] == ["ai_generation", "cross_field", "resume_farm"]


def test_none_and_insufficient_are_excluded(settings):
    comps = build_components(
        None, _xf(ConsistencyBand.INSUFFICIENT_DATA),
        _rf(DuplicationBand.UNIQUE), settings=settings,
    )
    assert [c.id for c in comps] == ["resume_farm"]
    assert build_components(None, None, None, settings=settings) == []


def test_component_risk_band_mapping(settings):
    comps = build_components(
        _ai(AILikelihoodBand.LIKELY), _xf(ConsistencyBand.MINOR_ISSUES),
        _rf(DuplicationBand.NEAR_DUPLICATE), settings=settings,
    )
    by_id = {c.id: c for c in comps}
    assert by_id["ai_generation"].risk == 0.75
    assert by_id["cross_field"].risk == 0.40
    assert by_id["resume_farm"].risk == 0.80


def test_flagged_only_at_top_band(settings):
    comps = build_components(
        _ai(AILikelihoodBand.POSSIBLE), _xf(ConsistencyBand.MAJOR_ISSUES),
        _rf(DuplicationBand.SIMILAR), settings=settings,
    )
    by_id = {c.id: c for c in comps}
    assert by_id["ai_generation"].flagged is False
    assert by_id["cross_field"].flagged is True
    assert by_id["resume_farm"].flagged is False


def test_weight_is_config_weight_times_confidence(settings):
    comps = build_components(_ai(AILikelihoodBand.UNLIKELY, conf=0.8), None, None, settings=settings)
    assert comps[0].weight == 0.8  # fr_weight_ai (1.0) x confidence
    assert comps[0].band == "unlikely"
