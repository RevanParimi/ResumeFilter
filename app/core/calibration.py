"""Calibration — the conservative decision layer.

Thresholds live in config; the *logic* lives here. The governing principle:
false positives (flagging a real person) are the existential risk, so we only
assert INCOHERENT when coherence is low AND confidence is high. Whenever we
aren't confident enough, we DEFER to a human rather than flag.

Pure functions, no I/O — trivially unit-testable.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.schemas.report import DepthBand, VerdictStatus


def classify(
    *, coherence: float, confidence: float, has_evidence: bool,
    settings: Settings | None = None,
) -> VerdictStatus:
    """Map (coherence, confidence) → a conservative per-claim status."""
    s = settings or get_settings()

    if not has_evidence:
        return VerdictStatus.UNVERIFIED

    # Not confident enough to assert anything → human decides.
    if confidence < s.defer_confidence_threshold:
        return VerdictStatus.DEFER

    # Flag ONLY when clearly incoherent AND we're confident enough to act.
    if coherence < s.flag_coherence_threshold and confidence >= s.flag_min_confidence:
        return VerdictStatus.INCOHERENT

    # Clearly coherent.
    if coherence >= s.flag_coherence_threshold:
        return VerdictStatus.COHERENT

    # Low coherence but not confident enough to flag → defer (conservative).
    return VerdictStatus.DEFER


def aggregate_depth(
    scores: list[tuple[float, float]],  # (coherence, confidence) per claim
    *, settings: Settings | None = None,
) -> tuple[float, float, DepthBand]:
    """Confidence-weighted depth score + overall confidence + advisory band."""
    s = settings or get_settings()
    if not scores:
        return 0.0, 0.0, DepthBand.INSUFFICIENT_SIGNAL

    weight = sum(c for _, c in scores)
    overall_conf = weight / len(scores)
    if weight == 0:
        depth = sum(coh for coh, _ in scores) / len(scores)
    else:
        depth = sum(coh * conf for coh, conf in scores) / weight

    # If we collectively aren't confident, don't pretend to band.
    if overall_conf < s.defer_confidence_threshold:
        return depth, overall_conf, DepthBand.INSUFFICIENT_SIGNAL

    band = (
        DepthBand.DEEP if depth >= 0.80
        else DepthBand.SOLID if depth >= 0.60
        else DepthBand.EMERGING if depth >= 0.40
        else DepthBand.SUPERFICIAL
    )
    return depth, overall_conf, band
