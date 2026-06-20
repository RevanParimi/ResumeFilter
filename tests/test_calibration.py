from app.core.calibration import aggregate_depth, classify
from app.schemas.report import DepthBand, VerdictStatus


def test_flag_requires_low_coherence_and_high_confidence(settings):
    assert classify(coherence=0.05, confidence=0.9, has_evidence=True, settings=settings) == (
        VerdictStatus.INCOHERENT
    )


def test_low_confidence_defers_not_flags(settings):
    # The conservative core: unsure → defer, never flag a possibly-real person.
    assert classify(coherence=0.05, confidence=0.30, has_evidence=True, settings=settings) == (
        VerdictStatus.DEFER
    )


def test_high_coherence_is_coherent(settings):
    assert classify(coherence=0.85, confidence=0.9, has_evidence=True, settings=settings) == (
        VerdictStatus.COHERENT
    )


def test_no_evidence_is_unverified(settings):
    assert classify(coherence=0.5, confidence=0.0, has_evidence=False, settings=settings) == (
        VerdictStatus.UNVERIFIED
    )


def test_aggregate_insufficient_when_unconfident(settings):
    _, _, band = aggregate_depth([(0.9, 0.1), (0.8, 0.2)], settings=settings)
    assert band == DepthBand.INSUFFICIENT_SIGNAL


def test_aggregate_deep_when_confident_and_coherent(settings):
    depth, conf, band = aggregate_depth([(0.85, 0.85), (0.9, 0.85)], settings=settings)
    assert band == DepthBand.DEEP
    assert depth > 0.8 and conf > 0.5
