"""Contact normalization + salted hashing for identity dedup (DPDP-lean).

S1.2 resolves "same candidate, new resume" by comparing these hashes instead
of raw contact values. The salt is a config.yaml tunable, NOT a secret — it
must stay stable across deploys or dedup breaks; changing it orphans every
stored hash.
"""

from __future__ import annotations

import hashlib
import re

from app.candidates.schema import CandidateProfile

_NON_DIGITS = re.compile(r"\D+")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(phone: str, default_country: str = "91") -> str:
    """Reduce a phone to '+<country><number>'; '' when not phone-shaped.

    Indian resumes write the same number as '+91 98765 43210',
    '098765 43210' or '9876543210' — all must hash identically.
    """
    digits = _NON_DIGITS.sub("", phone).lstrip("0")
    if len(digits) == 10:
        digits = default_country + digits
    if not 11 <= len(digits) <= 15:
        return ""
    return "+" + digits


def contact_hash(normalized: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{normalized}".encode("utf-8")).hexdigest()


def apply_contact_hashes(profile: CandidateProfile, salt: str) -> None:
    """Fill contact.*_hash in place from the raw extracted values."""
    contact = profile.contact
    if contact.email and contact.email.value:
        contact.email_hash = contact_hash(normalize_email(contact.email.value), salt)
    if contact.phone and contact.phone.value:
        normalized = normalize_phone(contact.phone.value)
        if normalized:
            contact.phone_hash = contact_hash(normalized, salt)
