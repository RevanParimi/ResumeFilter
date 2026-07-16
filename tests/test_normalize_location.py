"""S1.4 city gazetteer + notice-period parsing (raw-text scanners with offsets)."""

from app.candidates.normalize.location import find_city, parse_notice_period


def test_bangalore_becomes_bengaluru():
    for raw in ("Bangalore", "Bengaluru, Karnataka"):
        m = find_city(raw)
        assert m is not None and m.city == "Bengaluru", raw
        assert m.tier == "metro"


def test_gurgaon_becomes_gurugram():
    assert find_city("Gurgaon, Haryana").city == "Gurugram"


def test_new_delhi_prefers_longest_alias():
    m = find_city("New Delhi, India")
    assert m.city == "Delhi" and m.text == "New Delhi"


def test_tier2_aliases():
    assert find_city("Mysore").city == "Mysuru"
    assert find_city("Trivandrum").city == "Thiruvananthapuram"
    m = find_city("Vizag")
    assert m.city == "Visakhapatnam" and m.tier == "tier_2"


def test_find_city_span_offsets():
    text = "Based in Pune since 2020"
    m = find_city(text)
    assert text[m.start : m.end] == m.text == "Pune"


def test_no_known_city_none():
    assert find_city("Remote, Mars Colony One") is None
    assert find_city("") is None


def test_notice_labelled_forms():
    assert parse_notice_period("Notice Period: 30 days").days == 30
    assert parse_notice_period("Notice period - 2 months").days == 60


def test_notice_inline_forms():
    assert parse_notice_period("45 days notice").days == 45
    assert parse_notice_period("2 weeks' notice").days == 14


def test_notice_immediate_forms():
    assert parse_notice_period("Immediate joiner").days == 0
    assert parse_notice_period("Notice Period: Immediate").days == 0
    assert parse_notice_period("Available immediately").days == 0


def test_notice_bare_value_forms():
    # LLM extraction returns just the value ("30 days"): accept whole-string.
    assert parse_notice_period("30 days").days == 30
    assert parse_notice_period("Immediate").days == 0


def test_notice_serving_is_unquantified():
    m = parse_notice_period("Currently serving notice period")
    assert m is not None and m.days is None
    assert "serving notice" in m.text.lower()


def test_notice_absent_none():
    assert parse_notice_period("Python developer, 5 years experience") is None


def test_notice_span_offsets():
    text = "Skills: Python\nNotice Period: 45 days\n"
    m = parse_notice_period(text)
    assert text[m.start : m.end] == m.text
    assert m.days == 45
