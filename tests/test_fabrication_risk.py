"""S2.4 fusion math: component construction, fusion, banding — pure and offline."""

import pytest

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
    assert [c.id for c in comps] == ["cross_field", "resume_farm"]


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
    assert "ai_generation" not in by_id
    assert by_id["cross_field"].risk == 0.40
    assert by_id["resume_farm"].risk == 0.80


def test_flagged_only_at_top_band(settings):
    comps = build_components(
        _ai(AILikelihoodBand.POSSIBLE), _xf(ConsistencyBand.MAJOR_ISSUES),
        _rf(DuplicationBand.SIMILAR), settings=settings,
    )
    by_id = {c.id: c for c in comps}
    assert "ai_generation" not in by_id
    assert by_id["cross_field"].flagged is True
    assert by_id["resume_farm"].flagged is False


def test_weight_is_config_weight_times_confidence(settings):
    settings.fr_weight_cross_field = 2.0
    comps = build_components(None, _xf(ConsistencyBand.CONSISTENT, conf=0.8), None, settings=settings)
    assert comps[0].weight == 1.6
    assert comps[0].band == "consistent"


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
    # Only the two factual components count, with equal weights.
    assert abs(score - (0.7 * (0.75 + 0.80) / 2 + 0.3 * 0.80)) < 1e-9
    assert confidence == 0.60


def test_confidence_follows_coverage(settings):
    two = build_components(
        _ai(AILikelihoodBand.LIKELY), _xf(ConsistencyBand.CONSISTENT),
        _rf(DuplicationBand.UNIQUE), settings=settings,
    )
    assert fuse_components(two)[1] == 0.60
    one = build_components(_ai(AILikelihoodBand.LIKELY), _xf(ConsistencyBand.CONSISTENT), None, settings=settings)
    assert fuse_components(one)[1] == 0.45


def test_band_never_asserts_below_min_confidence(settings):
    assert band_for_risk(0.9, 0.45, 3, 3, settings=settings) is FabricationRiskBand.INSUFFICIENT_DATA


def test_band_elevated_needs_two_flags(settings):
    assert band_for_risk(0.70, 0.75, 2, 2, settings=settings) is FabricationRiskBand.ELEVATED
    # structural cap: one flag alone can never be ELEVATED, however high the score
    assert band_for_risk(0.78, 0.75, 1, 1, settings=settings) is FabricationRiskBand.MODERATE


def test_band_thresholds(settings):
    assert band_for_risk(0.10, 0.75, 0, 2, settings=settings) is FabricationRiskBand.LOW
    assert band_for_risk(0.30, 0.75, 0, 2, settings=settings) is FabricationRiskBand.MODERATE
    assert band_for_risk(0.29, 0.75, 0, 2, settings=settings) is FabricationRiskBand.LOW


def test_assess_all_clean_is_low(settings):
    a = assess_fabrication_risk(
        _ai(AILikelihoodBand.UNLIKELY), _xf(ConsistencyBand.CONSISTENT),
        _rf(DuplicationBand.UNIQUE), settings=settings,
    )
    assert a.band is FabricationRiskBand.LOW
    assert a.advisory is True
    assert len(a.components) == 2
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
    assert sum(1 for c in a.components if c.flagged) == 2


def test_assess_soft_signals_accumulate(settings):
    # The two factual soft signals suffice; style adds no corroboration.
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
        RiskComponent(id="resume_farm", band="near_duplicate", risk=0.80, confidence=0.0, weight=0.0),
        RiskComponent(id="cross_field", band="consistent", risk=0.10, confidence=0.0, weight=0.0),
    ]
    score, confidence = fuse_components(comps)
    mean = (0.80 + 0.10) / 2
    assert abs(score - (0.7 * mean + 0.3 * 0.80)) < 1e-9
    assert confidence == 0.60


def test_band_moderate_needs_corroboration_or_a_flag(settings):
    # One soft signal alone (nonclean=1, no flags) stays LOW even above the
    # moderate threshold; a flag or a second signal opens the gate.
    assert band_for_risk(0.32, 0.60, 0, 1, settings=settings) is FabricationRiskBand.LOW
    assert band_for_risk(0.32, 0.60, 1, 1, settings=settings) is FabricationRiskBand.MODERATE
    assert band_for_risk(0.32, 0.60, 0, 2, settings=settings) is FabricationRiskBand.MODERATE


def test_assess_single_soft_signal_stays_low(settings):
    # A soft factual signal plus a clean one cannot use style as corroboration.
    a = assess_fabrication_risk(
        _ai(AILikelihoodBand.LIKELY, conf=1.0), _xf(ConsistencyBand.CONSISTENT, conf=0.5),
        _rf(DuplicationBand.SIMILAR, conf=0.9), settings=settings,
    )
    assert a.score >= settings.fr_moderate_threshold  # the gate, not the threshold, holds it down
    assert a.band is FabricationRiskBand.LOW


@pytest.mark.parametrize("style", [
    None,
    _ai(AILikelihoodBand.INSUFFICIENT_TEXT),
    _ai(AILikelihoodBand.UNLIKELY),
    _ai(AILikelihoodBand.POSSIBLE),
    _ai(AILikelihoodBand.LIKELY, conf=0.0),
    _ai(AILikelihoodBand.LIKELY, conf=1.0),
])
@pytest.mark.parametrize("ai_weight", [0.0, 1.0, 100.0])
@pytest.mark.parametrize("factual", [
    (None, None),
    (_xf(ConsistencyBand.MAJOR_ISSUES), None),
    (_xf(ConsistencyBand.CONSISTENT), _rf(DuplicationBand.UNIQUE)),
    (_xf(ConsistencyBand.MINOR_ISSUES), _rf(DuplicationBand.SIMILAR)),
    (_xf(ConsistencyBand.MAJOR_ISSUES), _rf(DuplicationBand.NEAR_DUPLICATE)),
])
def test_style_cannot_change_any_factual_risk_output(settings, style, ai_weight, factual):
    settings.fr_weight_ai = ai_weight
    baseline = assess_fabrication_risk(None, *factual, settings=settings)
    observed = assess_fabrication_risk(style, *factual, settings=settings)
    assert observed == baseline
    assert all(c.id != "ai_generation" for c in observed.components)


def test_direct_fusion_ignores_legacy_style_component():
    factual = [RiskComponent(id="cross_field", band="consistent", risk=0.10,
                             confidence=0.8, weight=0.8)]
    style = RiskComponent(id="ai_generation", band="likely", risk=0.75,
                          confidence=1.0, weight=0.0, flagged=True)
    assert fuse_components([style, *factual]) == fuse_components(factual)
    assert fuse_components([style]) == (0.0, 0.0)


@pytest.mark.parametrize("score,confidence,flags,signals,expected", [
    (0.30, 0.50, 0, 2, "moderate"),
    (0.299999, 0.50, 0, 2, "low"),
    (0.60, 0.60, 2, 2, "elevated"),
    (0.599999, 0.60, 2, 2, "moderate"),
    (0.80, 0.499999, 2, 2, "insufficient_data"),
    (0.80, 0.60, 1, 1, "moderate"),
    (0.40, 0.60, 0, 1, "low"),
])
def test_factual_boundary_gates(settings, score, confidence, flags, signals, expected):
    assert band_for_risk(score, confidence, flags, signals, settings=settings).value == expected


def test_new_assessments_always_mark_current_semantics(settings):
    assert assess_fabrication_risk(None, None, None, settings=settings).scorer_version == 2
    assert assess_fabrication_risk(None, _xf(ConsistencyBand.CONSISTENT),
                                   _rf(DuplicationBand.UNIQUE), settings=settings).scorer_version == 2
