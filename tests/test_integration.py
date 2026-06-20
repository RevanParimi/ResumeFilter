"""End-to-end: the fabricated resume must be flagged WITH evidence; the genuine
one must not be flagged. Runs the full LangGraph with offline fake services."""

from app.graph.build import EvaluationEngine


async def test_fabricated_resume_is_flagged_with_evidence(services, fabricated_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=fabricated_resume, domain="genai")

    # Mandates.
    assert report.advisory is True
    assert report.human_review_required is True

    # Something must be flagged...
    assert report.flagged_claim_ids, "fabricated resume should raise at least one flag"

    # ...and every flag is EXPLAINED (no bare 'fake' labels).
    flagged = [v for v in report.verdicts if v.claim_id in report.flagged_claim_ids]
    assert all(v.evidence for v in flagged)
    assert all(v.reasoning for v in flagged)
    assert all(v.missing_signals for v in flagged)


async def test_genuine_resume_is_not_flagged(services, genuine_resume):
    engine = EvaluationEngine(services)
    report = await engine.evaluate(resume_text=genuine_resume, domain="genai")

    incoherent = [v for v in report.verdicts if v.status.value == "incoherent"]
    assert not incoherent, "a genuine resume must not be flagged (false positives are the risk)"
    assert report.depth_band.value in {"solid", "deep"}
    assert report.human_review_required is True  # still advisory, always
