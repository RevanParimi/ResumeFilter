"""S2.4 fusion math: component construction, fusion, banding — pure and offline."""

from app.fabrication.risk import build_components
from app.schemas.fabrication import (
    AIGenerationAssessment,
    AILikelihoodBand,
    ConsistencyBand,
    CrossFieldAssessment,
    DuplicationBand,
    ResumeFarmAssessment,
    RiskComponent,
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


from app.fabrication.risk import assess_fabrication_risk, band_for_risk, fuse_components
from app.schemas.fabrication import FabricationRiskBand


def test_fuse_empty_is_zero():
    assert fuse_components([]) == (0.0, 0.0)


def test_fuse_blends_weighted_mean_and_max(settings):
    comps = build_components(
        _ai(AILikelihoodBand.LIKELY, conf=0.8), _xf(ConsistencyBand.MAJOR_ISSUES, conf=0.8),
        _rf(DuplicationBand.NEAR_DUPLICATE, conf=0.8), settings=settings,
    )
    score, confidence = fuse_components(comps)
    # equal weights: mean = (0.75+0.75+0.80)/3; score = 0.7*mean + 0.3*0.80
    assert abs(score - (0.7 * (0.75 + 0.75 + 0.80) / 3 + 0.3 * 0.80)) < 1e-9
    assert confidence == 0.75  # min(0.9, 0.30 + 0.15*3)


def test_confidence_follows_coverage(settings):
    two = build_components(
        _ai(AILikelihoodBand.UNLIKELY), _xf(ConsistencyBand.CONSISTENT), None, settings=settings,
    )
    assert fuse_components(two)[1] == 0.60
    one = build_components(_ai(AILikelihoodBand.UNLIKELY), None, None, settings=settings)
    assert fuse_components(one)[1] == 0.45


def test_band_never_asserts_below_min_confidence(settings):
    assert band_for_risk(0.9, 0.45, 3, settings=settings) is FabricationRiskBand.INSUFFICIENT_DATA


def test_band_elevated_needs_two_flags(settings):
    assert band_for_risk(0.70, 0.75, 2, settings=settings) is FabricationRiskBand.ELEVATED
    # structural cap: one flag alone can never be ELEVATED, however high the score
    assert band_for_risk(0.78, 0.75, 1, settings=settings) is FabricationRiskBand.MODERATE


def test_band_thresholds(settings):
    assert band_for_risk(0.10, 0.75, 0, settings=settings) is FabricationRiskBand.LOW
    assert band_for_risk(0.30, 0.75, 0, settings=settings) is FabricationRiskBand.MODERATE
    assert band_for_risk(0.29, 0.75, 0, settings=settings) is FabricationRiskBand.LOW


def test_assess_all_clean_is_low(settings):
    a = assess_fabrication_risk(
        _ai(AILikelihoodBand.UNLIKELY), _xf(ConsistencyBand.CONSISTENT),
        _rf(DuplicationBand.UNIQUE), settings=settings,
    )
    assert a.band is FabricationRiskBand.LOW
    assert a.advisory is True
    assert len(a.components) == 3
    assert "never" in a.reasoning  # advisory copy present


def test_assess_single_near_duplicate_caps_at_moderate(settings):
    a = assess_fabrication_risk(
        _ai(AILikelihoodBand.UNLIKELY), _xf(ConsistencyBand.CONSISTENT),
        _rf(DuplicationBand.NEAR_DUPLICATE, conf=0.9), settings=settings,
    )
    assert a.band is FabricationRiskBand.MODERATE


def test_assess_corroborated_flags_reach_elevated(settings):
    a = assess_fabrication_risk(
        _ai(AILikelihoodBand.LIKELY, conf=0.8), _xf(ConsistencyBand.MAJOR_ISSUES, conf=0.8),
        _rf(DuplicationBand.NEAR_DUPLICATE, conf=0.8), settings=settings,
    )
    assert a.band is FabricationRiskBand.ELEVATED
    assert sum(1 for c in a.components if c.flagged) == 3


def test_assess_soft_signals_accumulate(settings):
    # No single subsystem flags loudly, but three soft signals together matter.
    a = assess_fabrication_risk(
        _ai(AILikelihoodBand.POSSIBLE), _xf(ConsistencyBand.MINOR_ISSUES),
        _rf(DuplicationBand.SIMILAR), settings=settings,
    )
    assert a.band is FabricationRiskBand.MODERATE


def test_assess_no_components_is_insufficient(settings):
    a = assess_fabrication_risk(None, None, None, settings=settings)
    assert a.band is FabricationRiskBand.INSUFFICIENT_DATA
    assert a.components == [] and a.score == 0.0 and a.confidence == 0.0


def test_assess_single_subsystem_never_asserts(settings):
    a = assess_fabrication_risk(None, _xf(ConsistencyBand.MAJOR_ISSUES, conf=0.9), None, settings=settings)
    assert a.band is FabricationRiskBand.INSUFFICIENT_DATA  # confidence 0.45 < 0.50


def test_assess_is_deterministic(settings):
    args = (_ai(AILikelihoodBand.POSSIBLE), _xf(ConsistencyBand.MAJOR_ISSUES), _rf(DuplicationBand.SIMILAR))
    assert assess_fabrication_risk(*args, settings=settings) == assess_fabrication_risk(*args, settings=settings)


def test_fuse_zero_total_weight_falls_back_to_plain_mean():
    # Defensive branch: evaluable components with zero confidence carry zero
    # weight; fusion then uses the unweighted mean instead of dividing by zero.
    comps = [
        RiskComponent(id="ai_generation", band="likely", risk=0.75, confidence=0.0, weight=0.0),
        RiskComponent(id="cross_field", band="consistent", risk=0.10, confidence=0.0, weight=0.0),
    ]
    score, confidence = fuse_components(comps)
    mean = (0.75 + 0.10) / 2
    assert abs(score - (0.7 * mean + 0.3 * 0.75)) < 1e-9
    assert confidence == 0.60
