# S7.1 — Verification Spine + Consent-First Identity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `app/verification/` — a reusable verification spine (assurance ladder behind a method-adapter seam) with consent-first identity verification as its first producer, so S7.2 can land document forensics as a second producer and a real KYC vendor is later just a new adapter.

**Architecture:** A new pure package owning two tables. Pure modules (`schema`/`assurance`/`otp`/`methods`) hold all logic with injected clock and RNG; `store.py` adds persistence, consent enforcement and audit; `service.py` orchestrates. Verification imports the ledger for consent — **the ledger never imports verification**. Assurance is computed at read time, never stored, and is advisory: it feeds no ranking, matching, or depth score.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 + Alembic on SQLite (Postgres-shaped), pytest. No LLM, no network, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-31-s71-identity-verification-design.md` — read it before Task 1.

## Global Constraints

- **TDD, fully offline.** No network, no API key, no LLM anywhere in S7.1. `pytest -q` green before every commit.
- **Advisory only.** `IdentityAssurance` never gates matching, ranking, depth scoring, or rejection. No auto-reject.
- **Store outcomes, never documents or biometrics.** The only evidence field is `evidence_digest`, a sha256 hex string. Never add a column able to hold an artifact.
- **Taxonomies are code constants** (`AssuranceLevel`, `VerificationMethod`, `VerificationStatus`, `ConsentPurpose`) — never config.
- **Tunables in `config.yaml` + `Settings`**, secrets only in `.env` (`DEE_*`). `config.yaml` comments must stay **ASCII-only** (the file is read as cp1252 on this machine; a non-ASCII byte crashes `Settings` load).
- **Every candidate-linked table CASCADEs** from `candidates`; DPDP erasure sweeps it.
- **Purity discipline:** `assurance.py` and `otp.py` do no I/O and never read the clock or global RNG — callers pass `at` / `rng`. Coerce datetimes with `as_utc` from `app.ledger.consent` (SQLite returns naive datetimes; S3.1 already solved this).
- **Candidate-plane isolation is structural:** handlers resolve `candidate_id` from `require_candidate`, never from a path or body param. Another candidate's row is an indistinguishable **404**.
- **Commit style:** conventional commits scoped `(s71)`. **Never** add a `Co-Authored-By` trailer.

---

## File Structure

**Create:**

| File | Responsibility |
|---|---|
| `app/verification/__init__.py` | Package marker |
| `app/verification/schema.py` | Contracts + code-constant taxonomies + `METHOD_LEVEL` |
| `app/verification/assurance.py` | Pure, clock-injected expiry + `compute_assurance` |
| `app/verification/otp.py` | Pure OTP mechanics + `Notifier` protocol + `NullNotifier` |
| `app/verification/methods.py` | Adapter protocol + registry + shipped adapters |
| `app/verification/models.py` | `VerificationRow`, `VerificationChallengeRow` |
| `app/verification/store.py` | Persistence, consent enforcement, audit |
| `app/verification/service.py` | Orchestration + `build_verification_service` |
| `alembic/versions/0013_identity_verification.py` | Both tables |
| `scripts/smoke_s71.py` | uvicorn + HTTP smoke |
| `VERIFICATION.md` | Subsystem doc (peer of `LEDGER.md` / `PORTAL.md`) |

**Modify:** `app/ledger/schema.py` (2 new `ConsentPurpose` members) · `app/core/config.py` + `config.yaml` (`verif_*`, `ret_verification_days`) · `app/portal/schema.py` + `service.py` + `retention.py` (`MyData.identity`, retention window) · `app/services/__init__.py` (wiring) · `app/api/routes.py` (6 routes) · `tests/conftest.py` (fixture wiring) · `tests/test_migrations.py` (guards).

---

### Task 1: Contracts, taxonomies, consent purposes, config

**Files:**
- Create: `app/verification/__init__.py`, `app/verification/schema.py`
- Modify: `app/ledger/schema.py` (add 2 `ConsentPurpose` members), `app/core/config.py:155` (after `ret_audit_log_days`), `config.yaml` (after the S6.3 curation block)
- Test: `tests/test_verification_schema.py`, `tests/test_config_verification.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `AssuranceLevel` (IntEnum: `NONE=0`, `SELF_ATTESTED=1`, `CONTACT_CONTROL=2`, `REVIEWED=3`, `GOVERNMENT_ID=4`), `VerificationMethod` (StrEnum: `SELF_ATTESTED="self_attested"`, `OTP_EMAIL="otp_email"`, `OTP_PHONE="otp_phone"`, `MANUAL_REVIEW="manual_review"`, `GOVERNMENT_ID="government_id"`), `VerificationStatus` (StrEnum: `PENDING`/`VERIFIED`/`FAILED`/`EXPIRED`), `METHOD_LEVEL: dict[VerificationMethod, AssuranceLevel]`, `Verification` and `IdentityAssurance` models; `ConsentPurpose.IDENTITY_VERIFY = "identity_verify"` and `ConsentPurpose.VERIFICATION_READ = "verification_read"`; Settings fields `verif_otp_length`, `verif_otp_ttl_minutes`, `verif_otp_max_attempts`, `verif_otp_resend_cooldown_seconds`, `verif_outcome_ttl_days`, `verif_otp_debug_echo`, `ret_verification_days`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_verification_schema.py`:

```python
"""S7.1 contracts: the assurance ladder is ordered, and the taxonomy is closed."""

from app.ledger.schema import ConsentPurpose
from app.verification.schema import (
    METHOD_LEVEL, AssuranceLevel, IdentityAssurance, Verification,
    VerificationMethod, VerificationStatus,
)


def test_assurance_levels_are_ordered_so_highest_held_is_a_max():
    # IntEnum: ordering is semantic here -- "highest level held" must be a max().
    assert AssuranceLevel.NONE < AssuranceLevel.SELF_ATTESTED
    assert AssuranceLevel.SELF_ATTESTED < AssuranceLevel.CONTACT_CONTROL
    assert AssuranceLevel.CONTACT_CONTROL < AssuranceLevel.REVIEWED
    assert AssuranceLevel.REVIEWED < AssuranceLevel.GOVERNMENT_ID
    assert max([AssuranceLevel.SELF_ATTESTED, AssuranceLevel.REVIEWED]) is AssuranceLevel.REVIEWED


def test_every_method_maps_to_a_level():
    assert set(METHOD_LEVEL) == set(VerificationMethod)
    assert METHOD_LEVEL[VerificationMethod.SELF_ATTESTED] is AssuranceLevel.SELF_ATTESTED
    assert METHOD_LEVEL[VerificationMethod.OTP_EMAIL] is AssuranceLevel.CONTACT_CONTROL
    assert METHOD_LEVEL[VerificationMethod.OTP_PHONE] is AssuranceLevel.CONTACT_CONTROL
    assert METHOD_LEVEL[VerificationMethod.MANUAL_REVIEW] is AssuranceLevel.REVIEWED
    assert METHOD_LEVEL[VerificationMethod.GOVERNMENT_ID] is AssuranceLevel.GOVERNMENT_ID


def test_verification_defaults_carry_no_artifact_fields():
    # The DPDP posture is structural: the ONLY evidence field is a digest.
    fields = set(Verification.model_fields)
    assert "evidence_digest" in fields
    for banned in ("document", "image", "raw", "artifact", "biometric", "file"):
        assert banned not in fields


def test_identity_assurance_is_advisory_and_defaults_to_none_level():
    a = IdentityAssurance(candidate_id="c1")
    assert a.advisory is True
    assert a.level is AssuranceLevel.NONE
    assert a.methods == [] and a.expired_methods == []


def test_verification_status_vocabulary_is_closed():
    assert {s.value for s in VerificationStatus} == {"pending", "verified", "failed", "expired"}


def test_two_new_consent_purposes_exist_without_disturbing_the_old_ones():
    assert ConsentPurpose.IDENTITY_VERIFY.value == "identity_verify"
    assert ConsentPurpose.VERIFICATION_READ.value == "verification_read"
    # S3.1 purposes must keep their exact wire values -- stored grants reference them.
    assert ConsentPurpose.LEDGER_WRITE.value == "ledger_write"
    assert ConsentPurpose.LEDGER_READ.value == "ledger_read"
```

Create `tests/test_config_verification.py`:

```python
"""S7.1 config knobs exist with the documented defaults and bounds."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_verification_defaults(settings):
    assert settings.verif_otp_length == 6
    assert settings.verif_otp_ttl_minutes == 10
    assert settings.verif_otp_max_attempts == 5
    assert settings.verif_otp_resend_cooldown_seconds == 60
    assert settings.verif_outcome_ttl_days == 365
    assert settings.verif_otp_debug_echo is False
    assert settings.ret_verification_days == 1095


def test_otp_length_has_a_floor_so_codes_cannot_be_trivially_guessable():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, verif_otp_length=3)


def test_max_attempts_must_be_at_least_one():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, verif_otp_max_attempts=0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_verification_schema.py tests/test_config_verification.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.verification'`

- [ ] **Step 3: Create the package and contracts**

Create `app/verification/__init__.py`:

```python
"""Verification spine (PI-7). Outcomes only -- never documents or biometrics."""
```

Create `app/verification/schema.py`:

```python
"""S7.1 verification contracts -- the spine PI-7 producers write into.

Taxonomies here are code constants, not config: the assurance ladder is a
reviewed schema decision, never a deploy-time tunable (same stance as
InterviewStage/ConsentPurpose). AssuranceLevel is an IntEnum because ordering
is genuinely semantic -- "the highest level a candidate currently holds" is an
ordinary max().

DPDP posture is STRUCTURAL: the only evidence field is `evidence_digest`, a
sha256 hex string. There is deliberately no field capable of holding a
document, image, or biometric, so a future government-ID adapter cannot
persist one without a migration a reviewer would see.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class AssuranceLevel(IntEnum):
    """Ordered ladder. Higher = stronger evidence that the candidate is who
    they claim. Advisory: a level never gates ranking, matching, or scoring."""

    NONE = 0
    SELF_ATTESTED = 1
    CONTACT_CONTROL = 2
    REVIEWED = 3
    GOVERNMENT_ID = 4


class VerificationMethod(StrEnum):
    SELF_ATTESTED = "self_attested"
    OTP_EMAIL = "otp_email"
    OTP_PHONE = "otp_phone"
    MANUAL_REVIEW = "manual_review"
    GOVERNMENT_ID = "government_id"  # declared; no v0 implementation


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"


METHOD_LEVEL: dict[VerificationMethod, AssuranceLevel] = {
    VerificationMethod.SELF_ATTESTED: AssuranceLevel.SELF_ATTESTED,
    VerificationMethod.OTP_EMAIL: AssuranceLevel.CONTACT_CONTROL,
    VerificationMethod.OTP_PHONE: AssuranceLevel.CONTACT_CONTROL,
    VerificationMethod.MANUAL_REVIEW: AssuranceLevel.REVIEWED,
    VerificationMethod.GOVERNMENT_ID: AssuranceLevel.GOVERNMENT_ID,
}


class Verification(BaseModel):
    """One verification attempt and its outcome."""

    id: str
    candidate_id: str
    method: VerificationMethod
    assurance_level: AssuranceLevel
    status: VerificationStatus
    consent_id: Optional[str] = None       # set only for third-party adapters
    evidence_digest: Optional[str] = None  # sha256 hex; NEVER an artifact
    details: dict = Field(default_factory=dict)  # non-PII
    requested_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class IdentityAssurance(BaseModel):
    """Advisory roll-up of a candidate's verifications. Computed at read time,
    never stored: a stored status would go stale the moment an outcome lapsed."""

    candidate_id: str
    level: AssuranceLevel = AssuranceLevel.NONE
    methods: list[VerificationMethod] = Field(default_factory=list)
    verified_at: Optional[datetime] = None       # most recent contributing outcome
    expired_methods: list[VerificationMethod] = Field(default_factory=list)
    advisory: bool = True
```

- [ ] **Step 4: Add the two consent purposes**

In `app/ledger/schema.py`, replace the `ConsentPurpose` class body with:

```python
class ConsentPurpose(StrEnum):
    """What a grant authorizes. ledger_write = an org may submit interview
    records about the candidate; ledger_read = an org may query the
    candidate's ledger history (enforced at query time in S3.2);
    identity_verify = the platform may verify the candidate's identity via an
    EXTERNAL source (S7.1 -- first-party self-service methods need no grant);
    verification_read = an org may see the candidate's identity assurance."""

    LEDGER_WRITE = "ledger_write"
    LEDGER_READ = "ledger_read"
    IDENTITY_VERIFY = "identity_verify"
    VERIFICATION_READ = "verification_read"
```

- [ ] **Step 5: Add the config knobs**

In `app/core/config.py`, insert immediately after the `ret_audit_log_days` line (currently line 155):

```python

    # --- Identity verification (PI-7, S7.1) -----------------------------------
    # Deterministic, offline: OTP mechanics + how long an outcome stays fresh.
    # verif_otp_debug_echo is DOUBLE-GUARDED at the route: the code is echoed
    # only when env == "local" AND this is true. It exists so the sprint smoke
    # can drive the two-step flow over plain HTTP; production cannot echo.
    verif_otp_length: int = Field(default=6, ge=4, le=10)
    verif_otp_ttl_minutes: int = Field(default=10, ge=1)
    verif_otp_max_attempts: int = Field(default=5, ge=1)
    verif_otp_resend_cooldown_seconds: int = Field(default=60, ge=0)
    verif_outcome_ttl_days: int = Field(default=365, ge=1)
    verif_otp_debug_echo: bool = False
    ret_verification_days: int = Field(default=1095, ge=1)  # 3y, posture only
```

In `config.yaml`, append after the S6.3 curation block (keep comments **ASCII-only**):

```yaml

# --- Identity verification (PI-7) - S7.1 spine + consent-first identity -------
# Deterministic and offline: no vendor, no network, no LLM. Assurance is
# ADVISORY - it never gates matching, ranking, or scoring.
verif_otp_length: 6                    # digits in an OTP challenge
verif_otp_ttl_minutes: 10              # challenge lifetime
verif_otp_max_attempts: 5              # wrong codes before the verification fails
verif_otp_resend_cooldown_seconds: 60  # min gap between challenges on one verification
verif_outcome_ttl_days: 365            # a verified outcome reads as expired after this
verif_otp_debug_echo: false            # local-only echo of the code; see config.py note
ret_verification_days: 1095            # retention window surfaced in the portal
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_verification_schema.py tests/test_config_verification.py -q`
Expected: PASS (9 tests)

- [ ] **Step 7: Run the full suite (the ConsentPurpose change is global)**

Run: `python -m pytest -q`
Expected: PASS — 784 + 9. If any test asserts an exhaustive `ConsentPurpose` membership set, update it to include the two new members; do **not** change the existing wire values.

- [ ] **Step 8: Commit**

```bash
git add app/verification/ app/ledger/schema.py app/core/config.py config.yaml tests/test_verification_schema.py tests/test_config_verification.py
git commit -m "feat(s71): verification contracts, assurance ladder, consent purposes"
```

---

### Task 2: Pure assurance logic

**Files:**
- Create: `app/verification/assurance.py`
- Test: `tests/test_verification_assurance.py`

**Interfaces:**
- Consumes: `Verification`, `IdentityAssurance`, `AssuranceLevel`, `VerificationMethod`, `VerificationStatus`, `METHOD_LEVEL` (Task 1); `as_utc` from `app.ledger.consent`.
- Produces: `is_expired(v: Verification, *, at: datetime) -> bool`, `effective_status(v: Verification, *, at: datetime) -> VerificationStatus`, `compute_assurance(candidate_id: str, verifications: Sequence[Verification], *, at: datetime) -> IdentityAssurance`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_verification_assurance.py`:

```python
"""S7.1 pure assurance folding. No I/O, no clock -- `at` is always injected."""

from datetime import datetime, timedelta, timezone

from app.verification.assurance import compute_assurance, effective_status, is_expired
from app.verification.schema import (
    AssuranceLevel, Verification, VerificationMethod, VerificationStatus,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _v(method, status=VerificationStatus.VERIFIED, *, completed=NOW, expires=None, vid="v1"):
    return Verification(
        id=vid, candidate_id="c1", method=method,
        assurance_level=AssuranceLevel.NONE,  # store stamps the real level; folding uses METHOD_LEVEL
        status=status, requested_at=completed, completed_at=completed,
        expires_at=expires,
    )


def test_no_verifications_is_level_none():
    a = compute_assurance("c1", [], at=NOW)
    assert a.level is AssuranceLevel.NONE
    assert a.methods == [] and a.verified_at is None
    assert a.advisory is True


def test_level_is_the_max_across_verified_methods():
    a = compute_assurance(
        "c1",
        [
            _v(VerificationMethod.SELF_ATTESTED, vid="v1"),
            _v(VerificationMethod.OTP_EMAIL, vid="v2"),
        ],
        at=NOW,
    )
    assert a.level is AssuranceLevel.CONTACT_CONTROL
    assert set(a.methods) == {VerificationMethod.SELF_ATTESTED, VerificationMethod.OTP_EMAIL}


def test_pending_and_failed_outcomes_never_contribute():
    a = compute_assurance(
        "c1",
        [
            _v(VerificationMethod.MANUAL_REVIEW, VerificationStatus.PENDING, vid="v1"),
            _v(VerificationMethod.OTP_PHONE, VerificationStatus.FAILED, vid="v2"),
        ],
        at=NOW,
    )
    assert a.level is AssuranceLevel.NONE
    assert a.methods == []


def test_expiry_is_evaluated_at_read_time_not_read_from_the_stored_status():
    lapsed = _v(VerificationMethod.OTP_EMAIL, expires=NOW - timedelta(days=1))
    assert is_expired(lapsed, at=NOW) is True
    # The row still SAYS verified; the effective status must disagree.
    assert lapsed.status is VerificationStatus.VERIFIED
    assert effective_status(lapsed, at=NOW) is VerificationStatus.EXPIRED

    a = compute_assurance("c1", [lapsed], at=NOW)
    assert a.level is AssuranceLevel.NONE
    assert a.methods == []
    assert a.expired_methods == [VerificationMethod.OTP_EMAIL]


def test_a_lapsed_method_downgrades_but_is_still_reported_for_re_verification():
    a = compute_assurance(
        "c1",
        [
            _v(VerificationMethod.SELF_ATTESTED, expires=NOW + timedelta(days=10), vid="v1"),
            _v(VerificationMethod.MANUAL_REVIEW, expires=NOW - timedelta(days=1), vid="v2"),
        ],
        at=NOW,
    )
    assert a.level is AssuranceLevel.SELF_ATTESTED
    assert a.methods == [VerificationMethod.SELF_ATTESTED]
    assert a.expired_methods == [VerificationMethod.MANUAL_REVIEW]


def test_a_null_expiry_never_lapses():
    assert is_expired(_v(VerificationMethod.SELF_ATTESTED, expires=None), at=NOW) is False


def test_verified_at_is_the_most_recent_contributing_outcome():
    older = _v(VerificationMethod.SELF_ATTESTED, completed=NOW - timedelta(days=5), vid="v1")
    newer = _v(VerificationMethod.OTP_EMAIL, completed=NOW - timedelta(days=1), vid="v2")
    a = compute_assurance("c1", [older, newer], at=NOW)
    assert a.verified_at == NOW - timedelta(days=1)


def test_naive_datetimes_are_treated_as_utc():
    # SQLite hands back naive datetimes even from timezone=True columns (S3.1).
    naive = Verification(
        id="v1", candidate_id="c1", method=VerificationMethod.OTP_EMAIL,
        assurance_level=AssuranceLevel.CONTACT_CONTROL,
        status=VerificationStatus.VERIFIED,
        requested_at=datetime(2026, 7, 31, 11, 0),
        completed_at=datetime(2026, 7, 31, 11, 0),
        expires_at=datetime(2026, 7, 31, 13, 0),
    )
    assert is_expired(naive, at=NOW) is False
    assert compute_assurance("c1", [naive], at=NOW).level is AssuranceLevel.CONTACT_CONTROL


def test_methods_and_expired_methods_are_deduplicated_and_deterministic():
    a = compute_assurance(
        "c1",
        [
            _v(VerificationMethod.OTP_EMAIL, vid="v1"),
            _v(VerificationMethod.OTP_EMAIL, vid="v2"),
        ],
        at=NOW,
    )
    assert a.methods == [VerificationMethod.OTP_EMAIL]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_assurance.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.verification.assurance'`

- [ ] **Step 3: Write the implementation**

Create `app/verification/assurance.py`:

```python
"""Pure assurance folding (S7.1). No I/O, no clock -- the caller passes `at`,
exactly like app/ledger/consent.py.

Expiry is computed at READ time rather than written by a job. There is no
scheduler in this system, so a stored `expired` status would simply be a lie
that nobody corrects; deriving it keeps the answer true at every moment.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from app.ledger.consent import as_utc
from app.verification.schema import (
    METHOD_LEVEL, AssuranceLevel, IdentityAssurance, Verification,
    VerificationMethod, VerificationStatus,
)


def is_expired(v: Verification, *, at: datetime) -> bool:
    """True once `expires_at` has passed. A null expiry never lapses."""
    if v.expires_at is None:
        return False
    return as_utc(v.expires_at) <= as_utc(at)


def effective_status(v: Verification, *, at: datetime) -> VerificationStatus:
    """The status as of `at` -- a stored `verified` past its expiry reads
    EXPIRED, so callers never act on a lapsed outcome."""
    if v.status is VerificationStatus.VERIFIED and is_expired(v, at=at):
        return VerificationStatus.EXPIRED
    return v.status


def compute_assurance(
    candidate_id: str, verifications: Sequence[Verification], *, at: datetime
) -> IdentityAssurance:
    """Fold a candidate's verifications into one advisory assurance.

    Contributing = status VERIFIED and not lapsed. Lapsed methods are reported
    separately (rather than silently dropped) so the portal can prompt a
    re-verify instead of showing an unexplained downgrade.
    """
    level = AssuranceLevel.NONE
    methods: list[VerificationMethod] = []
    expired_methods: list[VerificationMethod] = []
    verified_at: Optional[datetime] = None

    for v in verifications:
        status = effective_status(v, at=at)
        if status is VerificationStatus.VERIFIED:
            if v.method not in methods:
                methods.append(v.method)
            level = max(level, METHOD_LEVEL[v.method])
            if v.completed_at is not None:
                moment = as_utc(v.completed_at)
                if verified_at is None or moment > verified_at:
                    verified_at = moment
        elif status is VerificationStatus.EXPIRED:
            if v.method not in expired_methods:
                expired_methods.append(v.method)

    # A method that is currently held is not "expired" even if an older
    # attempt of the same method lapsed.
    expired_methods = [m for m in expired_methods if m not in methods]

    return IdentityAssurance(
        candidate_id=candidate_id,
        level=level,
        methods=methods,
        verified_at=verified_at,
        expired_methods=expired_methods,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_verification_assurance.py -q`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add app/verification/assurance.py tests/test_verification_assurance.py
git commit -m "feat(s71): pure assurance folding with read-time expiry"
```

---

### Task 3: Pure OTP mechanics + notifier seam

**Files:**
- Create: `app/verification/otp.py`
- Test: `tests/test_verification_otp.py`

**Interfaces:**
- Consumes: nothing from earlier tasks except `Settings` conventions.
- Produces: `generate_code(length: int, *, rng: random.Random) -> str`, `hash_code(code: str, salt: str) -> str`, `is_challenge_expired(expires_at: datetime, *, at: datetime) -> bool`, `attempts_exhausted(attempts: int, max_attempts: int) -> bool`, `cooldown_active(last_sent_at: datetime | None, cooldown_seconds: int, *, at: datetime) -> bool`, `Notifier` protocol (`send(destination: str, code: str, *, channel: str) -> None`), `NullNotifier`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_verification_otp.py`:

```python
"""S7.1 OTP mechanics: pure, deterministic under an injected RNG and clock."""

import random
from datetime import datetime, timedelta, timezone

from app.verification.otp import (
    NullNotifier, attempts_exhausted, cooldown_active, generate_code,
    hash_code, is_challenge_expired,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def test_generate_code_is_all_digits_of_the_requested_length():
    code = generate_code(6, rng=random.Random(1234))
    assert len(code) == 6 and code.isdigit()


def test_generate_code_is_deterministic_under_a_seeded_rng():
    assert generate_code(6, rng=random.Random(1234)) == generate_code(6, rng=random.Random(1234))


def test_generate_code_keeps_leading_zeros():
    # A code rendered as an int would silently shorten; it must stay a string.
    codes = [generate_code(6, rng=random.Random(seed)) for seed in range(300)]
    assert all(len(c) == 6 for c in codes)


def test_hash_code_is_stable_salted_and_hides_the_code():
    digest = hash_code("123456", "salt-a")
    assert digest == hash_code("123456", "salt-a")
    assert digest != hash_code("123456", "salt-b")
    assert digest != hash_code("654321", "salt-a")
    assert len(digest) == 64 and "123456" not in digest


def test_challenge_expiry_is_inclusive_at_the_boundary():
    assert is_challenge_expired(NOW, at=NOW) is True
    assert is_challenge_expired(NOW + timedelta(seconds=1), at=NOW) is False


def test_challenge_expiry_treats_naive_timestamps_as_utc():
    assert is_challenge_expired(datetime(2026, 7, 31, 11, 0), at=NOW) is True


def test_attempts_exhausted_at_the_cap():
    assert attempts_exhausted(4, 5) is False
    assert attempts_exhausted(5, 5) is True
    assert attempts_exhausted(6, 5) is True


def test_cooldown_blocks_a_resend_inside_the_window():
    assert cooldown_active(NOW - timedelta(seconds=30), 60, at=NOW) is True
    assert cooldown_active(NOW - timedelta(seconds=61), 60, at=NOW) is False
    assert cooldown_active(None, 60, at=NOW) is False


def test_zero_cooldown_never_blocks():
    assert cooldown_active(NOW, 0, at=NOW) is False


def test_null_notifier_accepts_a_send_and_records_nothing_sensitive():
    n = NullNotifier()
    n.send("someone@example.com", "123456", channel="email")  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_otp.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.verification.otp'`

- [ ] **Step 3: Write the implementation**

Create `app/verification/otp.py`:

```python
"""Pure OTP mechanics + the delivery seam (S7.1).

No I/O and no ambient randomness: the caller injects `rng` and `at`, so every
path is reproducible under test. Codes are stored only as salted sha256
digests -- the plaintext exists just long enough to hand to a notifier.

This repo has no email/SMS provider and S7.1 does not add one, so the shipped
notifier discards. Real delivery is a PI-8 concern.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta
from typing import Optional, Protocol

import structlog

from app.ledger.consent import as_utc

log = structlog.get_logger(__name__)


def generate_code(length: int, *, rng: random.Random) -> str:
    """A zero-padded numeric code. Kept a string end-to-end: an int would drop
    leading zeros and quietly shorten one code in ten."""
    upper = 10 ** length
    return str(rng.randrange(upper)).zfill(length)


def hash_code(code: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode("utf-8")).hexdigest()


def is_challenge_expired(expires_at: datetime, *, at: datetime) -> bool:
    """Inclusive at the boundary: a challenge is dead the instant it expires."""
    return as_utc(expires_at) <= as_utc(at)


def attempts_exhausted(attempts: int, max_attempts: int) -> bool:
    return attempts >= max_attempts


def cooldown_active(
    last_sent_at: Optional[datetime], cooldown_seconds: int, *, at: datetime
) -> bool:
    """True when a resend would land inside the cooldown window."""
    if last_sent_at is None or cooldown_seconds <= 0:
        return False
    return as_utc(at) < as_utc(last_sent_at) + timedelta(seconds=cooldown_seconds)


class Notifier(Protocol):
    """Delivery seam. Implementations must never persist the code."""

    def send(self, destination: str, code: str, *, channel: str) -> None: ...


class NullNotifier:
    """Ships nothing. Logs the delivery attempt WITHOUT the code or the raw
    destination -- an OTP in the log file is an OTP leak."""

    def send(self, destination: str, code: str, *, channel: str) -> None:
        log.info("verification.otp.dispatch", channel=channel)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_verification_otp.py -q`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add app/verification/otp.py tests/test_verification_otp.py
git commit -m "feat(s71): pure OTP mechanics + null notifier seam"
```

---

### Task 4: Adapter seam + registry

**Files:**
- Create: `app/verification/methods.py`
- Test: `tests/test_verification_methods.py`

**Interfaces:**
- Consumes: `VerificationMethod`, `AssuranceLevel`, `METHOD_LEVEL` (Task 1).
- Produces: `VerificationMethodAdapter` Protocol with attributes `method`, `level`, `third_party: bool`, `challenge_based: bool`; concrete `SelfAttestedAdapter`, `OtpEmailAdapter`, `OtpPhoneAdapter`, `ManualReviewAdapter`, `GovernmentIdAdapter`; `ADAPTERS: dict[VerificationMethod, VerificationMethodAdapter]`; `get_adapter(method: VerificationMethod) -> VerificationMethodAdapter`; `GovernmentIdAdapter.start()` raises `NotImplementedError`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_verification_methods.py`:

```python
"""S7.1 adapter seam: every method resolves; government_id is declared but inert."""

import pytest

from app.verification.methods import ADAPTERS, get_adapter
from app.verification.schema import AssuranceLevel, VerificationMethod


def test_every_method_has_an_adapter():
    assert set(ADAPTERS) == set(VerificationMethod)


def test_adapter_levels_agree_with_the_method_level_map():
    from app.verification.schema import METHOD_LEVEL
    for method, adapter in ADAPTERS.items():
        assert adapter.level is METHOD_LEVEL[method]
        assert adapter.method is method


def test_first_party_methods_are_not_third_party():
    for method in (
        VerificationMethod.SELF_ATTESTED,
        VerificationMethod.OTP_EMAIL,
        VerificationMethod.OTP_PHONE,
        VerificationMethod.MANUAL_REVIEW,
    ):
        assert get_adapter(method).third_party is False


def test_government_id_is_third_party_so_the_spine_gates_it_on_consent():
    adapter = get_adapter(VerificationMethod.GOVERNMENT_ID)
    assert adapter.third_party is True
    assert adapter.level is AssuranceLevel.GOVERNMENT_ID


def test_government_id_is_declared_but_unimplemented():
    with pytest.raises(NotImplementedError):
        get_adapter(VerificationMethod.GOVERNMENT_ID).start()


def test_only_otp_methods_are_challenge_based():
    challenge = {m for m, a in ADAPTERS.items() if a.challenge_based}
    assert challenge == {VerificationMethod.OTP_EMAIL, VerificationMethod.OTP_PHONE}


def test_otp_adapters_declare_their_channel_and_contact_hash_field():
    assert get_adapter(VerificationMethod.OTP_EMAIL).channel == "email"
    assert get_adapter(VerificationMethod.OTP_EMAIL).contact_hash_field == "email_hash"
    assert get_adapter(VerificationMethod.OTP_PHONE).channel == "phone"
    assert get_adapter(VerificationMethod.OTP_PHONE).contact_hash_field == "phone_hash"


def test_get_adapter_rejects_an_unknown_method():
    with pytest.raises(KeyError):
        get_adapter("not_a_method")  # type: ignore[arg-type]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_methods.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.verification.methods'`

- [ ] **Step 3: Write the implementation**

Create `app/verification/methods.py`:

```python
"""Verification method adapters (S7.1) -- the seam a real KYC vendor plugs into.

An adapter declares WHAT a method is, not how the spine treats it. In
particular the consent gate lives in the spine, keyed off `third_party`, never
inside an adapter: a gate an adapter could forget to apply is not a gate.

`GovernmentIdAdapter` is deliberately declared and inert. Shipping the slot
(with its level, its third_party flag, and therefore its consent requirement)
means a real DigiLocker/Aadhaar integration is later a new adapter rather than
a schema migration plus a consent retrofit.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from app.verification.schema import AssuranceLevel, VerificationMethod


@runtime_checkable
class VerificationMethodAdapter(Protocol):
    method: VerificationMethod
    level: AssuranceLevel
    third_party: bool     # True => spine requires an IDENTITY_VERIFY grant
    challenge_based: bool  # True => two-step start/confirm


class _Base:
    method: VerificationMethod
    level: AssuranceLevel
    third_party: bool = False
    challenge_based: bool = False
    channel: Optional[str] = None
    contact_hash_field: Optional[str] = None


class SelfAttestedAdapter(_Base):
    """The candidate asserts their own identity. Weakest rung, but a real one:
    it records that the claim was made, by whom, and when."""

    method = VerificationMethod.SELF_ATTESTED
    level = AssuranceLevel.SELF_ATTESTED


class OtpEmailAdapter(_Base):
    method = VerificationMethod.OTP_EMAIL
    level = AssuranceLevel.CONTACT_CONTROL
    challenge_based = True
    channel = "email"
    contact_hash_field = "email_hash"


class OtpPhoneAdapter(_Base):
    method = VerificationMethod.OTP_PHONE
    level = AssuranceLevel.CONTACT_CONTROL
    challenge_based = True
    channel = "phone"
    contact_hash_field = "phone_hash"


class ManualReviewAdapter(_Base):
    """An operator checked something out of band and recorded the outcome."""

    method = VerificationMethod.MANUAL_REVIEW
    level = AssuranceLevel.REVIEWED


class GovernmentIdAdapter(_Base):
    """DECLARED, NOT IMPLEMENTED. Needs a vendor and a legal review of
    DigiLocker API terms (gap-analysis section 8). No route reaches it."""

    method = VerificationMethod.GOVERNMENT_ID
    level = AssuranceLevel.GOVERNMENT_ID
    third_party = True

    def start(self, *args, **kwargs):
        raise NotImplementedError(
            "government_id verification needs a KYC vendor + legal review (PI-8+)"
        )


ADAPTERS: dict[VerificationMethod, _Base] = {
    VerificationMethod.SELF_ATTESTED: SelfAttestedAdapter(),
    VerificationMethod.OTP_EMAIL: OtpEmailAdapter(),
    VerificationMethod.OTP_PHONE: OtpPhoneAdapter(),
    VerificationMethod.MANUAL_REVIEW: ManualReviewAdapter(),
    VerificationMethod.GOVERNMENT_ID: GovernmentIdAdapter(),
}


def get_adapter(method: VerificationMethod) -> _Base:
    """KeyError for anything outside the taxonomy -- callers validate first."""
    return ADAPTERS[method]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_verification_methods.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add app/verification/methods.py tests/test_verification_methods.py
git commit -m "feat(s71): verification method adapter seam + registry"
```

---

### Task 5: ORM models + migration 0013 + drift guards

**Files:**
- Create: `app/verification/models.py`, `alembic/versions/0013_identity_verification.py`
- Modify: `tests/test_migrations.py:15` (import), `:49` (table assertion), `:81` (table tuple), `:89`, `:108`; `tests/conftest.py:19` (import)
- Test: `tests/test_verification_models.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (ORM is independent of the pydantic contracts).
- Produces: `VerificationRow` (table `verifications`) and `VerificationChallengeRow` (table `verification_challenges`), both on the shared `Base`. Columns as listed in Step 3.

- [ ] **Step 1: Write the failing test**

Create `tests/test_verification_models.py`:

```python
"""S7.1 ORM: CASCADE from the candidate, and no column can hold an artifact."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.candidates.models import CandidateRow
from app.core.db import Base, make_engine, make_session_factory
from app.verification.models import VerificationChallengeRow, VerificationRow

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _candidate(session, cid="c1"):
    session.add(CandidateRow(id=cid, full_name="A Candidate"))
    session.commit()
    return cid


def test_tables_exist_with_the_expected_names():
    assert VerificationRow.__tablename__ == "verifications"
    assert VerificationChallengeRow.__tablename__ == "verification_challenges"


def test_verification_row_has_no_column_able_to_hold_a_document():
    cols = set(VerificationRow.__table__.columns.keys())
    assert "evidence_digest" in cols
    for banned in ("document", "image", "raw", "artifact", "biometric", "file", "payload"):
        assert banned not in cols


def test_erasing_the_candidate_cascades_verifications_and_challenges():
    factory = _factory()
    with factory() as s:
        _candidate(s)
        v = VerificationRow(
            id="v1", candidate_id="c1", method="otp_email",
            assurance_level=2, status="pending", requested_at=NOW,
        )
        s.add(v)
        s.commit()
        s.add(
            VerificationChallengeRow(
                id="ch1", verification_id="v1", code_hash="d" * 64, channel="email",
                destination_hash="e" * 64, attempts=0, max_attempts=5,
                expires_at=NOW + timedelta(minutes=10), last_sent_at=NOW,
            )
        )
        s.commit()

        s.delete(s.get(CandidateRow, "c1"))
        s.commit()

        assert s.execute(select(VerificationRow)).scalars().all() == []
        assert s.execute(select(VerificationChallengeRow)).scalars().all() == []


def test_deleting_a_verification_cascades_its_challenges():
    factory = _factory()
    with factory() as s:
        _candidate(s)
        s.add(
            VerificationRow(
                id="v1", candidate_id="c1", method="otp_email",
                assurance_level=2, status="pending", requested_at=NOW,
            )
        )
        s.commit()
        s.add(
            VerificationChallengeRow(
                id="ch1", verification_id="v1", code_hash="d" * 64, channel="email",
                destination_hash="e" * 64, attempts=0, max_attempts=5,
                expires_at=NOW + timedelta(minutes=10), last_sent_at=NOW,
            )
        )
        s.commit()

        s.delete(s.get(VerificationRow, "v1"))
        s.commit()
        assert s.execute(select(VerificationChallengeRow)).scalars().all() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.verification.models'`

- [ ] **Step 3: Write the models**

Create `app/verification/models.py`:

```python
"""ORM rows for the verification spine (S7.1). Postgres-shaped on SQLite.

Two tables on purpose. `verifications` is a durable outcome; a challenge is
short-lived secret material with a create -> consume -> delete lifecycle. Their
sensitivity and their retention story are categorically different, and keeping
them apart means the challenge table can be dropped wholesale later at no cost.

NOTE the absent columns: nothing here can hold a document, image, or biometric.
The single evidence field is a sha256 digest. That is the DPDP posture made
structural rather than procedural.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VerificationRow(Base):
    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(32), index=True)
    assurance_level: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)
    # Set only for third-party adapters -- the IDENTITY_VERIFY grant that
    # authorized the pull. NOT a FK: consent rows are erased on DPDP delete
    # while an audit-bearing verification row may outlive that cascade order.
    consent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    evidence_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VerificationChallengeRow(Base):
    __tablename__ = "verification_challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    verification_id: Mapped[str] = mapped_column(
        ForeignKey("verifications.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(16))
    # Salted hash of the destination the code went to (S1.1 contact_hash). The
    # raw email/phone is used transiently for delivery and never persisted.
    destination_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 4: Write the migration**

Create `alembic/versions/0013_identity_verification.py`:

```python
"""identity verification spine: outcomes + short-lived OTP challenges (S7.1)

Revision ID: 0013_identity_verification
Revises: 0012_candidate_credentials
Create Date: 2026-07-31

Both tables CASCADE to the candidate so DPDP erasure sweeps them. No column on
either table can hold a document or biometric -- outcomes only, by design.
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_identity_verification"
down_revision = "0012_candidate_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id", sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("assurance_level", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("consent_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_digest", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_verifications_candidate_id", "verifications", ["candidate_id"])
    op.create_index("ix_verifications_method", "verifications", ["method"])
    op.create_index("ix_verifications_status", "verifications", ["status"])

    op.create_table(
        "verification_challenges",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "verification_id", sa.String(length=36),
            sa.ForeignKey("verifications.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("destination_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_verification_challenges_verification_id",
        "verification_challenges", ["verification_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_verification_challenges_verification_id", table_name="verification_challenges"
    )
    op.drop_table("verification_challenges")
    op.drop_index("ix_verifications_status", table_name="verifications")
    op.drop_index("ix_verifications_method", table_name="verifications")
    op.drop_index("ix_verifications_candidate_id", table_name="verifications")
    op.drop_table("verifications")
```

- [ ] **Step 5: Extend the drift/index/FK guards**

In `tests/test_migrations.py`, add after line 16 (`import app.curation.models  # noqa: F401 ...`):

```python
import app.verification.models  # noqa: F401 — populate Base.metadata
```

Add after line 49 (`assert "candidate_credentials" in names  # S6.4 migration 0012`):

```python
    assert "verifications" in names  # S7.1 migration 0013
    assert "verification_challenges" in names  # S7.1 migration 0013
```

Add after the `CANDIDATE_AUTH_TABLES` definition:

```python
VERIFICATION_TABLES = ("verifications", "verification_challenges")  # S7.1 — CASCADE
```

In **both** `test_migrated_indexes_match_orm` and `test_migrated_fks_and_nullability_match_orm`, append `+ VERIFICATION_TABLES` to the `for table in ...` tuple expression.

In `tests/conftest.py`, add after line 19 (`import app.curation.models ...`):

```python
import app.verification.models  # noqa: F401 — populate Base.metadata with verification tables
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_verification_models.py tests/test_migrations.py -q`
Expected: PASS. If the drift guard reports a mismatch, fix the **migration** to match the models — the models are the source of truth.

- [ ] **Step 7: Verify the migration runs standalone**

Run: `python -c "from alembic.config import Config; from alembic import command; import tempfile, os; d=tempfile.mkdtemp(); c=Config('alembic.ini'); c.set_main_option('sqlalchemy.url','sqlite:///'+os.path.join(d,'t.db').replace('\\\\','/')); command.upgrade(c,'head'); print('upgrade ok')"`
Expected: `upgrade ok`

- [ ] **Step 8: Commit**

```bash
git add app/verification/models.py alembic/versions/0013_identity_verification.py tests/test_verification_models.py tests/test_migrations.py tests/conftest.py
git commit -m "feat(s71): verification tables + migration 0013 with CASCADE guards"
```

---

### Task 6: VerificationStore — persistence, challenges, audit

**Files:**
- Create: `app/verification/store.py`
- Test: `tests/test_verification_store.py`

**Interfaces:**
- Consumes: `VerificationRow`/`VerificationChallengeRow` (Task 5), `Verification`/`VerificationStatus`/`VerificationMethod`/`AssuranceLevel`/`METHOD_LEVEL` (Task 1), `compute_assurance` (Task 2), `otp` helpers (Task 3), `LedgerStore` (for `_audit`).
- Produces: `VerificationStore(session_factory, *, ledger, settings=None)` with `create_verification(...) -> Verification`, `get_verification(verification_id) -> Optional[Verification]`, `verifications_for_candidate(candidate_id) -> list[Verification]`, `complete_verification(verification_id, *, status, evidence_digest=None, details=None, at=None) -> Verification`, `create_challenge(...) -> str` (returns plaintext code), `confirm_challenge(verification_id, code, *, at=None) -> Verification`, `assurance_for_candidate(candidate_id, *, at=None) -> IdentityAssurance`. Raises `ChallengeError` (new, exported) for wrong/expired/exhausted codes and `LookupError` for unknown ids.

- [ ] **Step 1: Write the failing test**

Create `tests/test_verification_store.py`:

```python
"""S7.1 store: outcomes persist, challenges are consumed, every write is audited."""

import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.ledger.store import LedgerStore
from app.verification.models import VerificationChallengeRow
from app.verification.schema import (
    AssuranceLevel, VerificationMethod, VerificationStatus,
)
from app.verification.store import ChallengeError, VerificationStore
from tests.conftest import make_candidate_store

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store_bundle(settings):
    candidates = make_candidate_store()
    ledger = LedgerStore(
        candidates._session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        settings=settings,
    )
    store = VerificationStore(candidates._session_factory, ledger=ledger, settings=settings)
    return candidates, ledger, store


def _candidate(candidates, email="dev@example.com"):
    from app.candidates.models import CandidateRow
    with candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash="e" * 64)
        s.add(row)
        s.commit()
        return row.id


def test_create_verification_persists_and_stamps_the_level(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    assert v.candidate_id == cid
    assert v.status is VerificationStatus.PENDING
    assert v.assurance_level is AssuranceLevel.CONTACT_CONTROL
    assert store.get_verification(v.id).id == v.id


def test_create_verification_rejects_an_unknown_candidate(store_bundle):
    _, _, store = store_bundle
    with pytest.raises(LookupError):
        store.create_verification(
            candidate_id="nope", method=VerificationMethod.SELF_ATTESTED, at=NOW
        )


def test_complete_sets_status_completed_at_and_an_expiry_from_config(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.SELF_ATTESTED, at=NOW
    )
    done = store.complete_verification(v.id, status=VerificationStatus.VERIFIED, at=NOW)
    assert done.status is VerificationStatus.VERIFIED
    assert done.completed_at is not None
    assert done.expires_at is not None  # verif_outcome_ttl_days from NOW


def test_every_mutation_writes_an_audit_row(store_bundle):
    candidates, ledger, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.SELF_ATTESTED, at=NOW
    )
    store.complete_verification(v.id, status=VerificationStatus.VERIFIED, at=NOW)
    actions = [e.action for e in ledger.audit_for_candidate(cid)]
    assert "verification.start" in actions
    assert "verification.complete" in actions


def test_confirm_with_the_right_code_verifies_and_deletes_the_challenge(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    code = store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    done = store.confirm_challenge(v.id, code, at=NOW)
    assert done.status is VerificationStatus.VERIFIED
    with store._session_factory() as s:  # consumed challenges are DELETED
        assert s.execute(select(VerificationChallengeRow)).scalars().all() == []


def test_a_wrong_code_raises_increments_attempts_and_leaves_it_pending(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    with pytest.raises(ChallengeError):
        store.confirm_challenge(v.id, "000000000"[: 6], at=NOW)
    assert store.get_verification(v.id).status is VerificationStatus.PENDING
    with store._session_factory() as s:
        ch = s.execute(select(VerificationChallengeRow)).scalars().one()
        assert ch.attempts == 1


def test_exhausting_attempts_fails_the_verification(store_bundle, settings):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    code = store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    wrong = "1" * len(code) if code != "1" * len(code) else "2" * len(code)
    for _ in range(settings.verif_otp_max_attempts):
        with pytest.raises(ChallengeError):
            store.confirm_challenge(v.id, wrong, at=NOW)
    assert store.get_verification(v.id).status is VerificationStatus.FAILED


def test_an_expired_challenge_is_refused(store_bundle, settings):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    code = store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    later = NOW + timedelta(minutes=settings.verif_otp_ttl_minutes + 1)
    with pytest.raises(ChallengeError):
        store.confirm_challenge(v.id, code, at=later)


def test_a_resend_inside_the_cooldown_is_refused(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    with pytest.raises(ChallengeError):
        store.create_challenge(
            verification_id=v.id, channel="email", destination_hash="e" * 64,
            rng=random.Random(8), at=NOW + timedelta(seconds=5),
        )


def test_a_resend_after_the_cooldown_replaces_the_old_challenge(store_bundle, settings):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    later = NOW + timedelta(seconds=settings.verif_otp_resend_cooldown_seconds + 1)
    code2 = store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(8), at=later,
    )
    with store._session_factory() as s:  # exactly one live challenge, the new one
        rows = s.execute(select(VerificationChallengeRow)).scalars().all()
        assert len(rows) == 1
    assert store.confirm_challenge(v.id, code2, at=later).status is VerificationStatus.VERIFIED


def test_the_raw_code_is_never_persisted(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.OTP_EMAIL, at=NOW
    )
    code = store.create_challenge(
        verification_id=v.id, channel="email", destination_hash="e" * 64,
        rng=random.Random(7), at=NOW,
    )
    with store._session_factory() as s:
        ch = s.execute(select(VerificationChallengeRow)).scalars().one()
        assert code not in ch.code_hash
        assert len(ch.code_hash) == 64


def test_assurance_for_candidate_folds_stored_outcomes(store_bundle):
    candidates, _, store = store_bundle
    cid = _candidate(candidates)
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.SELF_ATTESTED, at=NOW
    )
    store.complete_verification(v.id, status=VerificationStatus.VERIFIED, at=NOW)
    a = store.assurance_for_candidate(cid, at=NOW)
    assert a.level is AssuranceLevel.SELF_ATTESTED
    assert a.advisory is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.verification.store'`

- [ ] **Step 3: Write the implementation**

Create `app/verification/store.py`:

```python
"""Verification persistence + audit (S7.1).

Mirrors LedgerStore's discipline: every mutation is audited in the SAME
transaction as the write, so an outcome can never exist without its trail.
Audit rows go to the shared `audit_log` via LedgerStore._audit, which is what
makes verifications show up in the candidate's own DPDP access log for free.

Challenge hygiene is real deletion, not a retention policy: a consumed or
superseded OTP is secret material with no reason to survive, and it is removed
on paths that already run, so no scheduler is needed.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.candidates.models import CandidateRow
from app.core.config import Settings, get_settings
from app.ledger.consent import as_utc
from app.ledger.store import LedgerStore
from app.verification import otp as otp_logic
from app.verification.assurance import compute_assurance
from app.verification.models import VerificationChallengeRow, VerificationRow
from app.verification.schema import (
    METHOD_LEVEL, AssuranceLevel, IdentityAssurance, Verification,
    VerificationMethod, VerificationStatus,
)


class ChallengeError(Exception):
    """A challenge could not be issued or confirmed (wrong/expired/exhausted/
    cooling down). Carries no information about the correct code."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _verification(row: VerificationRow) -> Verification:
    return Verification(
        id=row.id,
        candidate_id=row.candidate_id,
        method=VerificationMethod(row.method),
        assurance_level=AssuranceLevel(row.assurance_level),
        status=VerificationStatus(row.status),
        consent_id=row.consent_id,
        evidence_digest=row.evidence_digest,
        details=row.details or {},
        requested_at=as_utc(row.requested_at),
        completed_at=as_utc(row.completed_at) if row.completed_at else None,
        expires_at=as_utc(row.expires_at) if row.expires_at else None,
    )


class VerificationStore:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        ledger: LedgerStore,
        settings: Optional[Settings] = None,
    ) -> None:
        self._session_factory = session_factory
        self._ledger = ledger
        self._settings = settings or get_settings()

    # -- outcomes -------------------------------------------------------------

    def create_verification(
        self,
        *,
        candidate_id: str,
        method: VerificationMethod,
        consent_id: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> Verification:
        moment = as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            row = VerificationRow(
                id=str(uuid.uuid4()),
                candidate_id=candidate_id,
                method=method.value,
                assurance_level=int(METHOD_LEVEL[method]),
                status=VerificationStatus.PENDING.value,
                consent_id=consent_id,
                details={},
                requested_at=moment,
            )
            session.add(row)
            session.flush()
            self._ledger._audit(
                session,
                actor_type="candidate",
                actor_id=candidate_id,
                action="verification.start",
                entity_type="verification",
                entity_id=row.id,
                candidate_id=candidate_id,
                details={"method": method.value, "third_party": consent_id is not None},
            )
            session.commit()
            return _verification(row)

    def get_verification(self, verification_id: str) -> Optional[Verification]:
        with self._session_factory() as session:
            row = session.get(VerificationRow, verification_id)
            return _verification(row) if row else None

    def verifications_for_candidate(self, candidate_id: str) -> list[Verification]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(VerificationRow)
                    .where(VerificationRow.candidate_id == candidate_id)
                    .order_by(VerificationRow.requested_at, VerificationRow.id)
                ).scalars().all()
            )
            return [_verification(r) for r in rows]

    def complete_verification(
        self,
        verification_id: str,
        *,
        status: VerificationStatus,
        evidence_digest: Optional[str] = None,
        details: Optional[dict] = None,
        at: Optional[datetime] = None,
    ) -> Verification:
        moment = as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            row = session.get(VerificationRow, verification_id)
            if row is None:
                raise LookupError(f"unknown verification: {verification_id}")
            row.status = status.value
            row.completed_at = moment
            if status is VerificationStatus.VERIFIED:
                row.expires_at = moment + timedelta(
                    days=self._settings.verif_outcome_ttl_days
                )
            if evidence_digest is not None:
                row.evidence_digest = evidence_digest
            if details:
                row.details = {**(row.details or {}), **details}
            self._ledger._audit(
                session,
                actor_type="system",
                actor_id=None,
                action="verification.complete",
                entity_type="verification",
                entity_id=row.id,
                candidate_id=row.candidate_id,
                details={"method": row.method, "status": status.value},
            )
            session.commit()
            return _verification(row)

    # -- challenges (short-lived secret material) ------------------------------

    def create_challenge(
        self,
        *,
        verification_id: str,
        channel: str,
        destination_hash: str,
        rng: Optional[random.Random] = None,
        at: Optional[datetime] = None,
    ) -> str:
        """Issue a code and return the PLAINTEXT once, for immediate delivery.
        Only its salted digest is stored. A prior challenge on the same
        verification is deleted, so exactly one code is ever live."""
        moment = as_utc(at) if at else _utcnow()
        rng = rng or random.SystemRandom()
        s = self._settings
        with self._session_factory() as session:
            row = session.get(VerificationRow, verification_id)
            if row is None:
                raise LookupError(f"unknown verification: {verification_id}")
            existing = (
                session.execute(
                    select(VerificationChallengeRow).where(
                        VerificationChallengeRow.verification_id == verification_id
                    )
                ).scalars().all()
            )
            for prior in existing:
                if otp_logic.cooldown_active(
                    prior.last_sent_at, s.verif_otp_resend_cooldown_seconds, at=moment
                ):
                    raise ChallengeError("a code was sent recently; try again shortly")
                session.delete(prior)
            session.flush()

            code = otp_logic.generate_code(s.verif_otp_length, rng=rng)
            session.add(
                VerificationChallengeRow(
                    id=str(uuid.uuid4()),
                    verification_id=verification_id,
                    code_hash=otp_logic.hash_code(code, s.contact_hash_salt),
                    channel=channel,
                    destination_hash=destination_hash,
                    attempts=0,
                    max_attempts=s.verif_otp_max_attempts,
                    expires_at=moment + timedelta(minutes=s.verif_otp_ttl_minutes),
                    last_sent_at=moment,
                )
            )
            session.commit()
            return code

    def confirm_challenge(
        self, verification_id: str, code: str, *, at: Optional[datetime] = None
    ) -> Verification:
        moment = as_utc(at) if at else _utcnow()
        s = self._settings
        with self._session_factory() as session:
            row = session.get(VerificationRow, verification_id)
            if row is None:
                raise LookupError(f"unknown verification: {verification_id}")
            challenge = (
                session.execute(
                    select(VerificationChallengeRow).where(
                        VerificationChallengeRow.verification_id == verification_id
                    )
                ).scalars().first()
            )
            if challenge is None:
                raise ChallengeError("no active challenge")
            if otp_logic.is_challenge_expired(challenge.expires_at, at=moment):
                session.delete(challenge)
                session.commit()
                raise ChallengeError("challenge expired")

            if otp_logic.hash_code(code or "", s.contact_hash_salt) != challenge.code_hash:
                challenge.attempts += 1
                exhausted = otp_logic.attempts_exhausted(
                    challenge.attempts, challenge.max_attempts
                )
                if exhausted:
                    row.status = VerificationStatus.FAILED.value
                    row.completed_at = moment
                    session.delete(challenge)
                    self._ledger._audit(
                        session,
                        actor_type="candidate",
                        actor_id=row.candidate_id,
                        action="verification.complete",
                        entity_type="verification",
                        entity_id=row.id,
                        candidate_id=row.candidate_id,
                        details={"method": row.method, "status": "failed",
                                 "reason": "attempts_exhausted"},
                    )
                session.commit()
                raise ChallengeError(
                    "incorrect code" if not exhausted else "too many attempts"
                )

            row.status = VerificationStatus.VERIFIED.value
            row.completed_at = moment
            row.expires_at = moment + timedelta(days=s.verif_outcome_ttl_days)
            session.delete(challenge)  # consumed secret material: gone
            self._ledger._audit(
                session,
                actor_type="candidate",
                actor_id=row.candidate_id,
                action="verification.complete",
                entity_type="verification",
                entity_id=row.id,
                candidate_id=row.candidate_id,
                details={"method": row.method, "status": "verified"},
            )
            session.commit()
            return _verification(row)

    # -- roll-up ---------------------------------------------------------------

    def assurance_for_candidate(
        self, candidate_id: str, *, at: Optional[datetime] = None
    ) -> IdentityAssurance:
        moment = as_utc(at) if at else _utcnow()
        return compute_assurance(
            candidate_id, self.verifications_for_candidate(candidate_id), at=moment
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_verification_store.py -q`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add app/verification/store.py tests/test_verification_store.py
git commit -m "feat(s71): verification store with audited writes + challenge hygiene"
```

---

### Task 7: Consent-gated org read

**Files:**
- Modify: `app/verification/store.py` (add one method)
- Test: `tests/test_verification_consent.py`

**Interfaces:**
- Consumes: everything from Task 6; `check_consent`/`ConsentError` from the ledger.
- Produces: `VerificationStore.assurance_for_org(*, org_id: str, candidate_id: str, at: datetime | None = None) -> IdentityAssurance` — raises `ConsentError` without an active `VERIFICATION_READ` grant, `LookupError` for an unknown org or candidate; audits **every** attempt as `verification.query`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_verification_consent.py`:

```python
"""S7.1 org-plane disclosure: gated on VERIFICATION_READ, audited either way."""

from datetime import datetime, timezone

import pytest

from app.candidates.models import CandidateRow
from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError, LedgerStore
from app.verification.schema import (
    AssuranceLevel, VerificationMethod, VerificationStatus,
)
from app.verification.store import VerificationStore
from tests.conftest import make_candidate_store

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def bundle(settings):
    candidates = make_candidate_store()
    ledger = LedgerStore(
        candidates._session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        settings=settings,
    )
    store = VerificationStore(candidates._session_factory, ledger=ledger, settings=settings)
    with candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash="e" * 64)
        s.add(row)
        s.commit()
        cid = row.id
    org = ledger.create_organization("Acme Corp")
    v = store.create_verification(
        candidate_id=cid, method=VerificationMethod.SELF_ATTESTED, at=NOW
    )
    store.complete_verification(v.id, status=VerificationStatus.VERIFIED, at=NOW)
    return candidates, ledger, store, cid, org.id


def test_without_a_grant_the_read_is_refused(bundle):
    _, _, store, cid, org_id = bundle
    with pytest.raises(ConsentError):
        store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)


def test_a_ledger_read_grant_does_not_unlock_verification(bundle):
    # The whole point of a separate purpose: an existing grant must not silently
    # widen to cover identity assurance.
    _, ledger, store, cid, org_id = bundle
    ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.LEDGER_READ, org_id=org_id
    )
    with pytest.raises(ConsentError):
        store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)


def test_with_a_verification_read_grant_the_assurance_is_disclosed(bundle):
    _, ledger, store, cid, org_id = bundle
    ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=org_id
    )
    a = store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)
    assert a.level is AssuranceLevel.SELF_ATTESTED
    assert a.advisory is True


def test_revocation_closes_the_disclosure_again(bundle):
    _, ledger, store, cid, org_id = bundle
    grant = ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=org_id
    )
    store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)
    ledger.revoke_consent(grant.id)
    with pytest.raises(ConsentError):
        store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)


def test_both_allowed_and_denied_attempts_are_audited(bundle):
    _, ledger, store, cid, org_id = bundle
    with pytest.raises(ConsentError):
        store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)
    ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=org_id
    )
    store.assurance_for_org(org_id=org_id, candidate_id=cid, at=NOW)

    queries = [e for e in ledger.audit_for_candidate(cid) if e.action == "verification.query"]
    assert len(queries) == 2
    assert [q.details.get("allowed") for q in queries] == [False, True]
    assert all(q.actor_type == "org" and q.actor_id == org_id for q in queries)


def test_unknown_org_and_unknown_candidate_raise_lookup_error(bundle):
    _, _, store, cid, org_id = bundle
    with pytest.raises(LookupError):
        store.assurance_for_org(org_id="nope", candidate_id=cid, at=NOW)
    with pytest.raises(LookupError):
        store.assurance_for_org(org_id=org_id, candidate_id="nope", at=NOW)


def test_a_wildcard_grant_covers_any_org(bundle):
    _, ledger, store, cid, org_id = bundle
    ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=None
    )
    assert store.assurance_for_org(
        org_id=org_id, candidate_id=cid, at=NOW
    ).level is AssuranceLevel.SELF_ATTESTED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_consent.py -q`
Expected: FAIL — `AttributeError: 'VerificationStore' object has no attribute 'assurance_for_org'`

- [ ] **Step 3: Write the implementation**

Add these imports to `app/verification/store.py`:

```python
from app.ledger import consent as consent_logic
from app.ledger.models import OrganizationRow
from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError
```

Append this method to `VerificationStore` (after `assurance_for_candidate`):

```python
    def assurance_for_org(
        self, *, org_id: str, candidate_id: str, at: Optional[datetime] = None
    ) -> IdentityAssurance:
        """Query-time DPDP gate, mirroring LedgerStore.query_records_for_org: an
        org sees assurance only under an active VERIFICATION_READ grant, and
        EVERY attempt -- allowed or denied -- is audited in the same
        transaction, because surveillance must itself be observable.

        Returns the advisory roll-up only. Never the evidence digests, the
        destination hashes, or the individual attempt rows.
        """
        moment = as_utc(at) if at else _utcnow()
        with self._session_factory() as session:
            if session.get(OrganizationRow, org_id) is None:
                raise LookupError(f"unknown organization: {org_id}")
            if session.get(CandidateRow, candidate_id) is None:
                raise LookupError(f"unknown candidate: {candidate_id}")
            grants = self._ledger._grants_for(
                session, candidate_id, ConsentPurpose.VERIFICATION_READ
            )
            decision = consent_logic.check_consent(
                grants, org_id=org_id, purpose=ConsentPurpose.VERIFICATION_READ, at=moment
            )
            if not decision.allowed:
                self._ledger._audit(
                    session,
                    actor_type="org",
                    actor_id=org_id,
                    action="verification.query",
                    entity_type="candidate",
                    entity_id=candidate_id,
                    candidate_id=candidate_id,
                    details={"allowed": False, "purpose": "verification_read"},
                )
                session.commit()
                raise ConsentError(decision.reason)

            rows = (
                session.execute(
                    select(VerificationRow)
                    .where(VerificationRow.candidate_id == candidate_id)
                    .order_by(VerificationRow.requested_at, VerificationRow.id)
                ).scalars().all()
            )
            assurance = compute_assurance(
                candidate_id, [_verification(r) for r in rows], at=moment
            )
            self._ledger._audit(
                session,
                actor_type="org",
                actor_id=org_id,
                action="verification.query",
                entity_type="candidate",
                entity_id=candidate_id,
                candidate_id=candidate_id,
                details={
                    "allowed": True,
                    "consent_id": decision.grant_id,
                    "level": int(assurance.level),
                },
            )
            session.commit()
            return assurance
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_verification_consent.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add app/verification/store.py tests/test_verification_consent.py
git commit -m "feat(s71): consent-gated org-plane assurance read, audited both ways"
```

---

### Task 8: VerificationService + wiring

**Files:**
- Create: `app/verification/service.py`
- Modify: `app/services/__init__.py` (TYPE_CHECKING import, dataclass field, function-local build), `tests/conftest.py` (`make_services` param + default)
- Test: `tests/test_verification_service.py`

**Interfaces:**
- Consumes: `VerificationStore` (Tasks 6–7), `get_adapter`/`ADAPTERS` (Task 4), `otp` (Task 3), `CandidateStore`, `LedgerStore`.
- Produces: `VerificationService(store, candidates, ledger, *, notifier=None, settings=None)` with `start(candidate_id, method, *, destination=None, rng=None, at=None) -> tuple[Verification, Optional[str]]` (the str is the plaintext code, for the double-guarded debug echo only), `confirm(candidate_id, verification_id, code, *, at=None) -> Verification`, `list_for_candidate(candidate_id, *, at=None) -> tuple[list[Verification], IdentityAssurance]`, `record_manual_review(candidate_id, *, outcome, note=None, evidence_digest=None, at=None) -> Verification`, `assurance_for_org(...)` (delegate). Raises `DestinationError` (new, exported), `ConsentError`, `ChallengeError`, `LookupError`. Also `build_verification_service(settings=None, *, candidates, ledger) -> VerificationService`. `Services.verification` field.

- [ ] **Step 1: Write the failing test**

Create `tests/test_verification_service.py`:

```python
"""S7.1 orchestration: destination binding, the third-party consent gate, isolation."""

import random
from datetime import datetime, timezone

import pytest

from app.candidates.hashing import contact_hash, normalize_email
from app.candidates.models import CandidateRow
from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError, LedgerStore
from app.verification.schema import (
    AssuranceLevel, VerificationMethod, VerificationStatus,
)
from app.verification.service import DestinationError, VerificationService
from app.verification.store import VerificationStore
from tests.conftest import make_candidate_store

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
EMAIL = "dev@example.com"


@pytest.fixture
def svc(settings):
    candidates = make_candidate_store()
    ledger = LedgerStore(
        candidates._session_factory,
        default_consent_ttl_days=settings.ledger_consent_default_ttl_days,
        settings=settings,
    )
    store = VerificationStore(candidates._session_factory, ledger=ledger, settings=settings)
    service = VerificationService(store, candidates, ledger, settings=settings)
    with candidates._session_factory() as s:
        row = CandidateRow(
            full_name="A Candidate",
            email_hash=contact_hash(normalize_email(EMAIL), settings.contact_hash_salt),
        )
        s.add(row)
        s.commit()
        cid = row.id
    return service, ledger, cid


def test_self_attest_completes_immediately(svc):
    service, _, cid = svc
    v, code = service.start(cid, VerificationMethod.SELF_ATTESTED, at=NOW)
    assert code is None
    assert v.status is VerificationStatus.VERIFIED
    assert v.assurance_level is AssuranceLevel.SELF_ATTESTED


def test_otp_start_requires_a_destination(svc):
    service, _, cid = svc
    with pytest.raises(DestinationError):
        service.start(cid, VerificationMethod.OTP_EMAIL, at=NOW)


def test_otp_start_rejects_a_destination_that_is_not_the_one_on_file(svc):
    service, _, cid = svc
    with pytest.raises(DestinationError):
        service.start(
            cid, VerificationMethod.OTP_EMAIL, destination="someone.else@example.com",
            rng=random.Random(3), at=NOW,
        )


def test_otp_start_accepts_the_contact_on_file_and_returns_a_code(svc):
    service, _, cid = svc
    v, code = service.start(
        cid, VerificationMethod.OTP_EMAIL, destination=EMAIL, rng=random.Random(3), at=NOW
    )
    assert v.status is VerificationStatus.PENDING
    assert code is not None and code.isdigit()


def test_destination_matching_is_normalized_before_hashing(svc):
    # "  DEV@Example.COM " and "dev@example.com" are the same contact.
    service, _, cid = svc
    v, code = service.start(
        cid, VerificationMethod.OTP_EMAIL, destination="  DEV@Example.COM ",
        rng=random.Random(3), at=NOW,
    )
    assert code is not None


def test_a_candidate_with_no_contact_hash_of_that_type_is_refused(svc, settings):
    service, _, _ = svc
    from app.verification.service import VerificationService as _VS  # same instance
    candidates = service._candidates
    with candidates._session_factory() as s:
        row = CandidateRow(full_name="No Phone", email_hash="e" * 64)
        s.add(row)
        s.commit()
        other = row.id
    with pytest.raises(DestinationError):
        service.start(
            other, VerificationMethod.OTP_PHONE, destination="+919876543210",
            rng=random.Random(3), at=NOW,
        )


def test_confirm_verifies_and_lifts_the_assurance_level(svc):
    service, _, cid = svc
    v, code = service.start(
        cid, VerificationMethod.OTP_EMAIL, destination=EMAIL, rng=random.Random(3), at=NOW
    )
    done = service.confirm(cid, v.id, code, at=NOW)
    assert done.status is VerificationStatus.VERIFIED
    _, assurance = service.list_for_candidate(cid, at=NOW)
    assert assurance.level is AssuranceLevel.CONTACT_CONTROL


def test_a_third_party_method_without_identity_verify_consent_is_refused(svc, monkeypatch):
    """The gate lives in the SPINE, keyed off adapter.third_party -- proven with
    a fake adapter so no real external integration is needed to test it."""
    service, ledger, cid = svc
    from app.verification import methods as methods_mod

    class _FakeThirdPartyAdapter:
        method = VerificationMethod.SELF_ATTESTED  # reuse a routable method value
        level = AssuranceLevel.GOVERNMENT_ID
        third_party = True
        challenge_based = False
        channel = None
        contact_hash_field = None

    monkeypatch.setitem(
        methods_mod.ADAPTERS, VerificationMethod.SELF_ATTESTED, _FakeThirdPartyAdapter()
    )
    with pytest.raises(ConsentError):
        service.start(cid, VerificationMethod.SELF_ATTESTED, at=NOW)


def test_a_third_party_method_with_consent_proceeds_and_stamps_the_grant(svc, monkeypatch):
    service, ledger, cid = svc
    from app.verification import methods as methods_mod

    class _FakeThirdPartyAdapter:
        method = VerificationMethod.SELF_ATTESTED
        level = AssuranceLevel.GOVERNMENT_ID
        third_party = True
        challenge_based = False
        channel = None
        contact_hash_field = None

    monkeypatch.setitem(
        methods_mod.ADAPTERS, VerificationMethod.SELF_ATTESTED, _FakeThirdPartyAdapter()
    )
    grant = ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.IDENTITY_VERIFY, org_id=None
    )
    v, _ = service.start(cid, VerificationMethod.SELF_ATTESTED, at=NOW)
    assert v.consent_id == grant.id


def test_confirm_refuses_a_verification_owned_by_another_candidate(svc, settings):
    service, _, cid = svc
    candidates = service._candidates
    with candidates._session_factory() as s:
        row = CandidateRow(full_name="Other", email_hash="f" * 64)
        s.add(row)
        s.commit()
        other = row.id
    v, code = service.start(
        cid, VerificationMethod.OTP_EMAIL, destination=EMAIL, rng=random.Random(3), at=NOW
    )
    # Indistinguishable from "does not exist" -- no probing for someone else's ids.
    with pytest.raises(LookupError):
        service.confirm(other, v.id, code, at=NOW)


def test_record_manual_review_records_a_reviewed_outcome(svc):
    service, _, cid = svc
    v = service.record_manual_review(cid, outcome=VerificationStatus.VERIFIED, at=NOW)
    assert v.assurance_level is AssuranceLevel.REVIEWED
    assert v.status is VerificationStatus.VERIFIED
    _, assurance = service.list_for_candidate(cid, at=NOW)
    assert assurance.level is AssuranceLevel.REVIEWED


def test_start_rejects_an_unknown_candidate(svc):
    service, _, _ = svc
    with pytest.raises(LookupError):
        service.start("nope", VerificationMethod.SELF_ATTESTED, at=NOW)


def test_services_container_exposes_verification(settings):
    from tests.conftest import make_services
    services = make_services(settings)
    assert services.verification is not None
    assert hasattr(services.verification, "start")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.verification.service'`

- [ ] **Step 3: Write the service**

Create `app/verification/service.py`:

```python
"""Verification orchestration (S7.1).

Two gates live here, in the spine, deliberately not in the adapters:

1. THIRD-PARTY CONSENT. Any adapter declaring `third_party` requires an active
   IDENTITY_VERIFY grant before anything happens. Putting this in the spine
   means a future vendor adapter is gated whether or not its author remembers.

2. DESTINATION BINDING. The candidates table stores only salted contact
   HASHES, so there is no address to look up. The candidate supplies the
   destination, we normalize + hash it with S1.1's helpers, and require it to
   equal the hash already on their row. This proves they know the contact on
   file, works regardless of what extraction retained, and lets the raw value
   stay transient -- only the hash is ever written.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Optional

from app.candidates.hashing import contact_hash, normalize_email, normalize_phone
from app.candidates.store import CandidateStore
from app.core.config import Settings, get_settings
from app.ledger import consent as consent_logic
from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError, LedgerStore
from app.verification.methods import get_adapter
from app.verification.otp import NullNotifier, Notifier
from app.verification.schema import (
    IdentityAssurance, Verification, VerificationMethod, VerificationStatus,
)
from app.verification.store import VerificationStore


class DestinationError(Exception):
    """The supplied OTP destination is missing, malformed, or does not match
    the contact hash on the candidate's record."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VerificationService:
    def __init__(
        self,
        store: VerificationStore,
        candidates: CandidateStore,
        ledger: LedgerStore,
        *,
        notifier: Optional[Notifier] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self._store = store
        self._candidates = candidates
        self._ledger = ledger
        self._notifier = notifier or NullNotifier()
        self._settings = settings or get_settings()

    def start(
        self,
        candidate_id: str,
        method: VerificationMethod,
        *,
        destination: Optional[str] = None,
        rng: Optional[random.Random] = None,
        at: Optional[datetime] = None,
    ) -> tuple[Verification, Optional[str]]:
        """Begin a verification. Returns (verification, plaintext_code | None).

        The plaintext code is returned ONLY so the route can honour the
        double-guarded debug echo; it is never persisted and never logged.
        """
        moment = consent_logic.as_utc(at) if at else _utcnow()
        summary = self._candidates.get_candidate(candidate_id)
        if summary is None:
            raise LookupError(f"unknown candidate: {candidate_id}")

        adapter = get_adapter(method)

        consent_id: Optional[str] = None
        if adapter.third_party:
            grants = self._ledger.consents_for_candidate(candidate_id)
            decision = consent_logic.has_any_active(
                grants, purpose=ConsentPurpose.IDENTITY_VERIFY, at=moment
            )
            if not decision.allowed:
                raise ConsentError(decision.reason)
            consent_id = decision.grant_id

        if adapter.challenge_based:
            destination_hash = self._bind_destination(summary, adapter, destination)
            verification = self._store.create_verification(
                candidate_id=candidate_id, method=method, consent_id=consent_id, at=moment
            )
            code = self._store.create_challenge(
                verification_id=verification.id,
                channel=adapter.channel or "",
                destination_hash=destination_hash,
                rng=rng,
                at=moment,
            )
            self._notifier.send(destination or "", code, channel=adapter.channel or "")
            return verification, code

        verification = self._store.create_verification(
            candidate_id=candidate_id, method=method, consent_id=consent_id, at=moment
        )
        completed = self._store.complete_verification(
            verification.id, status=VerificationStatus.VERIFIED, at=moment
        )
        return completed, None

    def _bind_destination(self, summary, adapter, destination: Optional[str]) -> str:
        if not destination or not destination.strip():
            raise DestinationError("destination is required for this method")
        if adapter.channel == "email":
            normalized = normalize_email(destination)
        else:
            normalized = normalize_phone(destination)
        if not normalized:
            raise DestinationError("destination is not a valid contact value")

        on_file = getattr(summary, adapter.contact_hash_field or "", None)
        if not on_file:
            raise DestinationError(
                f"no {adapter.channel} on file for this candidate"
            )
        supplied = contact_hash(normalized, self._settings.contact_hash_salt)
        if supplied != on_file:
            raise DestinationError("destination does not match the contact on file")
        return supplied

    def confirm(
        self,
        candidate_id: str,
        verification_id: str,
        code: str,
        *,
        at: Optional[datetime] = None,
    ) -> Verification:
        existing = self._store.get_verification(verification_id)
        if existing is None or existing.candidate_id != candidate_id:
            # Same error either way: a candidate cannot probe for another's ids.
            raise LookupError(f"unknown verification for candidate: {verification_id}")
        return self._store.confirm_challenge(verification_id, code, at=at)

    def list_for_candidate(
        self, candidate_id: str, *, at: Optional[datetime] = None
    ) -> tuple[list[Verification], IdentityAssurance]:
        moment = consent_logic.as_utc(at) if at else _utcnow()
        return (
            self._store.verifications_for_candidate(candidate_id),
            self._store.assurance_for_candidate(candidate_id, at=moment),
        )

    def assurance_for_candidate(
        self, candidate_id: str, *, at: Optional[datetime] = None
    ) -> IdentityAssurance:
        return self._store.assurance_for_candidate(candidate_id, at=at)

    def record_manual_review(
        self,
        candidate_id: str,
        *,
        outcome: VerificationStatus,
        note: Optional[str] = None,
        evidence_digest: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> Verification:
        moment = consent_logic.as_utc(at) if at else _utcnow()
        verification = self._store.create_verification(
            candidate_id=candidate_id,
            method=VerificationMethod.MANUAL_REVIEW,
            at=moment,
        )
        return self._store.complete_verification(
            verification.id,
            status=outcome,
            evidence_digest=evidence_digest,
            details={"note": note} if note else None,
            at=moment,
        )

    def assurance_for_org(
        self, *, org_id: str, candidate_id: str, at: Optional[datetime] = None
    ) -> IdentityAssurance:
        return self._store.assurance_for_org(
            org_id=org_id, candidate_id=candidate_id, at=at
        )


def build_verification_service(
    settings: Optional[Settings] = None,
    *,
    candidates: CandidateStore,
    ledger: LedgerStore,
) -> VerificationService:
    settings = settings or get_settings()
    store = VerificationStore(
        candidates._session_factory, ledger=ledger, settings=settings
    )
    return VerificationService(store, candidates, ledger, settings=settings)
```

- [ ] **Step 4: Wire into the services container**

In `app/services/__init__.py`:

1. Add to the `TYPE_CHECKING` block (alphabetical, after `from app.profile_sources.service import ProfileSourceService`):

```python
    from app.verification.service import VerificationService
```

2. Add to the `Services` dataclass, after `portal: PortalService`:

```python
    verification: VerificationService
```

3. Add to the function-local imports in `build_default_services`, after `from app.profile_sources.service import build_profile_source_service`:

```python
    from app.verification.service import build_verification_service
```

4. Add to the `Services(...)` construction, after the `portal=build_portal_service(...)` entry:

```python
        verification=build_verification_service(
            settings, candidates=candidates, ledger=ledger
        ),
```

- [ ] **Step 5: Wire into the test fixture**

In `tests/conftest.py`, add `verification=None` to `make_services`'s keyword parameters (after `portal=None`), then insert before the `return Services(` line:

```python
    if verification is None:
        from app.verification.service import VerificationService
        from app.verification.store import VerificationStore
        verification = VerificationService(
            VerificationStore(candidates._session_factory, ledger=ledger, settings=settings),
            candidates, ledger, settings=settings,
        )
```

and add `verification=verification,` to the `Services(...)` call after `portal=portal,`.

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_verification_service.py -q`
Expected: PASS (13 tests)

Run: `python -m pytest -q`
Expected: PASS — full suite green.

- [ ] **Step 7: Commit**

```bash
git add app/verification/service.py app/services/__init__.py tests/conftest.py tests/test_verification_service.py
git commit -m "feat(s71): verification service (destination binding + third-party gate) + wiring"
```

---

### Task 9: Candidate-plane endpoints + portal integration

**Files:**
- Modify: `app/api/routes.py` (3 routes + request models), `app/portal/schema.py` (`MyData.identity`), `app/portal/service.py` (populate it), `app/portal/retention.py` (`RETENTION_KNOBS`)
- Test: `tests/test_verification_api.py`, `tests/test_portal_identity.py`

**Interfaces:**
- Consumes: `Services.verification` (Task 8), `require_candidate` (existing).
- Produces: `POST /portal/verifications`, `POST /portal/verifications/{verification_id}/confirm`, `GET /portal/verifications`; `MyData.identity: IdentityAssurance`; `PortalService.__init__` gains a keyword-only `verification=None` parameter.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_verification_api.py`:

```python
"""S7.1 candidate-plane routes: the key is the only identity input that counts."""

import pytest
from fastapi.testclient import TestClient

from app.candidates.hashing import contact_hash, normalize_email
from app.candidates.models import CandidateRow
from app.main import app
from tests.conftest import make_services

EMAIL = "dev@example.com"


@pytest.fixture
def client(settings, monkeypatch):
    monkeypatch.setattr(settings, "verif_otp_debug_echo", True, raising=False)
    services = make_services(settings)
    with TestClient(app) as c:
        c.app.state.services = services
        yield c, services


def _candidate(services, email=EMAIL, name="A Candidate"):
    store = services.candidates
    with store._session_factory() as s:
        row = CandidateRow(
            full_name=name,
            email_hash=contact_hash(
                normalize_email(email), services.settings.contact_hash_salt
            ),
        )
        s.add(row)
        s.commit()
        cid = row.id
    return cid, store.issue_access_key(cid)


def test_verifications_require_a_candidate_key(client):
    c, _ = client
    assert c.get("/portal/verifications").status_code == 401
    assert c.get("/portal/verifications", headers={"X-Candidate-Key": "bogus"}).status_code == 401


def test_self_attest_lifts_the_level(client):
    c, services = client
    _, key = _candidate(services)
    h = {"X-Candidate-Key": key}
    r = c.post("/portal/verifications", json={"method": "self_attested"}, headers=h)
    assert r.status_code == 200
    assert r.json()["verification"]["status"] == "verified"

    listed = c.get("/portal/verifications", headers=h).json()
    assert listed["assurance"]["level"] == 1  # SELF_ATTESTED
    assert listed["assurance"]["advisory"] is True


def test_otp_flow_start_wrong_code_then_correct_code(client):
    c, services = client
    _, key = _candidate(services)
    h = {"X-Candidate-Key": key}
    started = c.post(
        "/portal/verifications",
        json={"method": "otp_email", "destination": EMAIL}, headers=h,
    )
    assert started.status_code == 200
    body = started.json()
    vid = body["verification"]["id"]
    code = body["debug_code"]  # double-guarded echo, enabled in this fixture
    assert code is not None

    wrong = "0" * len(code) if code != "0" * len(code) else "1" * len(code)
    assert c.post(
        f"/portal/verifications/{vid}/confirm", json={"code": wrong}, headers=h
    ).status_code == 400

    ok = c.post(f"/portal/verifications/{vid}/confirm", json={"code": code}, headers=h)
    assert ok.status_code == 200
    assert ok.json()["status"] == "verified"
    assert c.get("/portal/verifications", headers=h).json()["assurance"]["level"] == 2


def test_a_destination_that_is_not_on_file_is_a_400(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post(
        "/portal/verifications",
        json={"method": "otp_email", "destination": "attacker@example.com"},
        headers={"X-Candidate-Key": key},
    )
    assert r.status_code == 400


def test_a_missing_destination_for_an_otp_method_is_a_400(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post(
        "/portal/verifications", json={"method": "otp_email"},
        headers={"X-Candidate-Key": key},
    )
    assert r.status_code == 400


def test_an_unknown_method_is_a_422(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post(
        "/portal/verifications", json={"method": "telepathy"},
        headers={"X-Candidate-Key": key},
    )
    assert r.status_code == 422


def test_government_id_is_not_reachable_from_the_candidate_plane(client):
    c, services = client
    _, key = _candidate(services)
    r = c.post(
        "/portal/verifications", json={"method": "government_id"},
        headers={"X-Candidate-Key": key},
    )
    # Refused (no IDENTITY_VERIFY grant) rather than executed -- never a 500.
    assert r.status_code in (400, 403, 422)


def test_one_candidate_cannot_confirm_anothers_verification(client):
    c, services = client
    _, key_a = _candidate(services)
    _, key_b = _candidate(services, email="other@example.com", name="Other")
    started = c.post(
        "/portal/verifications", json={"method": "otp_email", "destination": EMAIL},
        headers={"X-Candidate-Key": key_a},
    ).json()
    vid, code = started["verification"]["id"], started["debug_code"]

    stolen = c.post(
        f"/portal/verifications/{vid}/confirm", json={"code": code},
        headers={"X-Candidate-Key": key_b},
    )
    assert stolen.status_code == 404  # indistinguishable from "no such id"

    # A's verification is untouched and still confirmable by A.
    assert c.post(
        f"/portal/verifications/{vid}/confirm", json={"code": code},
        headers={"X-Candidate-Key": key_a},
    ).status_code == 200


def test_the_debug_echo_is_absent_when_the_knob_is_off(settings):
    services = make_services(settings)  # verif_otp_debug_echo defaults to False
    with TestClient(app) as c:
        c.app.state.services = services
        _, key = _candidate(services)
        body = c.post(
            "/portal/verifications", json={"method": "otp_email", "destination": EMAIL},
            headers={"X-Candidate-Key": key},
        ).json()
        assert body.get("debug_code") is None
```

Create `tests/test_portal_identity.py`:

```python
"""S7.1: the DPDP access view surfaces identity assurance + its retention window."""

from app.candidates.models import CandidateRow
from app.verification.schema import AssuranceLevel, VerificationMethod
from tests.conftest import make_services


def _candidate(services):
    with services.candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash="e" * 64)
        s.add(row)
        s.commit()
        return row.id


def test_my_data_reports_identity_assurance(settings):
    services = make_services(settings)
    cid = _candidate(services)
    services.verification.start(cid, VerificationMethod.SELF_ATTESTED)
    data = services.portal.my_data(cid)
    assert data.identity is not None
    assert data.identity.level is AssuranceLevel.SELF_ATTESTED


def test_my_data_reports_level_none_before_any_verification(settings):
    services = make_services(settings)
    cid = _candidate(services)
    assert services.portal.my_data(cid).identity.level is AssuranceLevel.NONE


def test_retention_policy_includes_the_verifications_window(settings):
    services = make_services(settings)
    cid = _candidate(services)
    classes = {w.data_class for w in services.portal.my_data(cid).retention.windows}
    assert "verifications" in classes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_verification_api.py tests/test_portal_identity.py -q`
Expected: FAIL — 404s on the new routes; `MyData` has no `identity`.

- [ ] **Step 3: Extend the portal**

In `app/portal/schema.py`, add the import:

```python
from app.verification.schema import IdentityAssurance
```

and add to `MyData` (after `consents`):

```python
    identity: Optional[IdentityAssurance] = None
```

In `app/portal/retention.py`, add to `RETENTION_KNOBS` after `"profile_sources"`:

```python
    "verifications": "ret_verification_days",
```

In `app/portal/service.py`, add `verification=None` as a keyword-only parameter to `PortalService.__init__` (after `profile_sources`), store it as `self._verification = verification`, and inside `my_data` add before the `return MyData(`:

```python
        identity = (
            self._verification.assurance_for_candidate(candidate_id)
            if self._verification is not None
            else None
        )
```

then pass `identity=identity,` in the `MyData(...)` construction.

Update `build_portal_service` to accept and forward `verification=None`.

In `app/services/__init__.py`'s `build_default_services`, the portal is built **before** verification exists. Reorder so verification is built first:

```python
    verification = build_verification_service(settings, candidates=candidates, ledger=ledger)
```

placed with the other hoisted builds (after `profile_sources = ...`), then pass `verification=verification` into `build_portal_service(...)` and `verification=verification` into the `Services(...)` call.

Apply the same ordering in `tests/conftest.py`: build `verification` before `portal`, and pass `verification=verification` to `PortalService(...)`.

- [ ] **Step 4: Add the candidate-plane routes**

In `app/api/routes.py`, add imports near the other app imports:

```python
from app.ledger.store import ConsentError
from app.verification.schema import VerificationMethod, VerificationStatus
from app.verification.service import DestinationError
from app.verification.store import ChallengeError
```

(`ConsentError` may already be imported — do not duplicate it.)

Add the request models next to the other Pydantic request bodies:

```python
class StartVerificationRequest(BaseModel):
    """`destination` is required for OTP methods and must match the contact
    hash already on the candidate's record."""

    method: VerificationMethod
    destination: str | None = None


class ConfirmVerificationRequest(BaseModel):
    code: str
```

Add the three routes at the end of the candidate-plane section:

```python
@candidate_router.post("/portal/verifications")
async def start_verification(
    req: StartVerificationRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> dict:
    services = _services(request)
    try:
        verification, code = services.verification.start(
            candidate_id, req.method, destination=req.destination
        )
    except DestinationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ChallengeError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except NotImplementedError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    body: dict = {"verification": verification.model_dump(mode="json")}
    # Double-guarded: local env AND the knob. Exists so the sprint smoke can
    # drive the two-step flow over plain HTTP; production can never echo.
    if code is not None and services.settings.env == "local" and services.settings.verif_otp_debug_echo:
        body["debug_code"] = code
    return body


@candidate_router.post("/portal/verifications/{verification_id}/confirm")
async def confirm_verification(
    verification_id: str,
    req: ConfirmVerificationRequest,
    request: Request,
    candidate_id: str = Depends(require_candidate),
) -> dict:
    services = _services(request)
    try:
        verification = services.verification.confirm(
            candidate_id, verification_id, req.code
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ChallengeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return verification.model_dump(mode="json")


@candidate_router.get("/portal/verifications")
async def list_verifications(
    request: Request, candidate_id: str = Depends(require_candidate)
) -> dict:
    verifications, assurance = _services(request).verification.list_for_candidate(
        candidate_id
    )
    return {
        "verifications": [v.model_dump(mode="json") for v in verifications],
        "assurance": assurance.model_dump(mode="json"),
    }
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_verification_api.py tests/test_portal_identity.py -q`
Expected: PASS (12 tests)

Run: `python -m pytest -q`
Expected: PASS — full suite green.

- [ ] **Step 6: Commit**

```bash
git add app/api/routes.py app/portal/ app/services/__init__.py tests/conftest.py tests/test_verification_api.py tests/test_portal_identity.py
git commit -m "feat(s71): candidate-plane verification endpoints + portal identity view"
```

---

### Task 10: Org-plane + admin-plane endpoints

**Files:**
- Modify: `app/api/routes.py`
- Test: `tests/test_verification_org_api.py`

**Interfaces:**
- Consumes: `Services.verification`, `require_org`, `require_api_key`.
- Produces: `GET /verification/candidates/{candidate_id}/assurance` (org plane), `POST /candidates/{candidate_id}/verifications/manual-review` (admin plane) with body `ManualReviewRequest{outcome: VerificationStatus, note: str | None, evidence_digest: str | None}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_verification_org_api.py`:

```python
"""S7.1 org + admin planes: disclosure is consent-gated; review is operator-only."""

import pytest
from fastapi.testclient import TestClient

from app.candidates.models import CandidateRow
from app.main import app
from tests.conftest import make_services


@pytest.fixture
def client(settings):
    services = make_services(settings)
    with TestClient(app) as c:
        c.app.state.services = services
        yield c, services


def _candidate(services):
    with services.candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash="e" * 64)
        s.add(row)
        s.commit()
        return row.id


def _org(services):
    org = services.ledger.create_organization("Acme Corp")
    return org.id, services.ledger.issue_api_key(org.id)


def test_org_read_requires_an_org_key(client):
    c, services = client
    cid = _candidate(services)
    assert c.get(f"/verification/candidates/{cid}/assurance").status_code == 401


def test_org_read_without_consent_is_403(client):
    c, services = client
    cid = _candidate(services)
    _, org_key = _org(services)
    r = c.get(
        f"/verification/candidates/{cid}/assurance", headers={"X-Org-Key": org_key}
    )
    assert r.status_code == 403


def test_org_read_with_verification_read_consent_is_200(client):
    c, services = client
    cid = _candidate(services)
    org_id, org_key = _org(services)
    from app.ledger.schema import ConsentPurpose
    from app.verification.schema import VerificationMethod
    services.verification.start(cid, VerificationMethod.SELF_ATTESTED)
    services.ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=org_id
    )
    r = c.get(
        f"/verification/candidates/{cid}/assurance", headers={"X-Org-Key": org_key}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["level"] == 1
    assert body["advisory"] is True
    # The aggregate must not re-leak per-attempt evidence.
    assert "evidence_digest" not in body
    assert "destination_hash" not in body


def test_org_read_of_an_unknown_candidate_is_404(client):
    c, services = client
    _, org_key = _org(services)
    r = c.get(
        "/verification/candidates/nope/assurance", headers={"X-Org-Key": org_key}
    )
    assert r.status_code == 404


def test_admin_manual_review_records_a_reviewed_outcome(client):
    c, services = client
    cid = _candidate(services)
    r = c.post(
        f"/candidates/{cid}/verifications/manual-review",
        json={"outcome": "verified", "note": "passport seen in person"},
    )
    assert r.status_code == 200
    assert r.json()["assurance_level"] == 3  # REVIEWED
    assert services.verification.assurance_for_candidate(cid).level == 3


def test_admin_manual_review_of_an_unknown_candidate_is_404(client):
    c, _ = client
    r = c.post(
        "/candidates/nope/verifications/manual-review", json={"outcome": "verified"}
    )
    assert r.status_code == 404


def test_admin_manual_review_rejects_a_bad_outcome(client):
    c, services = client
    cid = _candidate(services)
    r = c.post(
        f"/candidates/{cid}/verifications/manual-review", json={"outcome": "maybe"}
    )
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_verification_org_api.py -q`
Expected: FAIL — 404 on both new routes.

- [ ] **Step 3: Write the routes**

In `app/api/routes.py`, add the admin request model beside the others:

```python
class ManualReviewRequest(BaseModel):
    """Operator-recorded verification outcome. `evidence_digest` is a hash of
    whatever was checked out of band -- never the artifact itself."""

    outcome: VerificationStatus
    note: str | None = None
    evidence_digest: str | None = None
```

Add the org-plane route in the org-plane section:

```python
@org_router.get("/verification/candidates/{candidate_id}/assurance")
async def org_candidate_assurance(
    candidate_id: str, request: Request, org_id: str = Depends(require_org)
) -> dict:
    """Consent-gated identity assurance. Every attempt -- allowed or denied --
    is audited by the store. Returns the advisory roll-up only."""
    try:
        assurance = _services(request).verification.assurance_for_org(
            org_id=org_id, candidate_id=candidate_id
        )
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return assurance.model_dump(mode="json")
```

Add the admin-plane route in the admin section:

```python
@router.post("/candidates/{candidate_id}/verifications/manual-review")
async def record_manual_review(
    candidate_id: str, req: ManualReviewRequest, request: Request
) -> dict:
    try:
        verification = _services(request).verification.record_manual_review(
            candidate_id,
            outcome=req.outcome,
            note=req.note,
            evidence_digest=req.evidence_digest,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return verification.model_dump(mode="json")
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_verification_org_api.py -q`
Expected: PASS (7 tests)

Run: `python -m pytest -q`
Expected: PASS — full suite green.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py tests/test_verification_org_api.py
git commit -m "feat(s71): org-plane assurance read + admin manual-review endpoint"
```

---

### Task 11: DPDP erasure test, smoke, docs, ROADMAP

**Files:**
- Create: `scripts/smoke_s71.py`, `VERIFICATION.md`
- Modify: `docs/ROADMAP.md`
- Test: `tests/test_verification_erasure.py`

**Interfaces:**
- Consumes: everything above. Produces no new code interfaces.

- [ ] **Step 1: Write the failing erasure test**

Create `tests/test_verification_erasure.py`:

```python
"""S7.1 DPDP: erasing the candidate sweeps every verification artifact."""

import pytest
from sqlalchemy import select

from app.candidates.models import CandidateRow
from app.ledger.schema import ConsentPurpose
from app.ledger.store import ConsentError
from app.verification.models import VerificationChallengeRow, VerificationRow
from app.verification.schema import VerificationMethod
from tests.conftest import make_services


def _candidate(services):
    with services.candidates._session_factory() as s:
        row = CandidateRow(full_name="A Candidate", email_hash="e" * 64)
        s.add(row)
        s.commit()
        return row.id


def test_erasure_removes_verifications_and_challenges(settings):
    services = make_services(settings)
    cid = _candidate(services)
    services.verification.start(cid, VerificationMethod.SELF_ATTESTED)

    assert services.candidates.delete_candidate(cid) is True

    with services.candidates._session_factory() as s:
        assert s.execute(select(VerificationRow)).scalars().all() == []
        assert s.execute(select(VerificationChallengeRow)).scalars().all() == []


def test_after_erasure_the_org_read_404s_rather_than_disclosing(settings):
    services = make_services(settings)
    cid = _candidate(services)
    org = services.ledger.create_organization("Acme Corp")
    services.verification.start(cid, VerificationMethod.SELF_ATTESTED)
    services.ledger.grant_consent(
        candidate_id=cid, purpose=ConsentPurpose.VERIFICATION_READ, org_id=org.id
    )
    services.verification.assurance_for_org(org_id=org.id, candidate_id=cid)

    services.candidates.delete_candidate(cid)
    with pytest.raises(LookupError):
        services.verification.assurance_for_org(org_id=org.id, candidate_id=cid)
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/test_verification_erasure.py -q`
Expected: PASS (the CASCADE from Task 5 already provides this — this test proves the contract end-to-end rather than driving new code).

If it FAILS, the cascade is broken: fix `app/verification/models.py` and the migration, do not weaken the test.

- [ ] **Step 3: Write the smoke script**

Create `scripts/smoke_s71.py`, modelled on `scripts/smoke_s64.py` (read that file first and copy its uvicorn bootstrap, port selection, `_check` helper, and exit-code convention exactly). The scripted sequence:

1. Set `DEE_VERIF_OTP_DEBUG_ECHO=true` in the child env before boot.
2. `POST /candidates` with a fixture resume that carries an email; capture `candidate_id` and the email.
3. `POST /candidates/{id}/auth-key` → candidate key.
4. `GET /portal/me` → `identity.level == 0`.
5. `POST /portal/verifications {"method": "self_attested"}` → 200, status `verified`.
6. `GET /portal/verifications` → `assurance.level == 1`.
7. `POST /portal/verifications {"method": "otp_email", "destination": "<wrong@example.com>"}` → **400**.
8. `POST /portal/verifications {"method": "otp_email", "destination": "<real email>"}` → 200, capture `debug_code`.
9. `POST /portal/verifications/{vid}/confirm {"code": "<wrong>"}` → **400**.
10. `POST /portal/verifications/{vid}/confirm {"code": "<debug_code>"}` → 200, `verified`.
11. `GET /portal/verifications` → `assurance.level == 2`.
12. Create an org + key; `GET /verification/candidates/{id}/assurance` → **403**.
13. Grant `verification_read`; same call → **200**, `level == 2`.
14. Revoke; same call → **403**.
15. `POST /candidates/{id}/verifications/manual-review {"outcome": "verified"}` → 200; `GET /portal/verifications` → `assurance.level == 3`.
16. `DELETE /portal/me` → 200; org read → **404**.

Print `OK`/`FAIL` per check and exit non-zero if any failed.

- [ ] **Step 4: Run the smoke**

Run: `python scripts/smoke_s71.py`
Expected: all 16 checks OK, exit 0. If a check fails, fix the **code**, not the check.

- [ ] **Step 5: Write `VERIFICATION.md`**

Create `VERIFICATION.md` as a peer of `LEDGER.md`/`PORTAL.md`, covering: what the spine is and why outcomes-not-documents is structural; the assurance ladder table; the adapter seam and how a future KYC vendor plugs in; the two consent purposes and exactly which actions each gates (including that first-party self-service needs none); the three planes and their routes with status codes; the OTP destination-binding rule; challenge hygiene vs. the deferred PI-8 retention sweep; the `verif_*` config knobs; and the explicit non-goals from spec §9.

- [ ] **Step 6: Update the ROADMAP**

In `docs/ROADMAP.md`: flip the status board's PI-7 line to show `[x] S7.1` with its one-line summary; rewrite "▶ Current state" for S7.1 (what was delivered, test count before→after, smoke result, the three scope decisions, deferred minors); set "Next action" to *merge S7.1, then shape S7.2 (document forensics + moonlighting advisory) as the second producer on this spine*; and add a dated session-log entry at the top of the log.

- [ ] **Step 7: Final verification**

Run: `python -m pytest -q`
Expected: PASS — report the exact final count.

Run: `python -m pytest --collect-only -q 2>&1 | tail -3` to confirm no collection errors.

Run: `python -m pyflakes app/verification/*.py scripts/smoke_s71.py` (or `python -m flake8 --select=F`) — expect clean.

- [ ] **Step 8: Commit**

```bash
git add tests/test_verification_erasure.py scripts/smoke_s71.py VERIFICATION.md docs/ROADMAP.md
git commit -m "test(s71): DPDP erasure + uvicorn smoke; VERIFICATION.md + ROADMAP closeout"
```

---

## Self-Review Notes

Checked against the spec:

- **§5.1 contracts** → Task 1. **§5.2 assurance** → Task 2. **§5.3 adapter seam** → Task 4. **§5.4 OTP + destination binding** → Tasks 3, 8. **§5.5 models/migration** → Task 5. **§5.6 store/service/wiring** → Tasks 6, 7, 8.
- **§4 DPDP posture** → structural no-artifact-column tests (Tasks 1, 5), consent basis table (Tasks 7, 8), CASCADE (Tasks 5, 11), retention window (Task 9), challenge deletion (Task 6).
- **§6 API** → candidate plane (Task 9), org plane + admin plane (Task 10).
- **§7 config** → Task 1, with the double-guard asserted in Task 9.
- **§8 testing + smoke** → every listed case has a named test; smoke in Task 11.
- **§10 definition of done** → Task 11 Steps 4–8.

Type consistency verified: `compute_assurance(candidate_id, verifications, *, at)` is called identically in Tasks 6, 7; `get_adapter` returns `_Base` with `channel`/`contact_hash_field` used in Task 8; `start()` returns `tuple[Verification, Optional[str]]` consumed as such by the route in Task 9; `ChallengeError`/`DestinationError`/`ConsentError` are raised in Tasks 6/8/7 and mapped in Tasks 9/10.

One ordering hazard called out explicitly: `build_portal_service` must receive the verification service, so Task 9 Step 3 reorders `build_default_services` and `make_services` to construct verification **before** portal.
