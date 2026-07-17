"""Fingerprint persistence: idempotent save, cross-candidate query, DPDP cascade."""

from app.candidates.extractor import heuristic_profile
from app.candidates.schema import ExtractionResult
from app.fabrication.similarity import Fingerprint, fingerprint_text
from tests.conftest import make_candidate_store


def _ingest(store, text: str):
    profile = heuristic_profile(text)
    return store.ingest(ExtractionResult(profile=profile, method="heuristic"), text)


def _fp(values: list[int], algo: str = "minhash-v1:128x3") -> Fingerprint:
    return Fingerprint(algo=algo, values=values, shingle_count=100)


def test_save_is_idempotent_per_resume_and_algo(farm_resume_a, settings):
    store = make_candidate_store()
    out = _ingest(store, farm_resume_a)
    fp = fingerprint_text(farm_resume_a, settings)
    assert store.save_fingerprint(fp, resume_id=out.resume_id, candidate_id=out.candidate_id) is True
    assert store.save_fingerprint(fp, resume_id=out.resume_id, candidate_id=out.candidate_id) is False


def test_similar_resumes_finds_the_other_candidate(farm_resume_a, farm_resume_b, settings):
    store = make_candidate_store()
    out_a = _ingest(store, farm_resume_a)
    out_b = _ingest(store, farm_resume_b)
    assert out_a.candidate_id != out_b.candidate_id  # different contact hashes
    fa = fingerprint_text(farm_resume_a, settings)
    fb = fingerprint_text(farm_resume_b, settings)
    store.save_fingerprint(fa, resume_id=out_a.resume_id, candidate_id=out_a.candidate_id)
    store.save_fingerprint(fb, resume_id=out_b.resume_id, candidate_id=out_b.candidate_id)

    matches, corpus = store.similar_resumes(
        fb, exclude_candidate_id=out_b.candidate_id, threshold=0.60, limit=10
    )
    assert corpus == 1
    assert len(matches) == 1
    assert matches[0].candidate_id == out_a.candidate_id
    assert matches[0].resume_id == out_a.resume_id
    assert matches[0].similarity >= 0.85


def test_own_candidate_is_always_excluded(farm_resume_a, settings):
    store = make_candidate_store()
    out = _ingest(store, farm_resume_a)
    fp = fingerprint_text(farm_resume_a, settings)
    store.save_fingerprint(fp, resume_id=out.resume_id, candidate_id=out.candidate_id)
    matches, corpus = store.similar_resumes(
        fp, exclude_candidate_id=out.candidate_id, threshold=0.60, limit=10
    )
    assert matches == [] and corpus == 0  # a perfect self-match never surfaces


def test_threshold_and_algo_filter(farm_resume_a, genuine_resume, settings):
    store = make_candidate_store()
    out_a = _ingest(store, farm_resume_a)
    out_g = _ingest(store, genuine_resume)
    fa = fingerprint_text(farm_resume_a, settings)
    fg = fingerprint_text(genuine_resume, settings)
    store.save_fingerprint(fa, resume_id=out_a.resume_id, candidate_id=out_a.candidate_id)
    # Unrelated content below threshold -> compared but not matched.
    matches, corpus = store.similar_resumes(
        fg, exclude_candidate_id=out_g.candidate_id, threshold=0.60, limit=10
    )
    assert corpus == 1 and matches == []
    # Different algo id -> not even compared (signatures incomparable).
    alien = _fp([1] * 64, algo="minhash-v1:64x3")
    matches, corpus = store.similar_resumes(
        alien, exclude_candidate_id=out_g.candidate_id, threshold=0.0, limit=10
    )
    assert corpus == 0 and matches == []


def test_dpdp_deletes_cascade_to_fingerprints(farm_resume_a, farm_resume_b, settings):
    store = make_candidate_store()
    out_a = _ingest(store, farm_resume_a)
    out_b = _ingest(store, farm_resume_b)
    fa = fingerprint_text(farm_resume_a, settings)
    fb = fingerprint_text(farm_resume_b, settings)
    store.save_fingerprint(fa, resume_id=out_a.resume_id, candidate_id=out_a.candidate_id)
    store.save_fingerprint(fb, resume_id=out_b.resume_id, candidate_id=out_b.candidate_id)

    store.delete_resume(out_a.resume_id)          # resume-level erasure
    _, corpus = store.similar_resumes(
        fb, exclude_candidate_id=out_b.candidate_id, threshold=0.60, limit=10
    )
    assert corpus == 0

    store.delete_candidate(out_b.candidate_id)    # candidate-level erasure
    _, corpus = store.similar_resumes(
        fa, exclude_candidate_id="nobody", threshold=0.0, limit=10
    )
    assert corpus == 0
