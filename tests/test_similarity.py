"""MinHash similarity — pure, offline, deterministic by construction."""

import pytest

from app.fabrication.similarity import (
    Fingerprint,
    algo_id,
    estimate_similarity,
    fingerprint_text,
    minhash_signature,
    normalize_for_shingles,
    shingle_set,
)


def test_normalization_masks_identity_channels():
    text = "Arjun Mehta | arjun.mehta@example.com | +91 98220 11223 | www.arjun.dev"
    out = normalize_for_shingles(text)
    assert "example" not in out          # email masked
    assert "98220" not in out            # phone masked
    assert "arjun dev" not in out        # url masked
    assert "arjun mehta" in out          # names are NOT masked (only ~2 words of noise)


def test_year_ranges_are_masked_like_phones():
    # The phone mask deliberately swallows bare digit runs such as "2013 - 2017";
    # farms stagger dates, so removing them from shingles helps detection.
    assert "2013" not in normalize_for_shingles("B.E. — PICT, 2013 - 2017")


def test_shingles_are_word_trigrams():
    s = shingle_set("alpha beta gamma delta", 3)
    assert s == {"alpha beta gamma", "beta gamma delta"}
    assert shingle_set("too short", 3) == set()


def test_signature_is_deterministic_and_sized():
    sh = shingle_set("one two three four five six seven eight nine ten", 3)
    a = minhash_signature(sh, 64)
    b = minhash_signature(sh, 64)
    assert a == b
    assert len(a) == 64


def test_identical_sets_estimate_one_disjoint_near_zero():
    x = shingle_set("the quick brown fox jumps over the lazy dog again and again", 3)
    y = shingle_set("completely different resume content about databases and networking systems here", 3)
    sx, sy = minhash_signature(x, 128), minhash_signature(y, 128)
    assert estimate_similarity(sx, sx) == 1.0
    assert estimate_similarity(sx, sy) < 0.15


def test_estimate_rejects_incomparable_signatures():
    with pytest.raises(ValueError):
        estimate_similarity([1, 2, 3], [1, 2])


def test_fingerprint_text_rejects_short_text(settings):
    assert fingerprint_text("too little text to fingerprint honestly", settings) is None


def test_fingerprint_text_shape(settings, farm_resume_a):
    fp = fingerprint_text(farm_resume_a, settings)
    assert isinstance(fp, Fingerprint)
    assert fp.algo == algo_id(settings) == "minhash-v1:128x3"
    assert len(fp.values) == settings.rf_num_permutations
    assert fp.shingle_count >= settings.rf_min_shingles


def test_contact_swap_alone_changes_nothing(settings, farm_resume_a):
    # Masking makes an email/phone-only swap invisible: same signature.
    swapped = farm_resume_a.replace("arjun.mehta@example.com", "someone.else@other.org")
    swapped = swapped.replace("+91 98220 11223", "+91 90000 00001")
    assert fingerprint_text(swapped, settings).values == fingerprint_text(farm_resume_a, settings).values


def test_farm_pair_estimates_near_duplicate(settings, farm_resume_a, farm_resume_b):
    fa = fingerprint_text(farm_resume_a, settings)
    fb = fingerprint_text(farm_resume_b, settings)
    assert estimate_similarity(fa.values, fb.values) >= 0.85


def test_farm_vs_genuine_estimates_low(settings, farm_resume_a, genuine_resume):
    fa = fingerprint_text(farm_resume_a, settings)
    fg = fingerprint_text(genuine_resume, settings)
    assert estimate_similarity(fa.values, fg.values) < 0.4


def test_settings_expose_rf_knobs(settings):
    assert settings.rf_shingle_words == 3
    assert settings.rf_num_permutations == 128
    assert settings.rf_min_shingles == 40
    assert settings.rf_similar_threshold == 0.60
    assert settings.rf_near_dup_threshold == 0.80
    assert settings.rf_cluster_candidates_min == 3
    assert settings.rf_max_matches == 10
