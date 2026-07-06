"""Contact dedup hashing (S1.1): same person ⇒ same hash, salt-scoped."""

from app.candidates.hashing import (
    apply_contact_hashes,
    contact_hash,
    normalize_email,
    normalize_phone,
)
from app.candidates.schema import CandidateProfile, ContactInfo, ExtractedStr


def test_email_normalization_is_case_and_space_insensitive():
    a = normalize_email("  Arjun.Mehta@Example.COM ")
    b = normalize_email("arjun.mehta@example.com")
    assert a == b == "arjun.mehta@example.com"


def test_indian_phone_formats_normalize_identically():
    forms = ["+91 98765 43210", "098765 43210", "9876543210", "+91-98765-43210"]
    assert {normalize_phone(f) for f in forms} == {"+919876543210"}


def test_non_phone_input_normalizes_to_empty():
    assert normalize_phone("123") == ""
    assert normalize_phone("call me") == ""


def test_contact_hash_is_salt_scoped_and_deterministic():
    h1 = contact_hash("arjun@example.com", salt="veritas-dedup-v1")
    h2 = contact_hash("arjun@example.com", salt="veritas-dedup-v1")
    h3 = contact_hash("arjun@example.com", salt="other-salt")
    assert h1 == h2 and h1 != h3 and len(h1) == 64


def test_apply_contact_hashes_fills_profile_in_place():
    profile = CandidateProfile(
        contact=ContactInfo(
            email=ExtractedStr(value="Arjun.Mehta@Example.com"),
            phone=ExtractedStr(value="+91 98765 43210"),
        )
    )
    apply_contact_hashes(profile, salt="veritas-dedup-v1")
    assert profile.contact.email_hash == contact_hash(
        "arjun.mehta@example.com", "veritas-dedup-v1"
    )
    assert profile.contact.phone_hash == contact_hash(
        "+919876543210", "veritas-dedup-v1"
    )


def test_apply_contact_hashes_skips_missing_or_invalid():
    profile = CandidateProfile(
        contact=ContactInfo(phone=ExtractedStr(value="not a phone"))
    )
    apply_contact_hashes(profile, salt="veritas-dedup-v1")
    assert profile.contact.email_hash is None
    assert profile.contact.phone_hash is None


def test_settings_expose_contact_hash_salt(settings):
    assert settings.contact_hash_salt == "veritas-dedup-v1"
