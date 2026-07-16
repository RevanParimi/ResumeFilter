"""S1.4 skill taxonomy — norm_key + normalize_skill lookup tables."""

from app.candidates.normalize.skills import (
    SKILL_CATEGORIES,
    _TAXONOMY,
    normalize_skill,
)
from app.candidates.normalize.text import norm_key


def test_norm_key_lowers_and_collapses_punctuation():
    assert norm_key("  Node.JS ") == "node js"
    assert norm_key("CI/CD") == "ci cd"
    assert norm_key("scikit-learn") == "scikit learn"


def test_norm_key_keeps_plus_and_hash():
    assert norm_key("C++") == "c++"
    assert norm_key("C#") == "c#"


def test_exact_canonical_match():
    m = normalize_skill("Python")
    assert m is not None
    assert (m.canonical, m.category) == ("python", "language")


def test_alias_variants():
    assert normalize_skill("JS").canonical == "javascript"
    assert normalize_skill("ReactJS").canonical == "react"
    assert normalize_skill("K8s").canonical == "kubernetes"
    assert normalize_skill("PySpark").canonical == "apache_spark"


def test_punctuation_variants():
    assert normalize_skill("Node.js").canonical == "nodejs"
    assert normalize_skill("scikit-learn").canonical == "scikit_learn"
    assert normalize_skill("CI/CD").canonical == "ci_cd"


def test_symbol_languages():
    assert normalize_skill("C++").canonical == "cpp"
    assert normalize_skill("c#").canonical == "csharp"


def test_all_categories_from_fixed_vocabulary():
    used = {category for category, _aliases in _TAXONOMY.values()}
    assert used <= SKILL_CATEGORIES


def test_unknown_and_empty_return_none():
    assert normalize_skill("Underwater Basket Weaving") is None
    assert normalize_skill("") is None
    assert normalize_skill("   ") is None
