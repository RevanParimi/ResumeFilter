"""Resume-farm similarity (S2.3) — deterministic MinHash, no LLM, no I/O.

Resume farms mass-produce applications from one template: same bullets,
different name/contact. Detection therefore compares CONTENT — word shingles
with identity channels (emails, phones, URLs) masked out — across candidates,
via MinHash signatures so the store never diffs raw text pairs.

Conservative by construction: shared resume templates are common and
legitimate (coaching institutes, resume builders, college placement cells),
so results are ADVISORY context for a reviewer, never a rejection signal.
S2.4 owns fusion into a unified fabrication_risk.

Determinism contract: signatures are comparable ONLY within one algo id
(hash family + permutation count + shingle size). Changing any of those
bumps `algo_id`, and stored rows only ever join on an exact algo id.
"""

from __future__ import annotations

import hashlib
import random
import re
from functools import lru_cache

from pydantic import BaseModel

from app.core.config import Settings
from app.schemas.fabrication import (
    DuplicationBand,
    ResumeFarmAssessment,
    ResumeMatch,
)

_ALGO_FAMILY = "minhash-v1"
_MERSENNE = (1 << 61) - 1  # modulus for the affine permutations
_SEED = 0x5EED_FA12  # fixed forever for minhash-v1; changing it means a new family

_EMAIL_RE = re.compile(r"\S+@\S+")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
# Also swallows bare digit runs like "2013 - 2017": farms stagger dates, so
# removing them from shingles helps detection and never hurts genuine pairs.
_PHONE_RE = re.compile(r"\+?\d[\d\s\-().]{7,}\d")
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


class Fingerprint(BaseModel):
    """One resume's MinHash signature + how much text stood behind it."""

    algo: str
    values: list[int]
    shingle_count: int


def algo_id(settings: Settings) -> str:
    return f"{_ALGO_FAMILY}:{settings.rf_num_permutations}x{settings.rf_shingle_words}"


def normalize_for_shingles(text: str) -> str:
    """Lowercased content with identity channels masked. Farms swap the name,
    email and phone but keep the bullets — contact strings must never
    contribute shingles (the name itself is ~2 words of noise; acceptable)."""
    t = text.lower()
    t = _URL_RE.sub(" ", t)
    t = _EMAIL_RE.sub(" ", t)
    t = _PHONE_RE.sub(" ", t)
    return _NON_WORD_RE.sub(" ", t).strip()


def shingle_set(text: str, size: int) -> set[str]:
    words = normalize_for_shingles(text).split()
    if len(words) < size:
        return set()
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


@lru_cache(maxsize=4)
def _permutations(num_perm: int) -> tuple[tuple[int, int], ...]:
    rng = random.Random(_SEED)  # Random's algorithm is stable across CPython versions
    return tuple(
        (rng.randrange(1, _MERSENNE), rng.randrange(0, _MERSENNE))
        for _ in range(num_perm)
    )


def _stable_hash(shingle: str) -> int:
    digest = hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def minhash_signature(shingles: set[str], num_perm: int) -> list[int]:
    """Classic MinHash: min over affine permutations of stable 64-bit hashes."""
    if not shingles:
        raise ValueError("cannot sign an empty shingle set")
    hashes = [_stable_hash(s) for s in shingles]
    return [
        min((a * h + b) % _MERSENNE for h in hashes) for a, b in _permutations(num_perm)
    ]


def estimate_similarity(a: list[int], b: list[int]) -> float:
    """Fraction of agreeing components ≈ Jaccard similarity of the shingle
    sets. Only signatures from the same algo id are comparable."""
    if not a or len(a) != len(b):
        raise ValueError("signatures are not comparable (length mismatch)")
    return sum(x == y for x, y in zip(a, b)) / len(a)


def fingerprint_text(text: str, settings: Settings) -> Fingerprint | None:
    """None when the text is too short to fingerprint honestly (a similarity
    estimate over a handful of shingles would be noise, not signal)."""
    shingles = shingle_set(text, settings.rf_shingle_words)
    if len(shingles) < settings.rf_min_shingles:
        return None
    return Fingerprint(
        algo=algo_id(settings),
        values=minhash_signature(shingles, settings.rf_num_permutations),
        shingle_count=len(shingles),
    )


def assess_resume_farm(
    matches: list[ResumeMatch],
    *,
    shingle_count: int,
    corpus_size: int,
    settings: Settings,
) -> ResumeFarmAssessment:
    """Band the store's match list (already filtered at rf_similar_threshold).

    NEAR_DUPLICATE fires on one near-identical copy OR a farm-like cluster
    (matches from >= rf_cluster_candidates_min distinct other candidates).
    Pure so S2.4 can reuse it when fusing fabrication_risk."""
    if shingle_count < settings.rf_min_shingles:
        return ResumeFarmAssessment(
            reasoning=(
                f"[deterministic] resume text too short to fingerprint honestly "
                f"(< {settings.rf_min_shingles} shingles); no comparison performed — "
                f"reviewer context only, never a rejection signal"
            )
        )

    confidence = min(0.9, 0.6 + 0.05 * min(corpus_size, 6))
    distinct = len({m.candidate_id for m in matches})
    if any(m.similarity >= settings.rf_near_dup_threshold for m in matches) or (
        distinct >= settings.rf_cluster_candidates_min
    ):
        band = DuplicationBand.NEAR_DUPLICATE
    elif matches:
        band = DuplicationBand.SIMILAR
    else:
        band = DuplicationBand.UNIQUE
    score = max((m.similarity for m in matches), default=0.0)

    if matches:
        reasoning = (
            f"[deterministic] {len(matches)} stored resume(s) from {distinct} other "
            f"candidate(s) share >= {settings.rf_similar_threshold:.0%} estimated "
            f"content overlap (max {score:.0%}) out of {corpus_size} compared; "
            f"shared templates are common and legitimate — reviewer context, "
            f"never a rejection signal"
        )
    else:
        reasoning = (
            f"[deterministic] no stored resume among {corpus_size} compared shares "
            f">= {settings.rf_similar_threshold:.0%} estimated content overlap — "
            f"reviewer context only, never a rejection signal"
        )
    return ResumeFarmAssessment(
        score=score,
        confidence=confidence,
        band=band,
        matches=matches,
        corpus_size=corpus_size,
        reasoning=reasoning,
        advisory=True,
    )
