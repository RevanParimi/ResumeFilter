"""S8.4 Phase B: the queue read-model's pure types.

The DPDP assertion in this file is load-bearing rather than stylistic. An item
keeps its signals after its candidate is erased (batch_items.candidate_id is
SET NULL so the org's record of what it screened is not silently rewritten), so
anything free-form stored here outlives the person it describes.
"""

from __future__ import annotations

import pytest

from app.schemas.fabrication import (
    FabricationRiskAssessment, FabricationRiskBand, ResumeFarmAssessment,
    RiskComponent,
)
from app.schemas.report import DepthBand, Report
from app.screening.schema import (
    BatchCounts, BatchStatus, ItemSignals, ItemStatus, compose_reason,
    derive_status, signals_from_report,
)


def test_item_signals_holds_no_free_text():
    """Every field is a number, a bool, an enum member, or one of the three
    closed-vocabulary strings -- design §1.2.

    Written as an allowlist of FIELD NAMES rather than a check on types,
    because `str` is exactly what a prose field would also be: only a human
    decision can say that `loudest_signal` is a closed vocabulary and a
    hypothetical `reasoning` is not. Adding any string field therefore fails
    here until someone justifies it.
    """
    closed_vocabulary_strings = {"loudest_signal", "loudest_band", "matched_on"}
    for name, field in ItemSignals.model_fields.items():
        anno = str(field.annotation)
        if "str" in anno:
            assert name in closed_vocabulary_strings, (
                f"{name} is a string field on an item that OUTLIVES its "
                f"candidate's erasure (batch_items.candidate_id is SET NULL). "
                f"If it is a closed vocabulary, add it to this set and say so; "
                f"if it is prose, it does not belong in ItemSignals."
            )


def test_item_signals_string_fields_are_closed_vocabularies():
    """The three string-ish fields are enumerated values, not prose. Asserted by
    name so ADDING a prose field to this model fails here."""
    assert set(ItemSignals.model_fields) == {
        "risk_band", "risk_confidence", "depth_band", "depth_score",
        "loudest_signal", "loudest_band", "n_components",
        "farm_band", "farm_score", "farm_corpus_size",
        "matched_existing", "matched_on", "duplicate_resume", "flagged_claims",
    }


def _report_with(components, *, band=FabricationRiskBand.ELEVATED) -> Report:
    return Report(
        depth_score=0.4, depth_band=DepthBand.EMERGING, overall_confidence=0.5,
        fabrication_risk=FabricationRiskAssessment(
            score=0.7, confidence=0.6, band=band, components=components,
            reasoning="prose that must NOT be copied onto the item",
        ),
        resume_farm=ResumeFarmAssessment(score=0.9, confidence=0.8, corpus_size=12),
        flagged_claim_ids=["c1", "c2"],
    )


def test_signals_from_report_picks_the_heaviest_component_as_loudest():
    rep = _report_with([
        RiskComponent(id="ai_generation", band="low", risk=0.2, confidence=0.9, weight=0.9),
        RiskComponent(id="resume_farm", band="elevated", risk=0.9, confidence=0.8, weight=2.4),
        RiskComponent(id="cross_field", band="moderate", risk=0.5, confidence=0.5, weight=1.0),
    ])
    sig = signals_from_report(rep, matched_existing=True, matched_on="email_hash",
                              duplicate_resume=False)
    assert sig.loudest_signal == "resume_farm"
    assert sig.loudest_band == "elevated"
    assert sig.n_components == 3
    assert sig.flagged_claims == 2
    assert sig.farm_corpus_size == 12
    assert sig.matched_existing is True and sig.matched_on == "email_hash"


def test_signals_from_report_ties_break_deterministically():
    """Two identical reports must not render a different loudest signal."""
    comps = [
        RiskComponent(id="cross_field", band="low", risk=0.5, confidence=0.5, weight=1.0),
        RiskComponent(id="ai_generation", band="low", risk=0.5, confidence=0.5, weight=1.0),
    ]
    a = signals_from_report(_report_with(comps), matched_existing=False,
                            matched_on=None, duplicate_resume=False)
    b = signals_from_report(_report_with(list(reversed(comps))), matched_existing=False,
                            matched_on=None, duplicate_resume=False)
    assert a.loudest_signal == b.loudest_signal == "ai_generation"


def test_signals_from_a_report_with_no_fabrication_block_is_neutral():
    """Pre-S2.4 stored reports have none. Neutral, never a zero score -- an
    absent assessment is not a clean one."""
    sig = signals_from_report(Report(), matched_existing=False, matched_on=None,
                              duplicate_resume=False)
    assert sig.risk_band == FabricationRiskBand.INSUFFICIENT_DATA
    assert sig.loudest_signal is None


def test_compose_reason_reads_as_a_sentence_and_names_the_signal():
    sig = ItemSignals(
        risk_band=FabricationRiskBand.ELEVATED, risk_confidence=0.42,
        loudest_signal="resume_farm", loudest_band="elevated", n_components=3,
    )
    text = compose_reason(sig, ItemStatus.DONE, None)
    assert "elevated" in text and "resume farm" in text.lower() and "0.42" in text


def test_compose_reason_for_an_unprocessed_or_failed_item():
    assert compose_reason(None, ItemStatus.PENDING, None) == "not screened yet"
    assert "empty_resume" in compose_reason(None, ItemStatus.FAILED, "empty_resume")


def test_compose_reason_never_claims_confidence_it_does_not_have():
    sig = ItemSignals(risk_band=FabricationRiskBand.INSUFFICIENT_DATA, risk_confidence=0.0)
    assert "insufficient" in compose_reason(sig, ItemStatus.DONE, None).lower()


@pytest.mark.parametrize(
    "counts,expected",
    [
        (BatchCounts(), BatchStatus.EMPTY),
        (BatchCounts(pending=3), BatchStatus.PENDING),
        # In flight beats work-not-started: a batch with an item genuinely
        # being screened reads `processing`, even though items also remain
        # queued behind it. "pending" is reserved for "nothing has started".
        (BatchCounts(pending=1, processing=1), BatchStatus.PROCESSING),
        (BatchCounts(processing=1), BatchStatus.PROCESSING),
        (BatchCounts(done=3), BatchStatus.COMPLETE),
        (BatchCounts(done=2, failed=1), BatchStatus.PARTIAL),
        (BatchCounts(failed=3), BatchStatus.PARTIAL),
        (BatchCounts(done=1, pending=1), BatchStatus.PENDING),
    ],
)
def test_derive_status(counts, expected):
    """Derived at read time, never stored (spec §4.4): a stored status goes
    stale the moment a process dies and nothing afterwards corrects it."""
    assert derive_status(counts) == expected
