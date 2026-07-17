"""Farm banding — pure, offline, conservative copy mandated."""

from app.fabrication.similarity import assess_resume_farm
from app.schemas.fabrication import DuplicationBand, ResumeMatch


def _m(cand: str, sim: float, resume: str = "r") -> ResumeMatch:
    return ResumeMatch(candidate_id=cand, resume_id=f"{resume}_{cand}", similarity=sim)


def test_short_text_is_insufficient_regardless_of_matches(settings):
    a = assess_resume_farm(
        [_m("c1", 0.95)], shingle_count=10, corpus_size=5, settings=settings
    )
    assert a.band is DuplicationBand.INSUFFICIENT_DATA
    assert a.confidence == 0.0


def test_no_matches_is_unique(settings):
    a = assess_resume_farm([], shingle_count=200, corpus_size=6, settings=settings)
    assert a.band is DuplicationBand.UNIQUE
    assert a.score == 0.0
    assert a.matches == []
    assert a.corpus_size == 6
    assert a.confidence == 0.9


def test_empty_corpus_unique_has_low_confidence(settings):
    a = assess_resume_farm([], shingle_count=200, corpus_size=0, settings=settings)
    assert a.band is DuplicationBand.UNIQUE
    assert a.confidence == 0.6  # "unique among nothing" is a weak claim


def test_single_high_match_is_near_duplicate(settings):
    a = assess_resume_farm(
        [_m("c1", 0.91)], shingle_count=200, corpus_size=4, settings=settings
    )
    assert a.band is DuplicationBand.NEAR_DUPLICATE
    assert a.score == 0.91


def test_mid_match_is_similar_only(settings):
    a = assess_resume_farm(
        [_m("c1", 0.65)], shingle_count=200, corpus_size=4, settings=settings
    )
    assert a.band is DuplicationBand.SIMILAR


def test_cluster_of_mid_matches_escalates_to_near_duplicate(settings):
    # A farm rarely produces one perfect copy; it produces MANY near copies.
    matches = [_m("c1", 0.65), _m("c2", 0.68), _m("c3", 0.62)]
    a = assess_resume_farm(matches, shingle_count=200, corpus_size=8, settings=settings)
    assert a.band is DuplicationBand.NEAR_DUPLICATE


def test_two_versions_of_one_other_candidate_stay_similar(settings):
    # Two resumes from ONE other candidate is not a cluster of candidates.
    matches = [_m("c1", 0.65), _m("c1", 0.68, resume="r2")]
    a = assess_resume_farm(matches, shingle_count=200, corpus_size=8, settings=settings)
    assert a.band is DuplicationBand.SIMILAR


def test_reasoning_carries_the_advisory_framing(settings):
    a = assess_resume_farm(
        [_m("c1", 0.91)], shingle_count=200, corpus_size=4, settings=settings
    )
    assert "never a rejection signal" in a.reasoning
    assert a.advisory is True
    clean = assess_resume_farm([], shingle_count=200, corpus_size=4, settings=settings)
    assert "no stored resume" in clean.reasoning
