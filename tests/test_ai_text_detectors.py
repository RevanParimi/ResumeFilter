"""Unit tests for the deterministic AI-text detectors — pure, offline."""

from app.fabrication.ai_text import (
    bullet_runs,
    detect_metric_saturation,
    detect_symmetric_structure,
    detect_template_phrases,
    detect_uniform_bullets,
    extract_bullets,
)

# ~75 words, saturated with stock LLM-resume phrasing.
AI_PROSE = (
    "Results-driven professional with a proven track record of delivering "
    "transformative, cutting-edge solutions in fast-paced environments, "
    "leveraging state-of-the-art tooling and fostering innovative solutions "
    "across teams while remaining passionate about impactful work and "
    "committed to excellence in everything, seamlessly exceeding expectations "
    "with meticulous attention and thought leadership across many projects, "
    "having spearheaded countless initiatives and honed many skills over the "
    "years across several organizations and industries worldwide."
)

# Same numeric bullet, only the percentage varies: identical shape, all
# past-tense verb openers, every bullet a round % metric.
UNIFORM_BULLETS = [
    f"Spearheaded cutting-edge pipeline improving accuracy by {n}%"
    for n in (30, 35, 40, 45, 50, 55)
]

# Human-shaped: varied lengths, varied openers, no % metrics.
VARIED_BULLETS = [
    "Fine-tuned Llama-3-8B with QLoRA on a 25,000-example dataset; F1 0.71 to 0.84",
    "Built RAG with recursive chunking (512 tokens, 64 overlap)",
    "On-call for the inference cluster",
    "Wrote the eval harness of 1,200 labeled examples and tracked regressions "
    "across quarterly releases",
    "Mentored two junior engineers",
    "Migrated the feature store off Redis onto Postgres",
]

SECTIONED = """Experience

Job A
- Spearheaded pipeline improving accuracy by 40%
- Leveraged fine-tuning to enhance precision by 35%
- Orchestrated deployment cutting latency by 50%

Job B
- Engineered workflows increasing throughput by 45%
- Optimized pipelines reducing costs by 25%
- Streamlined evaluation lifting coverage by 60%
"""


def test_extract_bullets_and_runs():
    bullets = extract_bullets(SECTIONED)
    assert len(bullets) == 6
    assert bullets[0].startswith("Spearheaded")
    assert bullet_runs(SECTIONED) == [3, 3]


def test_template_phrases_fire_on_dense_buzzwords():
    sig = detect_template_phrases(AI_PROSE)
    assert sig is not None
    assert sig.id == "template_phrases"
    assert sig.score > 0.8
    assert "cutting-edge" in sig.detail


def test_template_phrases_none_on_plain_engineering_prose():
    text = "Fine-tuned Llama-3-8B with QLoRA on 25,000 support tickets. " * 12
    assert detect_template_phrases(text) is None


def test_template_phrases_none_when_text_too_short():
    assert detect_template_phrases("Results-driven cutting-edge leveraging synergy") is None


def test_uniform_bullets_fire_on_identical_shapes():
    sig = detect_uniform_bullets(UNIFORM_BULLETS)
    assert sig is not None
    assert sig.id == "uniform_bullets"
    assert sig.score > 0.8


def test_uniform_bullets_none_on_varied_human_bullets():
    assert detect_uniform_bullets(VARIED_BULLETS) is None


def test_uniform_bullets_none_below_minimum_count():
    assert detect_uniform_bullets(UNIFORM_BULLETS[:4]) is None


def test_metric_saturation_fires_on_round_percents_everywhere():
    sig = detect_metric_saturation(UNIFORM_BULLETS)
    assert sig is not None
    assert sig.id == "metric_saturation"
    assert sig.score > 0.9


def test_metric_saturation_none_when_metrics_sparse():
    assert detect_metric_saturation(VARIED_BULLETS) is None


def test_symmetric_structure_fires_on_identical_entry_shapes():
    sig = detect_symmetric_structure([4, 4, 4])
    assert sig is not None
    assert sig.id == "symmetric_structure"
    assert sig.score >= 0.8


def test_symmetric_structure_none_on_organic_variation():
    assert detect_symmetric_structure([4, 3, 5]) is None
    assert detect_symmetric_structure([2, 2, 2]) is None  # entries too small to be a "shape"
    assert detect_symmetric_structure([4, 4]) is None  # < 3 entries
