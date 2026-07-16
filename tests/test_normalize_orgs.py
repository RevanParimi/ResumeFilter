"""S1.4 institution + employer canonicalization."""

from app.candidates.normalize.orgs import (
    canonicalize_employer,
    canonicalize_institution,
)


def test_iit_pattern_variants():
    for raw in ("IIT Bombay", "Indian Institute of Technology, Bombay"):
        m = canonicalize_institution(raw)
        assert m is not None and m.canonical == "IIT Bombay", raw
        assert m.tier == "tier_1"


def test_nit_trichy_spelling_variants_collide():
    a = canonicalize_institution("NIT Trichy")
    b = canonicalize_institution("National Institute of Technology, Tiruchirappalli")
    assert a is not None and b is not None
    assert a.canonical == b.canonical == "NIT Trichy"
    assert a.tier == "tier_2"


def test_alias_institutions():
    assert canonicalize_institution("Indian Institute of Science").canonical == "IISc Bangalore"
    assert canonicalize_institution("BITS Pilani").tier == "tier_1"
    assert canonicalize_institution("Visvesvaraya Technological University").canonical == "VTU"


def test_iiit_hyderabad_alias_beats_generic_pattern():
    assert canonicalize_institution("IIIT Hyderabad").tier == "tier_1"
    assert canonicalize_institution("IIIT Delhi").tier == "tier_2"  # generic pattern


def test_recognized_but_untiered():
    m = canonicalize_institution("IGNOU")
    assert m is not None and m.canonical == "IGNOU" and m.tier is None


def test_unknown_institution_none():
    assert canonicalize_institution("Springfield Institute of Magic") is None
    assert canonicalize_institution("") is None


def test_employer_aliases():
    assert canonicalize_employer("Tata Consultancy Services") == "TCS"
    assert canonicalize_employer("Cognizant Technology Solutions") == "Cognizant"
    assert canonicalize_employer("Facebook") == "Meta"


def test_employer_legal_suffixes_stripped():
    assert canonicalize_employer("Infosys Ltd") == "Infosys"
    assert canonicalize_employer("Wipro Pvt. Ltd.") == "Wipro"
    assert canonicalize_employer("Zoho Corporation") == "Zoho"
    assert canonicalize_employer("Amazon India") == "Amazon"


def test_employer_indian_startups():
    assert canonicalize_employer("Flipkart") == "Flipkart"
    assert canonicalize_employer("PhonePe") == "PhonePe"
    assert canonicalize_employer("Razorpay") == "Razorpay"


def test_employer_unknown_none():
    assert canonicalize_employer("Sharma & Sons Traders") is None
    assert canonicalize_employer("") is None
