from app.candidates.normalize.skills import (
    SKILL_CATEGORIES, SkillMatch, canonical_ids, category_for_canonical,
    clear_curated_overlay, normalize_skill, set_curated_overlay,
)


def teardown_function():
    clear_curated_overlay()  # never leak module state between tests


def test_overlay_fills_a_gap():
    assert normalize_skill("COBOL") is None
    set_curated_overlay({"cobol": SkillMatch(canonical="cobol", category="language")})
    m = normalize_skill("COBOL")
    assert m is not None and m.canonical == "cobol" and m.category == "language"


def test_static_taxonomy_wins_over_overlay():
    # try to shadow a known canonical; static index must still win
    set_curated_overlay({"python": SkillMatch(canonical="hijacked", category="ml")})
    assert normalize_skill("Python").canonical == "python"


def test_clear_overlay_restores_gap():
    set_curated_overlay({"cobol": SkillMatch(canonical="cobol", category="language")})
    clear_curated_overlay()
    assert normalize_skill("COBOL") is None


def test_canonical_ids_and_category_span_static_and_overlay():
    assert "python" in canonical_ids()
    assert category_for_canonical("python") == "language"
    set_curated_overlay({"cobol": SkillMatch(canonical="cobol", category="language")})
    assert "cobol" in canonical_ids()
    assert category_for_canonical("cobol") == "language"
    assert category_for_canonical("nope") is None


def test_empty_name_is_none_even_with_overlay():
    set_curated_overlay({"cobol": SkillMatch(canonical="cobol", category="language")})
    assert normalize_skill("") is None
