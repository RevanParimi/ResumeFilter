from datetime import datetime, timezone
from app.features.schema import FeatureContext
import app.features.definitions.depth as depth
from app.schemas.report import CoherenceVerdict, DepthBand, Report, VerdictStatus

AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _ctx(report):
    return FeatureContext(candidate_id="c1", as_of=AS_OF, report=report)


def _report(**kw):
    return Report(candidate_id="c1", **kw)


def test_depth_scalars_and_band():
    r = _report(depth_score=0.72, overall_confidence=0.6, depth_band=DepthBand.SOLID)
    assert depth.depth_score(_ctx(r)) == 0.72
    assert depth.overall_confidence(_ctx(r)) == 0.6
    assert depth.depth_band(_ctx(r)) == "solid"


def test_depth_none_without_report():
    assert depth.depth_score(_ctx(None)) is None
    assert depth.depth_band(_ctx(None)) is None


def test_claim_counts_and_ratio():
    verdicts = [
        CoherenceVerdict(claim_id="a", claim_text="x", claim_type="t",
                         status=VerdictStatus.COHERENT),
        CoherenceVerdict(claim_id="b", claim_text="y", claim_type="t",
                         status=VerdictStatus.INCOHERENT),
    ]
    r = _report(verdicts=verdicts, flagged_claim_ids=["b"], deferred_claim_ids=[])
    ctx = _ctx(r)
    assert depth.verdict_count(ctx) == 2
    assert depth.flagged_claim_count(ctx) == 1
    assert depth.deferred_claim_count(ctx) == 0
    assert depth.coherent_claim_ratio(ctx) == 0.5


def test_coherent_ratio_none_without_verdicts():
    assert depth.coherent_claim_ratio(_ctx(_report())) is None
