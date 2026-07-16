"""Deterministic assessment + conservative banding — pure, offline."""

import pytest

from app.fabrication.ai_text import assess_deterministic, band_for, fuse_pairs
from app.schemas.fabrication import AILikelihoodBand

HUMAN_LONG = """Priya Nair — Senior ML Engineer

Summary: ML engineer focused on retrieval and evaluation quality. Comfortable
owning services end to end, from data curation through deployment and the
inevitable 2am pager duty that follows real production systems around.

Acme SaaS (2022–present)
- Fine-tuned Llama-3-8B with QLoRA on a 25,000-example curated support-ticket dataset; F1 rose from 0.71 to 0.84
- Built the production RAG stack: text-embedding-3-large, recursive chunking (512 tokens, 64 overlap), recall@10 of 0.92
- On-call owner for the inference cluster
- Wrote the offline eval harness (1,200 labeled examples) and tracked regressions release over release

DataWorks (2019–2022)
- Maintained Airflow DAGs feeding the feature store
- Migrated embeddings off Redis onto pgvector after a cost review
- Mentored two junior engineers through their first production launches
- Shipped a latency dashboard the SRE team still uses
"""


def test_ai_resume_trips_multiple_detectors(ai_resume):
    det = assess_deterministic(ai_resume)
    assert det.evaluated == 4
    assert len(det.signals) >= 3
    assert det.likelihood >= 0.75
    assert det.confidence == pytest.approx(0.9)


def test_long_human_resume_is_unlikely(settings):
    det = assess_deterministic(HUMAN_LONG)
    assert det.evaluated >= 3           # enough text to judge...
    assert det.signals == []            # ...and nothing fires
    band = band_for(det.likelihood, det.confidence, len(det.signals), settings)
    assert band is AILikelihoodBand.UNLIKELY


def test_short_genuine_resume_is_insufficient(genuine_resume, settings):
    det = assess_deterministic(genuine_resume)
    assert det.confidence < settings.ai_min_confidence
    band = band_for(det.likelihood, det.confidence, len(det.signals), settings)
    assert band is AILikelihoodBand.INSUFFICIENT_TEXT


def test_empty_text_evaluates_nothing():
    det = assess_deterministic("")
    assert det.evaluated == 0
    assert det.confidence == 0.0


def test_band_gates_are_conservative(settings):
    # Low confidence never asserts, no matter the likelihood.
    assert band_for(0.9, 0.4, 3, settings) is AILikelihoodBand.INSUFFICIENT_TEXT
    # < 2 deterministic tells can never be LIKELY (the LLM alone can't flag).
    assert band_for(0.9, 0.9, 1, settings) is AILikelihoodBand.POSSIBLE
    assert band_for(0.7, 0.9, 2, settings) is AILikelihoodBand.LIKELY
    assert band_for(0.5, 0.9, 0, settings) is AILikelihoodBand.POSSIBLE
    assert band_for(0.2, 0.9, 0, settings) is AILikelihoodBand.UNLIKELY


def test_fuse_pairs_math():
    assert fuse_pairs([]) == (0.0, 0.0)
    likelihood, confidence = fuse_pairs([(0.9, 0.9), (0.3, 0.3)])
    assert 0.7 < likelihood < 0.8       # weighted toward the confident source
    assert confidence == pytest.approx(0.6)


def test_settings_expose_ai_knobs(settings):
    assert settings.ai_likely_threshold == 0.65
    assert settings.ai_possible_threshold == 0.40
    assert settings.ai_min_confidence == 0.50
    assert settings.ai_llm_excerpt_chars == 6000
