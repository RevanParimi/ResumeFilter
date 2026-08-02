# S8.2 — Identity & Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a real organization and a real candidate get into veritas by email-OTP login — holding an opaque, revocable, server-side session in an httpOnly cookie — with no operator touching the database.

**Architecture:** A new pure package `app/auth/` (peer of `app/portal/`, `app/verification/`, `app/interview/`) holds clock-injected session and OTP-policy logic, ORM rows, a store and a service. The three existing header-key dependencies in `app/api/routes.py` become thin wrappers over **one resolver per plane** that tries the session cookie first and the header key second, so all 63 endpoints gain session mode with zero handler edits. A structural guard over the FastAPI route table asserts no route establishes a principal any other way. A new `app/services/email.py` seam (shaped like `llm.py`/`speech.py`) delivers the codes.

**Tech Stack:** Python 3.11/3.12 · FastAPI · SQLAlchemy 2.x (`Mapped`/`mapped_column`) · Alembic · Pydantic v2 · pytest · structlog. SQLite is the local/test backend; everything is written Postgres-shaped.

**Spec:** `docs/superpowers/specs/2026-08-02-s82-identity-access-design.md`
**PI design:** `docs/superpowers/specs/2026-08-01-pi8-launch-readiness-design.md` (§4 auth architecture)
**Baseline:** `main` at `714dbc7`, **1200 tests green**.

## Global Constraints

Every task's requirements implicitly include these. They come from `CLAUDE.md` and the spec; none is negotiable.

- **TDD.** Write the failing test, run it and see it fail for the right reason, then implement. `pytest -q` must be green before any commit.
- **Fully offline tests.** No network, no provider, no `time.sleep`. Clocks and RNGs are injected (`*, at: datetime`, `*, rng: random.Random`) — the `app/verification/otp.py` pattern.
- **No pinned-NOW time bombs.** If a test pins `NOW`, inject that clock into **every** mutation in the test, not just the setup. This detonated mid-session during S8.1; see `tests/test_interview_org.py::test_revocation_closes_it_again`.
- **Advisory only.** Nothing here auto-rejects anybody.
- **DPDP.** First-party data only; every new table has a delete path. `ip_hash`, never a raw IP.
- **No new `ConsentPurpose`.** Authentication is not a disclosure (spec §8).
- **Config in `config.yaml`, secrets in `.env` under `DEE_*`.** No secret ever in YAML.
- **Gates live on the service, never on the route.** This is the bug shape that shipped in S7.1, S7.2 and S7.3.
- **Commit messages: NO `Co-Authored-By` trailer.** House rule.
- **Branch:** `s82-identity-access`, cut from `main` at `714dbc7`.

**Naming, fixed here so tasks agree** (the resolver is consumed by Task 10 before Task 9's file is read by anyone):

| Thing | Exact name |
|---|---|
| Package | `app/auth/` |
| Session cookie | value of `settings.session_cookie_name`, default `"dee_session"` |
| CSRF cookie | value of `settings.csrf_cookie_name`, default `"dee_csrf"` |
| CSRF header | `X-CSRF-Token` |
| Resolver entry point | `AuthService.resolve_principal(request, *, kind) -> Principal` |
| Route dependencies | `require_api_key`, `require_org`, `require_candidate`, `require_any_principal` |
| Migration | `0017_auth_identity`, `down_revision = "0016_reports_outcomes"` |

---

## File Structure

**Create:**

| File | Responsibility |
|---|---|
| `app/auth/__init__.py` | package marker |
| `app/auth/schema.py` | Pydantic contracts + StrEnums. No I/O, no ORM. |
| `app/auth/sessions.py` | pure session mechanics: token mint/hash, `effective_status(at)` |
| `app/auth/csrf.py` | pure double-submit token mint + constant-time compare |
| `app/auth/challenges.py` | pure login-OTP **policy** over `app/verification/otp.py`'s mechanics |
| `app/auth/models.py` | 4 ORM rows on the shared `Base` |
| `app/auth/store.py` | `AuthStore` — all SQL for the 4 tables |
| `app/auth/service.py` | `AuthService` — the gate; signup/login/resolve/logout |
| `app/services/email.py` | delivery seam: `EmailClient`/`SMTPEmail`/`NullEmail`/`CaptureEmail`/`build_email` |
| `alembic/versions/0017_auth_identity.py` | the migration |
| `scripts/smoke_s82.py` | key-less uvicorn smoke |
| `AUTH.md` | subsystem doc (peer of `LEDGER.md`, `PORTAL.md`, `VERIFICATION.md`, `INTERVIEWS.md`) |

**Modify:**

| File | Change |
|---|---|
| `app/core/config.py` | new knobs; fix the stale `api_auth_key` comment at `:361` |
| `app/core/boot.py` | three new prod refusals |
| `app/api/routes.py` | 3 resolvers become wrappers; add `require_any_principal`, the CSRF dependency, and the auth + admin-user routes |
| `app/main.py` | `CORSMiddleware`; register `auth_router` |
| `app/services/__init__.py` | `Services.auth` + `Services.email` |
| `app/candidates/store.py` | `find_by_email_hash`, `create_bare_candidate` |
| `app/portal/schema.py` | `MyData.sessions` |
| `app/portal/service.py` | populate it |
| `tests/conftest.py` | build `auth` + `email` in `make_services`; session-header helpers |
| `tests/test_migrations.py` | extend the four guards to the new tables |

---

## Task 1: Config knobs, boot refusals, and one stale comment

**Files:**
- Modify: `app/core/config.py` (add knobs; fix comment at `:361`)
- Modify: `app/core/boot.py`
- Modify: `config.yaml`
- Test: `tests/test_boot_config.py` (extend; it exists from S8.1)

**Interfaces:**
- Produces: `Settings.session_ttl_minutes`, `.session_idle_timeout_minutes`, `.session_token_bytes`, `.session_last_seen_write_seconds`, `.session_cookie_name`, `.session_cookie_secure`, `.session_cookie_samesite`, `.csrf_cookie_name`, `.csrf_token_bytes`, `.login_otp_length`, `.login_otp_ttl_seconds`, `.login_otp_max_attempts`, `.login_otp_cooldown_seconds`, `.cors_allowed_origins`, `.email_provider`, `.email_from`, `.email_smtp_host`, `.email_smtp_port`, `.email_smtp_starttls`, `.email_capture_path`, `.email_smtp_user: SecretStr`, `.email_smtp_password: SecretStr`; three new `LaunchConfigError` conditions.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_boot_config.py`:

```python
import pytest
from pydantic import SecretStr

from app.core.boot import LaunchConfigError, verify_launch_config
from app.core.config import Settings


def _prod(**over) -> Settings:
    """A prod-shaped Settings that passes S8.1's two refusals, so each test
    below isolates exactly the new refusal it names."""
    base = dict(
        _env_file=None,
        api_auth_key=SecretStr("set"),
        env="prod",
        candidates_db_url="postgresql+psycopg://u:p@h/db",
    )
    base.update(over)
    return Settings(**base)


def test_prod_refuses_insecure_session_cookie():
    with pytest.raises(LaunchConfigError, match="session_cookie_secure"):
        verify_launch_config(_prod(session_cookie_secure=False))


def test_prod_refuses_wildcard_cors_origin():
    with pytest.raises(LaunchConfigError, match="cors_allowed_origins"):
        verify_launch_config(_prod(cors_allowed_origins=["*"]))


def test_prod_refuses_capture_email_provider():
    with pytest.raises(LaunchConfigError, match="capture"):
        verify_launch_config(_prod(email_provider="capture"))


def test_prod_accepts_a_sound_config():
    verify_launch_config(_prod(cors_allowed_origins=["https://app.example.com"]))


def test_local_may_use_capture_and_insecure_cookies():
    """The smoke runs over http://localhost. These refusals are prod-only ON
    PURPOSE -- an env-gated escape is not the S8.1 mistake here, because the
    refusing state (prod) is the DEPLOYED one, not the default one."""
    verify_launch_config(
        Settings(
            _env_file=None,
            api_auth_key=SecretStr("set"),
            env="local",
            session_cookie_secure=False,
            email_provider="capture",
        )
    )


def test_session_defaults_are_secure():
    s = Settings(_env_file=None, api_auth_key=SecretStr("x"))
    assert s.session_cookie_secure is True
    assert s.session_cookie_samesite == "none"
    assert s.cors_allowed_origins == []      # fail-closed
    assert s.email_provider == "null"        # refuses, never capture
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_boot_config.py -q`
Expected: FAIL — `TypeError`/`ValidationError` on unknown settings fields (`session_cookie_secure` etc.).

- [ ] **Step 3: Add the knobs**

In `app/core/config.py`, immediately **before** the `# --- Service ---` block, add:

```python
    # --- Auth sessions + login (PI-8, S8.2) -----------------------------------
    # Opaque server-side sessions, NOT JWT (PI-8 decision 0.2): a JWT stays valid
    # after a candidate revokes consent or erases their account, which is a DPDP
    # correctness bug. An opaque row dies with a DELETE.
    session_ttl_minutes: int = Field(default=720, ge=1)
    session_idle_timeout_minutes: int = Field(default=120, ge=1)
    session_token_bytes: int = Field(default=32, ge=16)
    # last_seen_at is needed for the idle timeout but must NOT be a write per
    # request -- on Postgres that is a row lock + WAL entry on the hottest path.
    session_last_seen_write_seconds: int = Field(default=60, ge=0)
    session_cookie_name: str = "dee_session"
    # SameSite=None is REQUIRED (the UI is separately hosted, so every request is
    # cross-site and Lax would drop the cookie). None mandates Secure, which
    # mandates HTTPS -- so `false` is for localhost only and prod refuses to boot
    # with it (app/core/boot.py).
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["none", "lax", "strict"] = "none"
    csrf_cookie_name: str = "dee_csrf"
    csrf_token_bytes: int = Field(default=32, ge=16)
    login_otp_length: int = Field(default=6, ge=4, le=10)
    login_otp_ttl_seconds: int = Field(default=600, ge=30)
    login_otp_max_attempts: int = Field(default=5, ge=1)
    login_otp_cooldown_seconds: int = Field(default=60, ge=0)
    # Fail-closed: no origin may call this API cross-site until one is named.
    # NEVER "*" -- browsers forbid it with credentials anyway, and relying on
    # that as the guard leaves a defect waiting for someone to silence the error.
    cors_allowed_origins: list[str] = Field(default_factory=list)

    # --- Email seam (PI-8, S8.2) ----------------------------------------------
    # Shaped like llm.py / speech.py. "null" REFUSES (503 email_unavailable) --
    # nothing silently degrades. "capture" is reachable only by explicit config,
    # never by fallback, and prod refuses to boot with it.
    email_provider: Literal["null", "smtp", "capture"] = "null"
    email_from: str = ""
    email_smtp_host: str = ""
    email_smtp_port: int = Field(default=587, ge=1, le=65535)
    email_smtp_starttls: bool = True
    email_capture_path: str = ""   # CaptureEmail writes JSON lines here
    email_smtp_user: SecretStr = Field(default=SecretStr(""))
    email_smtp_password: SecretStr = Field(default=SecretStr(""))
```

Then fix the stale comment. Replace:

```python
    # Optional shared-secret gate (FR-15). SECRET → env/.env only, never YAML.
    # Empty (default) = auth disabled (local/dev). /healthz and / stay open.
    api_auth_key: SecretStr = Field(default=SecretStr(""))
```

with:

```python
    # Shared-secret admin gate (FR-15). SECRET → env/.env only, never YAML.
    # Empty is NOT "auth disabled" -- since S8.1 it is the most refusing state:
    # require_api_key 401s everything and verify_launch_config refuses to boot.
    # The default is empty so that a forgotten variable fails loudly, not openly.
    api_auth_key: SecretStr = Field(default=SecretStr(""))
```

- [ ] **Step 4: Add the boot refusals**

Append to `verify_launch_config` in `app/core/boot.py`:

```python
    if settings.env != "prod":
        return
    # Everything below is prod-only BY DESIGN, and that is not the S8.1 mistake:
    # S8.1's rejected escape keyed a refusal on `env` DEFAULTING to the safe
    # value. Here the refusing state IS the deployed one, so a forgotten
    # variable still lands on the strict side.
    if not settings.session_cookie_secure:
        raise LaunchConfigError(
            "DEE_ENV=prod with session_cookie_secure=false. The session cookie "
            "would travel in the clear, and SameSite=None requires Secure in "
            "every browser. Set session_cookie_secure=true and serve over HTTPS."
        )
    if "*" in settings.cors_allowed_origins:
        raise LaunchConfigError(
            'DEE_ENV=prod with "*" in cors_allowed_origins. This API is called '
            "with credentials, so a wildcard origin is never correct. List the "
            "UI's exact origins."
        )
    if settings.email_provider == "capture":
        raise LaunchConfigError(
            "DEE_ENV=prod with email_provider=capture. CaptureEmail writes login "
            "codes to email_capture_path in plaintext -- that is an OTP leak "
            "wearing a test harness's clothes. Use email_provider=smtp."
        )
```

- [ ] **Step 5: Mirror the knobs in `config.yaml`**

Add both blocks from Step 3 to `config.yaml` (values only, no secrets — `email_smtp_user`/`email_smtp_password` stay out of YAML and live in `.env` as `DEE_EMAIL_SMTP_USER`/`DEE_EMAIL_SMTP_PASSWORD`).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_boot_config.py -q`
Expected: PASS.

Then the full suite, because a new `Settings` field can break `config.yaml` round-trip tests:
Run: `python -m pytest -q`
Expected: 1200 passed + the new ones.

- [ ] **Step 7: Commit**

```bash
git add app/core/config.py app/core/boot.py config.yaml tests/test_boot_config.py
git commit -m "feat(s82): auth/email/CORS knobs + three prod boot refusals

Insecure session cookie, "*" CORS origin and the capture email provider each
refuse to boot in prod. The boot guard is where launch-time refusals live
(S8.1) and CORS was the roadmap's nominated next candidate.

Also corrects api_auth_key's field comment, which still claimed empty meant
auth disabled. S8.1 made that false, and a stale comment describing a
fail-open default is how the next reader re-derives the wrong model."
```

---

## Task 2: The email seam

**Files:**
- Create: `app/services/email.py`
- Test: `tests/test_email_seam.py`

**Interfaces:**
- Produces: `EmailClient` (ABC, `send(*, to: str, subject: str, body: str) -> None`), `NullEmail`, `CaptureEmail`, `SMTPEmail`, `build_email(settings=None) -> EmailClient`, `EmailUnavailable(Exception)`.
- Consumes: `Settings` from Task 1.

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services.email import (
    CaptureEmail, EmailUnavailable, NullEmail, build_email,
)


def _settings(**over) -> Settings:
    base = dict(_env_file=None, api_auth_key=SecretStr("x"))
    base.update(over)
    return Settings(**base)


def test_null_email_refuses():
    with pytest.raises(EmailUnavailable):
        NullEmail(_settings()).send(to="a@b.com", subject="s", body="b")


def test_null_email_logs_neither_code_nor_destination(caplog):
    """S7.1's NullNotifier posture: an OTP in a log file is an OTP leak, and so
    is the address it went to."""
    with pytest.raises(EmailUnavailable):
        NullEmail(_settings()).send(to="a@b.com", subject="s", body="code 123456")
    assert "123456" not in caplog.text
    assert "a@b.com" not in caplog.text


def test_capture_email_writes_json_lines(tmp_path):
    path = tmp_path / "mail.jsonl"
    client = CaptureEmail(_settings(email_capture_path=str(path)))
    client.send(to="a@b.com", subject="Your code", body="code 123456")
    client.send(to="c@d.com", subject="Your code", body="code 654321")
    lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert [l["to"] for l in lines] == ["a@b.com", "c@d.com"]
    assert "123456" in lines[0]["body"]


def test_build_email_defaults_to_the_refusing_client():
    assert isinstance(build_email(_settings()), NullEmail)


def test_build_email_never_falls_back_to_capture():
    """Selecting capture by accident would be PI-8 section 1's bug again: a
    test harness reachable in production because nobody configured the real one."""
    assert isinstance(build_email(_settings(email_provider="smtp")), NullEmail)  # no host
    assert isinstance(build_email(_settings(email_provider="null")), NullEmail)


def test_build_email_selects_capture_only_when_asked(tmp_path):
    client = build_email(
        _settings(email_provider="capture", email_capture_path=str(tmp_path / "m.jsonl"))
    )
    assert isinstance(client, CaptureEmail)


def test_capture_requires_a_path(tmp_path):
    """A capture client with nowhere to write is a silent black hole."""
    assert isinstance(build_email(_settings(email_provider="capture")), NullEmail)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_email_seam.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.email'`.

- [ ] **Step 3: Implement the seam**

```python
"""Email delivery seam -- config-driven, credentials never hardcoded (S8.2).

Deliberately shaped like app/services/llm.py and app/services/speech.py, which
have survived seven PIs: an abstract client, a live implementation, and a Null
that REFUSES so tests need no network and a key-less deployment still works.

The refusal matters and is not an error path to paper over. With no provider,
signup and login return 503 email_unavailable rather than appearing to succeed
-- the NullSpeech posture from S7.3.

This also gives S7.1's L2 contact-control assurance its first real delivery
path: NullNotifier logs neither code nor destination, so the ladder's second
rung has been theoretical since 2026-07-31.
"""

from __future__ import annotations

import json
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class EmailUnavailable(Exception):
    """No email provider is configured. The caller should surface a clear 503 --
    this is the designed no-provider path, not a malfunction."""


class EmailSendFailed(Exception):
    """A configured provider could not deliver. The caller must NOT consume the
    challenge: a retry has to be free, so an SMTP outage never costs a login."""


class EmailClient(ABC):
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    @abstractmethod
    def send(self, *, to: str, subject: str, body: str) -> None: ...


class NullEmail(EmailClient):
    """Ships nothing. Logs the attempt WITHOUT the address or the body -- an OTP
    in a log file is an OTP leak, and so is who it was for (S7.1 NullNotifier)."""

    def send(self, *, to: str, subject: str, body: str) -> None:
        log.info("email.dispatch.refused", provider="null")
        raise EmailUnavailable(
            "no email provider is configured; set email_provider=smtp"
        )


class CaptureEmail(EmailClient):
    """Writes messages as JSON lines to `email_capture_path` instead of sending.

    This is how the key-less smoke drives a real login end to end. It is
    selected ONLY by explicit config -- never by fallback -- and prod refuses to
    boot with it (app/core/boot.py).
    """

    def send(self, *, to: str, subject: str, body: str) -> None:
        path = Path(self.settings.email_capture_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"to": to, "subject": subject, "body": body}) + "\n")
        log.info("email.dispatch.captured")


class SMTPEmail(EmailClient):
    """Live delivery over SMTP with STARTTLS. Credentials come from .env."""

    def send(self, *, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.settings.email_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(
                self.settings.email_smtp_host, self.settings.email_smtp_port, timeout=15
            ) as smtp:
                if self.settings.email_smtp_starttls:
                    smtp.starttls()
                user = self.settings.email_smtp_user.get_secret_value()
                if user:
                    smtp.login(user, self.settings.email_smtp_password.get_secret_value())
                smtp.send_message(msg)
        except Exception as exc:  # noqa: BLE001 -- one failure surface for the caller
            log.warning("email.dispatch.failed", error=str(exc))
            raise EmailSendFailed(f"email delivery failed: {exc}") from exc
        log.info("email.dispatch.sent")


def build_email(settings: Optional[Settings] = None) -> EmailClient:
    settings = settings or get_settings()
    if settings.email_provider == "smtp" and settings.email_smtp_host:
        return SMTPEmail(settings)
    if settings.email_provider == "capture" and settings.email_capture_path:
        return CaptureEmail(settings)
    # Everything else -- including a misconfigured smtp/capture -- REFUSES.
    # Silent degradation into a working-looking client is PI-8 section 1's bug.
    log.warning(
        "email_unavailable",
        provider=settings.email_provider,
        detail="Signup and login will return 503 email_unavailable.",
    )
    return NullEmail(settings)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_email_seam.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/email.py tests/test_email_seam.py
git commit -m "feat(s82): email seam -- Null refuses, Capture only by explicit config

Shaped like llm.py/speech.py. NullEmail refuses so signup/login return a clear
503 instead of appearing to succeed, and it logs neither the address nor the
body. CaptureEmail is how the key-less smoke drives a real login; build_email
never falls back into it, including from a misconfigured smtp provider.

Also gives S7.1's L2 contact-control rung its first real delivery path."
```

---

## Task 3: `app/auth/schema.py` — the contracts

**Files:**
- Create: `app/auth/__init__.py` (empty), `app/auth/schema.py`
- Test: `tests/test_auth_schema.py`

**Interfaces:**
- Produces: `PrincipalKind`, `PrincipalVia`, `AuthPlane`, `LoginPurpose`, `SessionStatus`, `Principal`, `SessionView`, `OrgUser`, `AdminUser`, `OrgUserRole`.
- Consumed by: every later task.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from pydantic import ValidationError

from app.auth.schema import (
    AuthPlane, LoginPurpose, Principal, PrincipalKind, PrincipalVia,
    SessionStatus, SessionView,
)


def test_principal_kinds_and_planes_are_strings():
    assert PrincipalKind.CANDIDATE == "candidate"
    assert PrincipalKind.ORG == "org"
    assert PrincipalKind.ADMIN == "admin"
    assert AuthPlane.CANDIDATE == "candidate"
    assert LoginPurpose.SIGNUP == "signup"
    assert LoginPurpose.LOGIN == "login"


def test_principal_records_how_it_was_established():
    """CSRF enforcement reads `via`. Without it on the object the exemption
    inevitably gets written as 'was a header present?', which is the bypass."""
    p = Principal(kind=PrincipalKind.ORG, via=PrincipalVia.KEY, org_id="org-1")
    assert p.via == PrincipalVia.KEY
    assert p.org_user_id is None      # a key is not a person
    assert p.session_id is None


def test_a_session_principal_names_the_human():
    p = Principal(
        kind=PrincipalKind.ORG, via=PrincipalVia.SESSION,
        org_id="org-1", org_user_id="ou-1", session_id="s-1",
    )
    assert p.org_user_id == "ou-1"


def test_session_view_never_carries_the_token():
    assert "token" not in SessionView.model_fields
    assert "token_hash" not in SessionView.model_fields


def test_session_statuses():
    assert set(SessionStatus) == {
        SessionStatus.ACTIVE, SessionStatus.EXPIRED,
        SessionStatus.IDLE_EXPIRED, SessionStatus.REVOKED,
    }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_auth_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth'`.

- [ ] **Step 3: Implement**

Create `app/auth/__init__.py` (empty file), then `app/auth/schema.py`:

```python
"""Auth contracts (S8.2). Pure Pydantic + StrEnum -- no I/O, no ORM.

`Principal` is the single answer to "who is calling?" for all three planes. It
deliberately carries HOW it was established (`via`) as well as who: CSRF
enforcement keys on that field, and an exemption written against "was a header
present?" instead is a bypass (spec section 4.2).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class PrincipalKind(StrEnum):
    CANDIDATE = "candidate"
    ORG = "org"
    ADMIN = "admin"


class PrincipalVia(StrEnum):
    """How the principal was established. SESSION is the stricter one: it is
    cookie-borne and therefore CSRF-checked."""

    SESSION = "session"
    KEY = "key"


class AuthPlane(StrEnum):
    """Which login surface a challenge belongs to. One address can legitimately
    be both a candidate and an org user, so challenges are scoped by plane."""

    CANDIDATE = "candidate"
    ORG = "org"
    ADMIN = "admin"


class LoginPurpose(StrEnum):
    SIGNUP = "signup"
    LOGIN = "login"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    IDLE_EXPIRED = "idle_expired"
    REVOKED = "revoked"


class OrgUserRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class Principal(BaseModel):
    """Who is calling, and how. `org_user_id`/`admin_user_id` being None is what
    distinguishes a machine caller from a named human -- which is what makes
    admin action attribution possible (spec section 6.3)."""

    kind: PrincipalKind
    via: PrincipalVia
    candidate_id: Optional[str] = None
    org_id: Optional[str] = None
    org_user_id: Optional[str] = None
    admin_user_id: Optional[str] = None
    session_id: Optional[str] = None


class SessionView(BaseModel):
    """A session as its own owner sees it. Carries no token and no hash: this
    is returned to the portal and to GET /auth/sessions."""

    id: str
    issued_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    status: SessionStatus
    user_agent: Optional[str] = None
    current: bool = False   # is this the session making the request?


class OrgUser(BaseModel):
    id: str
    organization_id: str
    email_hash: str
    role: OrgUserRole = OrgUserRole.MEMBER
    created_at: datetime
    disabled_at: Optional[datetime] = None


class AdminUser(BaseModel):
    id: str
    email_hash: str
    label: str = ""
    created_at: datetime
    disabled_at: Optional[datetime] = None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_auth_schema.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/auth/__init__.py app/auth/schema.py tests/test_auth_schema.py
git commit -m "feat(s82): auth contracts -- Principal carries HOW it was established

Principal.via is not decoration: CSRF enforcement keys on it, and an exemption
written against 'was a header present?' lets a session cookie plus an
attacker-supplied X-Org-Key skip the check entirely."
```

---

## Task 4: Pure session + CSRF token mechanics

**Files:**
- Create: `app/auth/sessions.py`, `app/auth/csrf.py`
- Test: `tests/test_auth_sessions.py`, `tests/test_auth_csrf.py`

**Interfaces:**
- Produces: `generate_token(nbytes) -> str`, `hash_token(raw) -> str`, `effective_status(*, expires_at, last_seen_at, revoked_at, idle_timeout_minutes, at) -> SessionStatus`, `should_write_last_seen(last_seen_at, throttle_seconds, *, at) -> bool`; `generate_csrf_token(nbytes) -> str`, `csrf_matches(cookie_value, header_value) -> bool`.

- [ ] **Step 1: Write the failing tests**

`tests/test_auth_sessions.py`:

```python
from datetime import datetime, timedelta, timezone

from app.auth.schema import SessionStatus
from app.auth.sessions import (
    effective_status, generate_token, hash_token, should_write_last_seen,
)

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _status(**over) -> SessionStatus:
    kw = dict(
        expires_at=NOW + timedelta(hours=1),
        last_seen_at=NOW - timedelta(minutes=5),
        revoked_at=None,
        idle_timeout_minutes=120,
        at=NOW,
    )
    kw.update(over)
    return effective_status(**kw)


def test_a_fresh_session_is_active():
    assert _status() == SessionStatus.ACTIVE


def test_absolute_expiry_wins():
    assert _status(expires_at=NOW - timedelta(seconds=1)) == SessionStatus.EXPIRED


def test_expiry_is_inclusive_at_the_boundary():
    """Dead the instant it expires -- the is_challenge_expired convention."""
    assert _status(expires_at=NOW) == SessionStatus.EXPIRED


def test_idle_timeout():
    assert _status(last_seen_at=NOW - timedelta(minutes=121)) == SessionStatus.IDLE_EXPIRED


def test_revocation_beats_everything():
    assert _status(revoked_at=NOW - timedelta(days=1)) == SessionStatus.REVOKED
    assert _status(
        revoked_at=NOW - timedelta(days=1), expires_at=NOW - timedelta(days=1)
    ) == SessionStatus.REVOKED


def test_naive_datetimes_are_coerced_to_utc():
    """SQLite refetch returns naive datetimes; an uncoerced compare would raise
    or silently mis-window an IST-written row (the S3.1 as_utc lesson)."""
    assert _status(expires_at=datetime(2026, 8, 2, 13, 0)) == SessionStatus.ACTIVE


def test_tokens_are_unguessable_and_distinct():
    a, b = generate_token(32), generate_token(32)
    assert a != b
    assert len(a) >= 32


def test_hash_token_is_stable_sha256_hex():
    assert hash_token("abc") == hash_token("abc")
    assert len(hash_token("abc")) == 64
    assert hash_token("abc") != hash_token("abd")


def test_last_seen_write_is_throttled():
    assert should_write_last_seen(NOW - timedelta(seconds=5), 60, at=NOW) is False
    assert should_write_last_seen(NOW - timedelta(seconds=61), 60, at=NOW) is True
    assert should_write_last_seen(NOW, 0, at=NOW) is True   # throttle disabled
```

`tests/test_auth_csrf.py`:

```python
from app.auth.csrf import csrf_matches, generate_csrf_token


def test_tokens_are_distinct():
    assert generate_csrf_token(32) != generate_csrf_token(32)


def test_matching_tokens_pass():
    t = generate_csrf_token(32)
    assert csrf_matches(t, t) is True


def test_mismatched_tokens_fail():
    assert csrf_matches(generate_csrf_token(32), generate_csrf_token(32)) is False


def test_absent_or_empty_never_matches():
    """An empty cookie and an empty header are equal strings. If that counted as
    a match, a request with neither would pass CSRF."""
    assert csrf_matches("", "") is False
    assert csrf_matches(None, None) is False
    assert csrf_matches("tok", "") is False
    assert csrf_matches("", "tok") is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_auth_sessions.py tests/test_auth_csrf.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.sessions'`.

- [ ] **Step 3: Implement `app/auth/sessions.py`**

```python
"""Pure session mechanics (S8.2). No I/O, no ambient clock.

Expiry -- absolute AND idle -- is computed at READ time and never written by a
job. That is the S7.1 `effective_status` precedent and it holds for the same
reason: no scheduler exists in this repo, and a stored `expired` that nothing
corrects is a lie nobody notices.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from app.auth.schema import SessionStatus
from app.ledger.consent import as_utc


def generate_token(nbytes: int) -> str:
    """URL-safe opaque token. Returned to the caller ONCE; only its hash is
    stored, mirroring CandidateStore.issue_access_key."""
    return secrets.token_urlsafe(nbytes)


def hash_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def effective_status(
    *,
    expires_at: datetime,
    last_seen_at: datetime,
    revoked_at: Optional[datetime],
    idle_timeout_minutes: int,
    at: datetime,
) -> SessionStatus:
    """Revoked beats expired beats idle beats active.

    Revocation is checked FIRST and unconditionally: a revoked session must
    read as revoked even after it would also have expired, because the two
    answer different questions ("was it taken away?" vs "did it lapse?").
    """
    now = as_utc(at)
    if revoked_at is not None:
        return SessionStatus.REVOKED
    if as_utc(expires_at) <= now:          # inclusive: dead the instant it expires
        return SessionStatus.EXPIRED
    if idle_timeout_minutes > 0:
        idle_deadline = as_utc(last_seen_at) + timedelta(minutes=idle_timeout_minutes)
        if idle_deadline <= now:
            return SessionStatus.IDLE_EXPIRED
    return SessionStatus.ACTIVE


def should_write_last_seen(
    last_seen_at: datetime, throttle_seconds: int, *, at: datetime
) -> bool:
    """Idle timeout needs last_seen_at, but writing it on every request turns
    each authenticated GET into a row lock plus a WAL entry on the hottest path
    in the system. The staleness this admits is bounded by the knob and is two
    orders below the idle window, so it cannot change a timeout decision."""
    if throttle_seconds <= 0:
        return True
    return as_utc(at) >= as_utc(last_seen_at) + timedelta(seconds=throttle_seconds)
```

- [ ] **Step 4: Implement `app/auth/csrf.py`**

```python
"""Double-submit CSRF tokens (S8.2). Pure.

SameSite=None is required because the UI is separately hosted (PI-8 decision
0.1), which is precisely why this layer is non-optional rather than
belt-and-braces.
"""

from __future__ import annotations

import hmac
import secrets
from typing import Optional


def generate_csrf_token(nbytes: int) -> str:
    return secrets.token_urlsafe(nbytes)


def csrf_matches(cookie_value: Optional[str], header_value: Optional[str]) -> bool:
    """Constant-time compare, with absent/empty rejected BEFORE the compare.

    Two empty strings are equal, so without this guard a request carrying
    neither cookie nor header would pass -- which is every CSRF attack.
    """
    if not cookie_value or not header_value:
        return False
    return hmac.compare_digest(cookie_value, header_value)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_auth_sessions.py tests/test_auth_csrf.py -q`
Expected: PASS (13 tests).

- [ ] **Step 6: Commit**

```bash
git add app/auth/sessions.py app/auth/csrf.py tests/test_auth_sessions.py tests/test_auth_csrf.py
git commit -m "feat(s82): pure session + CSRF mechanics, clock injected

Read-time expiry (absolute and idle) on the S7.1 effective_status precedent --
no scheduler exists, so a stored 'expired' would be a lie. last_seen_at writes
are throttled because the naive version is a row lock per authenticated GET.

csrf_matches rejects empty BEFORE comparing: two empty strings are equal, so
the obvious implementation passes a request carrying neither cookie nor header."
```

---

## Task 5: `app/auth/challenges.py` — login-OTP policy

**Files:**
- Create: `app/auth/challenges.py`
- Test: `tests/test_auth_challenges.py`

**Interfaces:**
- Consumes: `app/verification/otp.py` (`generate_code`, `hash_code`, `is_challenge_expired`, `attempts_exhausted`, `cooldown_active`), `AuthPlane`, `LoginPurpose` from Task 3.
- Produces: `ChallengeScope` (frozen dataclass: `email_hash`, `purpose`, `plane`), `VerifyOutcome` StrEnum (`OK`/`WRONG_CODE`/`EXPIRED`/`EXHAUSTED`/`NOT_FOUND`), `evaluate_verification(...) -> VerifyOutcome`, `may_send(...) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
import random
from datetime import datetime, timedelta, timezone

from app.auth.challenges import (
    ChallengeScope, VerifyOutcome, evaluate_verification, may_send, mint_code,
)
from app.auth.schema import AuthPlane, LoginPurpose

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _scope(**over) -> ChallengeScope:
    kw = dict(
        email_hash="h1", purpose=LoginPurpose.LOGIN, plane=AuthPlane.CANDIDATE
    )
    kw.update(over)
    return ChallengeScope(**kw)


def test_scope_is_hashable_and_includes_the_plane():
    """One address can legitimately be both a candidate and an org user;
    collapsing the planes would let activity on one lock the other."""
    a = _scope()
    b = _scope(plane=AuthPlane.ORG)
    assert a != b
    assert len({a, b}) == 2


def test_scope_separates_signup_from_login():
    assert _scope() != _scope(purpose=LoginPurpose.SIGNUP)


def test_mint_code_is_deterministic_under_an_injected_rng():
    code, digest = mint_code(6, salt="s", rng=random.Random(7))
    again, _ = mint_code(6, salt="s", rng=random.Random(7))
    assert code == again
    assert len(code) == 6 and code.isdigit()
    assert len(digest) == 64 and digest != code


def test_may_send_respects_cooldown():
    assert may_send(last_sent_at=None, cooldown_seconds=60, at=NOW) is True
    assert may_send(
        last_sent_at=NOW - timedelta(seconds=30), cooldown_seconds=60, at=NOW
    ) is False
    assert may_send(
        last_sent_at=NOW - timedelta(seconds=61), cooldown_seconds=60, at=NOW
    ) is True


def _verify(**over) -> VerifyOutcome:
    kw = dict(
        stored_hash=None, supplied_hash="d", expires_at=NOW + timedelta(minutes=5),
        attempts=0, max_attempts=5, at=NOW,
    )
    kw.update(over)
    return evaluate_verification(**kw)


def test_no_challenge_is_not_found():
    assert _verify(stored_hash=None) == VerifyOutcome.NOT_FOUND


def test_correct_code_passes():
    assert _verify(stored_hash="d", supplied_hash="d") == VerifyOutcome.OK


def test_wrong_code_fails():
    assert _verify(stored_hash="d", supplied_hash="x") == VerifyOutcome.WRONG_CODE


def test_expired_beats_correct():
    """An expired challenge must not be redeemable even with the right code."""
    assert _verify(
        stored_hash="d", supplied_hash="d", expires_at=NOW
    ) == VerifyOutcome.EXPIRED


def test_exhausted_beats_correct():
    """Ordering matters: checking the code first would let an attacker keep
    guessing past the cap as long as the last guess happened to be right."""
    assert _verify(
        stored_hash="d", supplied_hash="d", attempts=5, max_attempts=5
    ) == VerifyOutcome.EXHAUSTED
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_auth_challenges.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.challenges'`.

- [ ] **Step 3: Implement**

```python
"""Login-OTP POLICY (S8.2), layered over app/verification/otp.py's MECHANICS.

Login reuses the FUNCTIONS, not the TABLE: `verification_challenges` is
candidate-scoped identity verification and stays that way, while login
authentication belongs to a principal that may not exist yet.

Cooldown and attempt caps are scoped to email_hash + purpose + PLANE, applying
S7.1's own review finding verbatim -- a limit scoped to a row that the flow
re-mints limits nothing. `plane` is added on top of PI-8 section 4.4 because one
address can legitimately be both a candidate and an org user, and collapsing
those would let activity on one plane lock the other.
"""

from __future__ import annotations

import hmac
import random
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Optional

from app.auth.schema import AuthPlane, LoginPurpose
from app.verification import otp as otp_logic


@dataclass(frozen=True)
class ChallengeScope:
    """The unit a cooldown and an attempt cap apply to."""

    email_hash: str
    purpose: LoginPurpose
    plane: AuthPlane


class VerifyOutcome(StrEnum):
    OK = "ok"
    WRONG_CODE = "wrong_code"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"
    NOT_FOUND = "not_found"


def mint_code(length: int, *, salt: str, rng: random.Random) -> tuple[str, str]:
    """Return (plaintext, digest). The plaintext exists only long enough to hand
    to the email client; only the digest is ever stored."""
    code = otp_logic.generate_code(length, rng=rng)
    return code, otp_logic.hash_code(code, salt)


def may_send(
    *, last_sent_at: Optional[datetime], cooldown_seconds: int, at: datetime
) -> bool:
    return not otp_logic.cooldown_active(last_sent_at, cooldown_seconds, at=at)


def evaluate_verification(
    *,
    stored_hash: Optional[str],
    supplied_hash: str,
    expires_at: datetime,
    attempts: int,
    max_attempts: int,
    at: datetime,
) -> VerifyOutcome:
    """Order is load-bearing: exhaustion and expiry are checked BEFORE the code.

    Checking the code first would let an attacker keep guessing past the cap so
    long as the final guess happened to be right -- which is exactly the guess
    a brute-forcer is making.
    """
    if stored_hash is None:
        return VerifyOutcome.NOT_FOUND
    if otp_logic.attempts_exhausted(attempts, max_attempts):
        return VerifyOutcome.EXHAUSTED
    if otp_logic.is_challenge_expired(expires_at, at=at):
        return VerifyOutcome.EXPIRED
    if not hmac.compare_digest(stored_hash, supplied_hash):
        return VerifyOutcome.WRONG_CODE
    return VerifyOutcome.OK
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_auth_challenges.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add app/auth/challenges.py tests/test_auth_challenges.py
git commit -m "feat(s82): login-OTP policy over S7.1's pure mechanics

Reuses the functions, not the table: verification_challenges is candidate-scoped
identity verification and stays that way. Scope is email_hash+purpose+PLANE --
one address can legitimately be both a candidate and an org user.

evaluate_verification checks exhaustion and expiry BEFORE the code, because the
reverse lets an attacker guess past the cap when the last guess is the right one."
```

---

## Task 6: ORM rows, migration `0017`, and the schema guards

**Files:**
- Create: `app/auth/models.py`, `alembic/versions/0017_auth_identity.py`
- Modify: `tests/test_migrations.py`
- Test: `tests/test_auth_models.py`

**Interfaces:**
- Consumes: `app.core.db.Base`.
- Produces: `OrgUserRow`, `AdminUserRow`, `AuthSessionRow`, `LoginChallengeRow` — table names `org_users`, `admin_users`, `auth_sessions`, `login_challenges`.

- [ ] **Step 1: Write the failing tests**

`tests/test_auth_models.py` — the cascade tests are written **before** the store exists, deliberately: they must pass with no service orchestration at all, which is the whole point of putting the guarantee in the database. This is the S8.1 fold ordering, reapplied.

```python
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.auth.models import AdminUserRow, AuthSessionRow, LoginChallengeRow, OrgUserRow
from app.candidates.models import CandidateRow
from app.ledger.models import OrganizationRow
from tests.conftest import make_candidate_store


def _factory():
    return make_candidate_store()._session_factory


def test_session_cascades_when_its_candidate_is_erased():
    """No route orchestration anywhere in this test -- the database is the
    guarantee, exactly as the S8.1 fold established."""
    sf = _factory()
    with sf() as s:
        cand = CandidateRow(email_hash="h")
        s.add(cand)
        s.flush()
        s.add(AuthSessionRow(
            candidate_id=cand.id, token_hash="t1",
            expires_at=sa.func.now(), last_seen_at=sa.func.now(),
        ))
        s.commit()
        cid = cand.id
    with sf() as s:
        s.delete(s.get(CandidateRow, cid))
        s.commit()
    with sf() as s:
        assert s.execute(sa.select(AuthSessionRow)).scalars().all() == []


def test_session_cascades_when_its_org_is_deleted():
    sf = _factory()
    with sf() as s:
        org = OrganizationRow(name="Acme")
        s.add(org)
        s.flush()
        ou = OrgUserRow(organization_id=org.id, email_hash="h", role="owner")
        s.add(ou)
        s.flush()
        s.add(AuthSessionRow(
            org_user_id=ou.id, token_hash="t2",
            expires_at=sa.func.now(), last_seen_at=sa.func.now(),
        ))
        s.commit()
        oid = org.id
    with sf() as s:
        s.delete(s.get(OrganizationRow, oid))
        s.commit()
    with sf() as s:
        assert s.execute(sa.select(AuthSessionRow)).scalars().all() == []
        assert s.execute(sa.select(OrgUserRow)).scalars().all() == []


def test_a_session_with_no_principal_is_rejected():
    sf = _factory()
    with sf() as s:
        s.add(AuthSessionRow(
            token_hash="t3", expires_at=sa.func.now(), last_seen_at=sa.func.now()
        ))
        with pytest.raises(IntegrityError):
            s.commit()


def test_a_session_with_two_principals_is_rejected():
    """The exclusive arc is a CHECK, not a convention: a session that is both a
    candidate and an operator would authorize as whichever the reader asked for."""
    sf = _factory()
    with sf() as s:
        cand = CandidateRow(email_hash="h")
        admin = AdminUserRow(email_hash="a", label="ops")
        s.add_all([cand, admin])
        s.flush()
        s.add(AuthSessionRow(
            candidate_id=cand.id, admin_user_id=admin.id, token_hash="t4",
            expires_at=sa.func.now(), last_seen_at=sa.func.now(),
        ))
        with pytest.raises(IntegrityError):
            s.commit()


def test_login_challenges_have_no_foreign_key():
    """At signup time no principal exists, so there is nothing to point at --
    which is exactly why erasure has to delete them explicitly (spec 8.1)."""
    assert list(LoginChallengeRow.__table__.foreign_keys) == []
```

Extend `tests/test_migrations.py`: add the import, the table assertions and the guard tuple.

```python
# with the other Base.metadata imports at the top
import app.auth.models  # noqa: F401 — populate Base.metadata

# inside test_upgrade_head_creates_candidate_tables
    assert "org_users" in names           # S8.2 migration 0017
    assert "admin_users" in names         # S8.2 migration 0017
    assert "auth_sessions" in names       # S8.2 migration 0017
    assert "login_challenges" in names    # S8.2 migration 0017

# beside the other guard tuples
AUTH_TABLES = ("org_users", "admin_users", "auth_sessions", "login_challenges")  # S8.2
```

Then append `+ AUTH_TABLES` to the `for table in ...` loop in `test_migrated_indexes_match_orm`, and to the equivalent loop in `test_migrated_fks_and_nullability_match_orm`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_auth_models.py tests/test_migrations.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.models'`.

- [ ] **Step 3: Implement `app/auth/models.py`**

```python
"""ORM rows for auth (S8.2). Postgres-shaped on SQLite.

auth_sessions uses an EXCLUSIVE ARC -- three nullable FKs plus a CHECK that
exactly one is non-null -- rather than a polymorphic subject_type+subject_id.
A polymorphic id column CANNOT carry a foreign key, so erasure would stop
cascading, silently breaking a guarantee that has held for eight PIs. Three
nullable FKs keep the cascade in the database, where it belongs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrgUserRow(Base):
    """A human who logs into an organization. An org's X-Org-Key is a MACHINE
    credential and is unaffected -- both modes are permanent (PI-8 0.4)."""

    __tablename__ = "org_users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email_hash", name="uq_org_users_org_email"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email_hash: Mapped[str] = mapped_column(String(64), index=True)
    # owner | member. The invite endpoints are a NON-GOAL for S8.2, but the
    # column ships now so adding them later needs no migration.
    role: Mapped[str] = mapped_column(String(16), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    disabled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AdminUserRow(Base):
    """A platform operator. No FK: operators are not data principals in the DPDP
    sense, and there is nothing for them to cascade from."""

    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    disabled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuthSessionRow(Base):
    """One opaque server-side session. Exactly one principal, always."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN candidate_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN org_user_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN admin_user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_auth_sessions_exactly_one_principal",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True, index=True
    )
    org_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("org_users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    admin_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    csrf_token: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # A hash, never a raw IP: store what identifies, not what re-identifies.
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class LoginChallengeRow(Base):
    """A pending email-OTP login/signup. NO FK -- at signup time no principal
    exists yet, which is precisely why DELETE /portal/me must delete these
    explicitly by email_hash (spec 8.1)."""

    __tablename__ = "login_challenges"
    __table_args__ = (
        UniqueConstraint(
            "email_hash", "purpose", "plane", name="uq_login_challenges_scope"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email_hash: Mapped[str] = mapped_column(String(64), index=True)
    purpose: Mapped[str] = mapped_column(String(16))
    plane: Mapped[str] = mapped_column(String(16))
    code_hash: Mapped[str] = mapped_column(String(64))
    # Signup-only data that must survive the OTP round trip (today: the
    # organization name). Never read on a `login` purpose.
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 4: Write the migration**

`alembic/versions/0017_auth_identity.py`:

```python
"""org_users, admin_users, auth_sessions, login_challenges (S8.2)

Revision ID: 0017_auth_identity
Revises: 0016_reports_outcomes
Create Date: 2026-08-02

Sessions are opaque server-side rows, not JWTs: a JWT stays valid after a
candidate revokes consent or erases their account, which is a DPDP correctness
bug rather than a preference (PI-8 decision 0.2).

auth_sessions carries three nullable FKs and a CHECK that exactly one is
non-null. A polymorphic subject_type+subject_id cannot carry a foreign key, so
erasure would stop cascading -- the guarantee this whole architecture rests on.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_auth_identity"
down_revision = "0016_reports_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("organization_id", "email_hash", name="uq_org_users_org_email"),
    )
    op.create_index("ix_org_users_organization_id", "org_users", ["organization_id"])
    op.create_index("ix_org_users_email_hash", "org_users", ["email_hash"])

    op.create_table(
        "admin_users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_admin_users_email_hash", "admin_users", ["email_hash"], unique=True
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column("org_user_id", sa.String(length=36), nullable=True),
        sa.Column("admin_user_id", sa.String(length=36), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_user_id"], ["org_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "(CASE WHEN candidate_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN org_user_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN admin_user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_auth_sessions_exactly_one_principal",
        ),
    )
    op.create_index("ix_auth_sessions_candidate_id", "auth_sessions", ["candidate_id"])
    op.create_index("ix_auth_sessions_org_user_id", "auth_sessions", ["org_user_id"])
    op.create_index("ix_auth_sessions_admin_user_id", "auth_sessions", ["admin_user_id"])
    op.create_index(
        "ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True
    )

    op.create_table(
        "login_challenges",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("plane", sa.String(length=16), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "email_hash", "purpose", "plane", name="uq_login_challenges_scope"
        ),
    )
    op.create_index("ix_login_challenges_email_hash", "login_challenges", ["email_hash"])


def downgrade() -> None:
    op.drop_index("ix_login_challenges_email_hash", table_name="login_challenges")
    op.drop_table("login_challenges")
    for ix in (
        "ix_auth_sessions_token_hash", "ix_auth_sessions_admin_user_id",
        "ix_auth_sessions_org_user_id", "ix_auth_sessions_candidate_id",
    ):
        op.drop_index(ix, table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_admin_users_email_hash", table_name="admin_users")
    op.drop_table("admin_users")
    op.drop_index("ix_org_users_email_hash", table_name="org_users")
    op.drop_index("ix_org_users_organization_id", table_name="org_users")
    op.drop_table("org_users")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_auth_models.py tests/test_migrations.py -q`
Expected: PASS. If the drift guard reports a mismatch, **fix the migration to match the ORM** — that guard caught a real drift in S7.1 and is the point of running it here.

Then verify the migration reverses cleanly:
Run: `python -m pytest tests/test_migrations.py -q -k "upgrade or drift or index or fks"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/auth/models.py alembic/versions/0017_auth_identity.py tests/test_auth_models.py tests/test_migrations.py
git commit -m "feat(s82): migration 0017 -- four auth tables, cascades written first

auth_sessions is an exclusive arc (three nullable FKs + a CHECK that exactly
one is non-null), not a polymorphic subject_type+subject_id: a polymorphic id
cannot carry a foreign key, so erasure would stop cascading.

The cascade tests pass with NO service orchestration at all -- the S8.1 fold
ordering reapplied. login_challenges deliberately has no FK, which is why
erasure has to delete them explicitly (a later task)."
```

---

## Task 7: `AuthStore`

**Files:**
- Create: `app/auth/store.py`
- Modify: `app/candidates/store.py` (add `find_by_email_hash`, `create_bare_candidate`)
- Test: `tests/test_auth_store.py`

**Interfaces:**
- Produces:
  - `AuthStore(session_factory, *, settings)` with `create_session(*, kind, subject_id, csrf_token, at, user_agent=None, ip_hash=None) -> tuple[str, SessionView]` (returns **plaintext token** + view), `session_by_token(raw, *, at) -> tuple[Optional[AuthSessionRow], SessionStatus]`, `touch(session_id, *, at)`, `revoke(session_id, *, at) -> bool`, `sessions_for(*, kind, subject_id, at) -> list[SessionView]`, `revoke_all_for_candidate(candidate_id, *, at) -> int`
  - `upsert_challenge(scope, *, code_hash, expires_at, payload, at)`, `get_challenge(scope) -> Optional[LoginChallengeRow]`, `bump_attempts(scope) -> None`, `delete_challenge(scope) -> None`, `delete_challenges_for_email(email_hash) -> int`, `purge_expired_for_email(email_hash, *, at) -> None`
  - `create_org_user(...) -> OrgUser`, `org_user_by_email(email_hash) -> Optional[OrgUser]`, `create_admin_user(...) -> AdminUser`, `admin_user_by_email(...)`, `list_admin_users()`, `delete_admin_user(id) -> bool`
  - `CandidateStore.find_by_email_hash(email_hash) -> Optional[str]`, `CandidateStore.create_bare_candidate(*, email_hash) -> str`

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime, timedelta, timezone

from pydantic import SecretStr

from app.auth.challenges import ChallengeScope
from app.auth.schema import AuthPlane, LoginPurpose, PrincipalKind, SessionStatus
from app.auth.store import AuthStore
from app.candidates.models import CandidateRow
from app.core.config import Settings
from tests.conftest import make_candidate_store

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def _fixture():
    candidates = make_candidate_store()
    settings = Settings(_env_file=None, api_auth_key=SecretStr("x"))
    store = AuthStore(candidates._session_factory, settings=settings)
    with candidates._session_factory() as s:
        cand = CandidateRow(email_hash="hash-1")
        s.add(cand)
        s.commit()
        cid = cand.id
    return candidates, store, cid


def test_create_session_returns_plaintext_once_and_stores_only_a_hash():
    _, store, cid = _fixture()
    raw, view = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    assert raw and len(raw) > 20
    row, status = store.session_by_token(raw, at=NOW)
    assert status == SessionStatus.ACTIVE
    assert row.token_hash != raw
    assert view.id == row.id


def test_an_unknown_token_resolves_to_nothing():
    _, store, _ = _fixture()
    row, status = store.session_by_token("nope", at=NOW)
    assert row is None


def test_revoked_session_reads_revoked_immediately():
    _, store, cid = _fixture()
    raw, view = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    assert store.revoke(view.id, at=NOW) is True
    _, status = store.session_by_token(raw, at=NOW)
    assert status == SessionStatus.REVOKED


def test_expiry_and_idle_are_read_time_not_written():
    _, store, cid = _fixture()
    raw, _ = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    later = NOW + timedelta(minutes=121)
    _, status = store.session_by_token(raw, at=later)
    assert status == SessionStatus.IDLE_EXPIRED
    much_later = NOW + timedelta(hours=13)
    _, status = store.session_by_token(raw, at=much_later)
    assert status == SessionStatus.EXPIRED


def test_erasing_the_candidate_kills_the_session():
    candidates, store, cid = _fixture()
    raw, _ = store.create_session(
        kind=PrincipalKind.CANDIDATE, subject_id=cid, csrf_token="c", at=NOW
    )
    candidates.delete_candidate(cid)
    row, _ = store.session_by_token(raw, at=NOW)
    assert row is None


def test_challenge_upsert_supersedes_rather_than_accumulating():
    _, store, _ = _fixture()
    scope = ChallengeScope(
        email_hash="h", purpose=LoginPurpose.LOGIN, plane=AuthPlane.CANDIDATE
    )
    store.upsert_challenge(
        scope, code_hash="a", expires_at=NOW + timedelta(minutes=10), payload={}, at=NOW
    )
    store.upsert_challenge(
        scope, code_hash="b", expires_at=NOW + timedelta(minutes=10), payload={}, at=NOW
    )
    row = store.get_challenge(scope)
    assert row.code_hash == "b"
    assert row.attempts == 0     # a fresh code gets a fresh attempt budget


def test_challenges_are_scoped_by_plane_and_purpose():
    _, store, _ = _fixture()
    a = ChallengeScope("h", LoginPurpose.LOGIN, AuthPlane.CANDIDATE)
    b = ChallengeScope("h", LoginPurpose.LOGIN, AuthPlane.ORG)
    store.upsert_challenge(a, code_hash="a", expires_at=NOW + timedelta(minutes=10),
                           payload={}, at=NOW)
    store.upsert_challenge(b, code_hash="b", expires_at=NOW + timedelta(minutes=10),
                           payload={}, at=NOW)
    assert store.get_challenge(a).code_hash == "a"
    assert store.get_challenge(b).code_hash == "b"


def test_delete_challenges_for_email_covers_every_plane():
    """DELETE /portal/me relies on this: login_challenges has no FK, so nothing
    cascades and an outstanding challenge would outlive the person."""
    _, store, _ = _fixture()
    for plane in (AuthPlane.CANDIDATE, AuthPlane.ORG):
        store.upsert_challenge(
            ChallengeScope("h", LoginPurpose.LOGIN, plane),
            code_hash="x", expires_at=NOW + timedelta(minutes=10), payload={}, at=NOW,
        )
    assert store.delete_challenges_for_email("h") == 2
    assert store.get_challenge(ChallengeScope("h", LoginPurpose.LOGIN, AuthPlane.ORG)) is None


def test_candidate_lookup_and_bare_creation():
    candidates, _, cid = _fixture()
    assert candidates.find_by_email_hash("hash-1") == cid
    assert candidates.find_by_email_hash("nobody") is None
    new_id = candidates.create_bare_candidate(email_hash="fresh")
    assert candidates.find_by_email_hash("fresh") == new_id
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_auth_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.store'`.

- [ ] **Step 3: Add the two `CandidateStore` methods**

In `app/candidates/store.py`, immediately after `authenticate_candidate`:

```python
    # -- self-registration support (S8.2) --------------------------------------

    def find_by_email_hash(self, email_hash: str) -> Optional[str]:
        """The candidate whose contact hash matches, else None.

        This is what lets a self-registering candidate CLAIM the record built
        from a resume an org uploaded. The hash must be produced by the same
        salted function that wrote it (app/candidates/hashing.contact_hash with
        settings.contact_hash_salt) or nothing will ever match.
        """
        if not email_hash:
            return None
        with self._session_factory() as session:
            row = session.execute(
                select(CandidateRow).where(CandidateRow.email_hash == email_hash)
            ).scalars().first()
            return row.id if row else None

    def create_bare_candidate(self, *, email_hash: str) -> str:
        """A candidate row with a contact hash and nothing else -- someone who
        signed up before any resume of theirs was ever submitted."""
        with self._session_factory() as session:
            row = CandidateRow(email_hash=email_hash)
            session.add(row)
            session.commit()
            return row.id
```

- [ ] **Step 4: Implement `app/auth/store.py`**

Write `AuthStore` against the interfaces listed above. Required behaviours, each pinned by a test in Step 1:

- `create_session` mints via `sessions.generate_token(settings.session_token_bytes)`, stores **only** `hash_token(raw)`, sets `expires_at = at + session_ttl_minutes`, `last_seen_at = at`, and writes `candidate_id`/`org_user_id`/`admin_user_id` from `kind` — never more than one.
- `session_by_token` looks up by `hash_token(raw)`, returns `(None, SessionStatus.REVOKED)` when absent, otherwise `(row, sessions.effective_status(...))` using `settings.session_idle_timeout_minutes`.
- `touch` writes `last_seen_at` **only** when `sessions.should_write_last_seen(row.last_seen_at, settings.session_last_seen_write_seconds, at=at)`.
- `upsert_challenge` deletes any existing row for the scope and inserts a fresh one — supersession, so `attempts` resets with the code. Rows carry `payload` verbatim.
- `delete_challenges_for_email` deletes across **all** purposes and planes and returns the count.
- `purge_expired_for_email` deletes expired rows for that email — the opportunistic hygiene that avoids inventing a scheduler.
- All datetimes are normalized with `as_utc` on write, because SQLite drops `tzinfo` on refetch (the S3.1 lesson).

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_auth_store.py -q`
Expected: PASS (9 tests).

- [ ] **Step 6: Commit**

```bash
git add app/auth/store.py app/candidates/store.py tests/test_auth_store.py
git commit -m "feat(s82): AuthStore -- sessions, challenges, org/admin users

Plaintext token returned once, only the sha256 stored (issue_access_key's
pattern). Expiry and idle are read-time. upsert_challenge supersedes rather
than accumulating, so a fresh code gets a fresh attempt budget.

CandidateStore gains find_by_email_hash/create_bare_candidate, which is what
lets a self-registering candidate claim the record built from an org-uploaded
resume rather than forking a duplicate person."
```

---

## Task 8: `AuthService` — the gate

**Files:**
- Create: `app/auth/service.py`
- Modify: `app/services/__init__.py` (add `auth`, `email` to `Services` + `build_default_services`), `tests/conftest.py` (build them in `make_services`)
- Test: `tests/test_auth_service.py`

**Interfaces:**
- Produces: `AuthService`, `build_auth_service(settings, *, candidates, ledger, email)`; `EmailUnavailableError`, `ChallengeRefused(Exception)` with `.reason: VerifyOutcome`.
  - `request_code(*, email, plane, purpose, payload=None, at, rng) -> None`
  - `verify_code(*, email, plane, purpose, code, at, user_agent=None, ip_hash=None) -> tuple[str, str, Principal]` → `(session_token, csrf_token, principal)`
  - `resolve_principal(request, *, kind) -> Principal` (raises `HTTPException` 401)
  - `resolve_any(request) -> Principal`
  - `logout(principal) -> bool`, `sessions_for(principal) -> list[SessionView]`, `revoke_session(principal, session_id) -> bool`
- Consumes: Tasks 2–7.

- [ ] **Step 1: Write the failing test**

```python
import random
from datetime import datetime, timedelta, timezone

import pytest

from app.auth.schema import AuthPlane, LoginPurpose, PrincipalKind, PrincipalVia
from app.auth.service import ChallengeRefused, EmailUnavailableError

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
RNG = lambda: random.Random(1234)   # noqa: E731 — deterministic codes in tests


def _code_from(capture_path) -> str:
    """Pull the six-digit code out of the last captured message."""
    import json, re
    line = json.loads(capture_path.read_text(encoding="utf-8").splitlines()[-1])
    return re.search(r"\b(\d{6})\b", line["body"]).group(1)


def test_signup_then_verify_creates_an_org_and_a_session(auth_fixture):
    svc, capture, _ = auth_fixture
    svc.request_code(
        email="ops@acme.in", plane=AuthPlane.ORG, purpose=LoginPurpose.SIGNUP,
        payload={"organization_name": "Acme"}, at=NOW, rng=RNG(),
    )
    token, csrf, principal = svc.verify_code(
        email="ops@acme.in", plane=AuthPlane.ORG, purpose=LoginPurpose.SIGNUP,
        code=_code_from(capture), at=NOW,
    )
    assert token and csrf
    assert principal.kind == PrincipalKind.ORG
    assert principal.via == PrincipalVia.SESSION
    assert principal.org_id and principal.org_user_id


def test_candidate_signup_claims_an_existing_candidate(auth_fixture, existing_candidate):
    """The sprint's most security-consequential behaviour: OTP against the
    email_hash already on file connects the data principal to the record built
    from a resume someone else uploaded."""
    svc, capture, _ = auth_fixture
    cid, email = existing_candidate
    svc.request_code(email=email, plane=AuthPlane.CANDIDATE,
                     purpose=LoginPurpose.SIGNUP, at=NOW, rng=RNG())
    _, _, principal = svc.verify_code(
        email=email, plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
        code=_code_from(capture), at=NOW,
    )
    assert principal.candidate_id == cid    # claimed, not duplicated


def test_candidate_signup_with_an_unknown_email_creates_a_bare_candidate(auth_fixture):
    svc, capture, _ = auth_fixture
    svc.request_code(email="new@person.in", plane=AuthPlane.CANDIDATE,
                     purpose=LoginPurpose.SIGNUP, at=NOW, rng=RNG())
    _, _, principal = svc.verify_code(
        email="new@person.in", plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.SIGNUP, code=_code_from(capture), at=NOW,
    )
    assert principal.candidate_id


def test_signup_does_not_grant_identity_assurance(auth_fixture, existing_candidate):
    """Logging in is not being verified. Fusing them would repeat S7.2's
    two-ladders mistake."""
    svc, capture, verification = auth_fixture[0], auth_fixture[1], auth_fixture[2]
    cid, email = existing_candidate
    svc.request_code(email=email, plane=AuthPlane.CANDIDATE,
                     purpose=LoginPurpose.SIGNUP, at=NOW, rng=RNG())
    svc.verify_code(email=email, plane=AuthPlane.CANDIDATE,
                    purpose=LoginPurpose.SIGNUP, code=_code_from(capture), at=NOW)
    assert verification.assurance_for(cid).level == 0


def test_wrong_code_refuses_and_counts_an_attempt(auth_fixture):
    svc, capture, _ = auth_fixture
    svc.request_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                     purpose=LoginPurpose.SIGNUP, at=NOW, rng=RNG())
    with pytest.raises(ChallengeRefused):
        svc.verify_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                        purpose=LoginPurpose.SIGNUP, code="000000", at=NOW)


def test_reused_code_refuses(auth_fixture):
    svc, capture, _ = auth_fixture
    svc.request_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                     purpose=LoginPurpose.SIGNUP, at=NOW, rng=RNG())
    code = _code_from(capture)
    svc.verify_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                    purpose=LoginPurpose.SIGNUP, code=code, at=NOW)
    with pytest.raises(ChallengeRefused):
        svc.verify_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                        purpose=LoginPurpose.SIGNUP, code=code, at=NOW)


def test_expired_code_refuses(auth_fixture):
    svc, capture, _ = auth_fixture
    svc.request_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                     purpose=LoginPurpose.SIGNUP, at=NOW, rng=RNG())
    with pytest.raises(ChallengeRefused):
        svc.verify_code(
            email="a@b.in", plane=AuthPlane.CANDIDATE, purpose=LoginPurpose.SIGNUP,
            code=_code_from(capture), at=NOW + timedelta(minutes=11),
        )


def test_over_attempted_code_refuses_even_when_finally_correct(auth_fixture):
    svc, capture, _ = auth_fixture
    svc.request_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                     purpose=LoginPurpose.SIGNUP, at=NOW, rng=RNG())
    code = _code_from(capture)
    for _ in range(5):
        with pytest.raises(ChallengeRefused):
            svc.verify_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                            purpose=LoginPurpose.SIGNUP, code="000000", at=NOW)
    with pytest.raises(ChallengeRefused):
        svc.verify_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                        purpose=LoginPurpose.SIGNUP, code=code, at=NOW)


def test_cooldown_blocks_an_immediate_resend(auth_fixture):
    svc, _, _ = auth_fixture
    svc.request_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                     purpose=LoginPurpose.SIGNUP, at=NOW, rng=RNG())
    with pytest.raises(ChallengeRefused):
        svc.request_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                         purpose=LoginPurpose.SIGNUP,
                         at=NOW + timedelta(seconds=30), rng=RNG())


def test_no_provider_refuses_loudly(auth_fixture_null_email):
    svc = auth_fixture_null_email
    with pytest.raises(EmailUnavailableError):
        svc.request_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                         purpose=LoginPurpose.SIGNUP, at=NOW, rng=RNG())


def test_a_failed_send_does_not_consume_the_challenge(auth_fixture_null_email):
    """A vendor outage must never cost someone their login."""
    svc = auth_fixture_null_email
    with pytest.raises(EmailUnavailableError):
        svc.request_code(email="a@b.in", plane=AuthPlane.CANDIDATE,
                         purpose=LoginPurpose.SIGNUP, at=NOW, rng=RNG())
    assert svc._store.get_challenge(
        __import__("app.auth.challenges", fromlist=["ChallengeScope"]).ChallengeScope(
            svc._hash_email("a@b.in"), LoginPurpose.SIGNUP, AuthPlane.CANDIDATE
        )
    ) is None
```

Add the three fixtures to `tests/conftest.py`:

```python
@pytest.fixture
def auth_fixture(tmp_path, settings_capture_email):
    """AuthService wired to CaptureEmail; returns (service, capture_path, verification)."""
    from app.auth.service import build_auth_service
    ...  # build candidates + ledger + verification via make_services, then:
    #     svc = build_auth_service(settings, candidates=..., ledger=..., email=...)
    #     return svc, capture_path, verification
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_auth_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.service'`.

- [ ] **Step 3: Implement `AuthService`**

Required behaviours, each pinned above:

- `_hash_email(email)` = `contact_hash(normalize_email(email), settings.contact_hash_salt)` — **the same salted function that wrote `candidates.email_hash`**, or the claim in §6.2 silently never matches.
- `request_code`: build the `ChallengeScope`; `purge_expired_for_email`; refuse with `ChallengeRefused` if `not may_send(...)`; mint via `challenges.mint_code`; **send the email FIRST, and only persist the challenge if the send succeeded** — a failed send must not consume or supersede anything.
- `verify_code`: `evaluate_verification(...)`; on `WRONG_CODE` call `bump_attempts` then raise; on `OK` delete the challenge, then create the principal (org: `create_organization` + `create_org_user`; candidate: `find_by_email_hash` → claim, else `create_bare_candidate`; admin: look up `admin_user_by_email`, never create), mint the csrf token, `create_session`, and return `(token, csrf, principal)`.
- `resolve_principal(request, *, kind)`: read `request.cookies[settings.session_cookie_name]`; if present and the session resolves `ACTIVE` **and** its principal kind matches, `touch` it and return a `SESSION` principal. Otherwise fall back to the plane's header (`X-API-Key` / `X-Org-Key` / `X-Candidate-Key`) and return a `KEY` principal. Neither → `HTTPException(401)`.
- `resolve_any(request)`: **session only**, any kind. A header key has no session to list or revoke, so it 401s rather than pretending.
- Audit `auth.session.create` / `auth.session.revoke` via `LedgerStore._audit` **only when the subject is a candidate** (the audit table is candidate-scoped); log the org/admin equivalents with structlog.

Then wire `Services`:

```python
# app/services/__init__.py — in the dataclass
    email: EmailClient
    auth: AuthService
```

and build them in `build_default_services` (function-local import, like the others) and in `tests/conftest.py::make_services` (default `email` to `NullEmail(settings)` so the suite proves the refusing path unless a test injects `CaptureEmail`).

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_auth_service.py -q`
Expected: PASS (11 tests).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: green. `Services` gained two required fields, so any construction site that missed them fails here.

- [ ] **Step 6: Commit**

```bash
git add app/auth/service.py app/services/__init__.py tests/conftest.py tests/test_auth_service.py
git commit -m "feat(s82): AuthService -- OTP signup/login, claim-on-signup, resolve_principal

Candidate signup CLAIMS the existing candidate by email_hash rather than
forking a duplicate person: records built from org-uploaded resumes would
otherwise be unreachable by their own subject, making the portal's DPDP rights
theoretical for every candidate in the system. It grants NO identity assurance
-- fusing 'logged in' with 'verified' would repeat S7.2's two-ladders mistake.

The email is sent BEFORE the challenge is persisted, so a provider outage never
consumes or supersedes a login."
```

---

## Task 9: The four resolvers, CSRF, CORS, and the route-table guard

**Files:**
- Modify: `app/api/routes.py:78-125`, `app/main.py`
- Test: `tests/test_auth_resolvers.py`, `tests/test_route_table_guard.py`

**Interfaces:**
- Produces: `require_api_key`, `require_org`, `require_candidate` (rewritten, **same signatures and return types**), `require_any_principal`, `require_csrf`, `PUBLIC_PATHS`.

- [ ] **Step 1: Write the failing tests**

`tests/test_route_table_guard.py`:

```python
from app.api.routes import (
    PUBLIC_PATHS, require_any_principal, require_api_key, require_candidate,
    require_org,
)
from app.main import create_app

RESOLVERS = {require_api_key, require_org, require_candidate, require_any_principal}


def _dependency_callables(route) -> set:
    return {d.call for d in getattr(route, "dependant", None).dependencies} if getattr(
        route, "dependant", None
    ) else set()


def test_every_non_public_route_uses_a_sanctioned_resolver(services):
    """The structural answer to PI-8's highest regression risk. Hand-written
    session twins only cover routes that existed when someone wrote them; this
    fails the moment a NEW route establishes a principal any other way."""
    app = create_app(services)
    unguarded = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if path is None or path in PUBLIC_PATHS:
            continue
        deps = set()
        for d in route.dependant.flat_dependant().dependencies:
            deps.add(d.call)
        deps.add(route.dependant.call)
        if not (deps & RESOLVERS):
            unguarded.append(f"{list(route.methods)} {path}")
    assert unguarded == [], (
        "routes establishing a principal outside the sanctioned resolvers: "
        + ", ".join(unguarded)
    )


def test_public_paths_is_an_explicit_short_list():
    """Widening this list is the reviewable act. If it grows silently, the
    guard above stops meaning anything."""
    assert PUBLIC_PATHS == {
        "/", "/healthz", "/docs", "/redoc", "/openapi.json",
        "/auth/org/signup", "/auth/org/login", "/auth/org/verify",
        "/auth/candidate/signup", "/auth/candidate/login", "/auth/candidate/verify",
        "/auth/admin/login", "/auth/admin/verify",
    }
```

`tests/test_auth_resolvers.py` — the three resolver suites plus the CSRF trap:

```python
def test_candidate_route_accepts_a_session_cookie(client, candidate_session):
    r = client.get("/portal/me", cookies={"dee_session": candidate_session.token})
    assert r.status_code == 200


def test_candidate_route_still_accepts_the_header_key(client, candidate_key):
    r = client.get("/portal/me", headers={"X-Candidate-Key": candidate_key})
    assert r.status_code == 200


def test_a_revoked_session_401s_immediately(client, candidate_session):
    candidate_session.revoke()
    r = client.get("/portal/me", cookies={"dee_session": candidate_session.token})
    assert r.status_code == 401


def test_an_org_session_cannot_authenticate_on_the_candidate_plane(client, org_session):
    """Kind is checked, not merely presence. Otherwise any valid session would
    authenticate on every plane."""
    r = client.get("/portal/me", cookies={"dee_session": org_session.token})
    assert r.status_code == 401


def test_mutating_session_request_without_csrf_is_refused(client, candidate_session):
    r = client.post(
        "/portal/consents",
        cookies={"dee_session": candidate_session.token},
        json={"purpose": "ledger_read"},
    )
    assert r.status_code == 403


def test_mutating_session_request_with_csrf_passes(client, candidate_session):
    r = client.post(
        "/portal/consents",
        cookies={
            "dee_session": candidate_session.token,
            "dee_csrf": candidate_session.csrf,
        },
        headers={"X-CSRF-Token": candidate_session.csrf},
        json={"purpose": "ledger_read"},
    )
    assert r.status_code in (200, 404)   # 404 only if the org id is unknown


def test_a_header_key_needs_no_csrf(client, candidate_key):
    r = client.post(
        "/portal/consents",
        headers={"X-Candidate-Key": candidate_key},
        json={"purpose": "ledger_read"},
    )
    assert r.status_code in (200, 404)


def test_a_session_cookie_plus_a_header_key_is_still_csrf_checked(
    client, candidate_session, candidate_key
):
    """THE TRAP. If the exemption keys on 'a header was present' instead of
    'this request authenticated BY a header', an attacker-supplied X-Candidate-Key
    turns every session request into a CSRF-exempt one."""
    r = client.post(
        "/portal/consents",
        cookies={"dee_session": candidate_session.token},
        headers={"X-Candidate-Key": candidate_key},
        json={"purpose": "ledger_read"},
    )
    assert r.status_code == 403


def test_cors_rejects_an_unlisted_origin(client_with_cors):
    r = client_with_cors.options(
        "/portal/me",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_cors_allows_a_listed_origin(client_with_cors):
    r = client_with_cors.options(
        "/portal/me",
        headers={"Origin": "https://app.example.com",
                 "Access-Control-Request-Method": "GET"},
    )
    assert r.headers["access-control-allow-origin"] == "https://app.example.com"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_route_table_guard.py tests/test_auth_resolvers.py -q`
Expected: FAIL — `ImportError: cannot import name 'require_any_principal'`.

- [ ] **Step 3: Rewrite the resolvers**

Replace `app/api/routes.py:78-114` with:

```python
PUBLIC_PATHS: set[str] = {
    "/", "/healthz", "/docs", "/redoc", "/openapi.json",
    # Login surfaces BY DEFINITION precede a principal. Widening this set is
    # the reviewable act that the route-table guard exists to force.
    "/auth/org/signup", "/auth/org/login", "/auth/org/verify",
    "/auth/candidate/signup", "/auth/candidate/login", "/auth/candidate/verify",
    "/auth/admin/login", "/auth/admin/verify",
}


async def require_api_key(request: Request) -> Principal:
    """Admin-plane gate. Fail-CLOSED since S8.1; session-capable since S8.2.

    Every plane resolves through ONE function so a gate cannot be forgotten at
    a second door -- the bug shape that shipped in S7.1, S7.2 and S7.3.
    """
    return await _services(request).auth.resolve_principal(
        request, kind=PrincipalKind.ADMIN
    )


async def require_org(request: Request) -> str:
    principal = await _services(request).auth.resolve_principal(
        request, kind=PrincipalKind.ORG
    )
    return principal.org_id


async def require_candidate(request: Request) -> str:
    principal = await _services(request).auth.resolve_principal(
        request, kind=PrincipalKind.CANDIDATE
    )
    return principal.candidate_id


async def require_any_principal(request: Request) -> Principal:
    """The session-lifecycle routes are genuinely cross-plane: a candidate, an
    org user and an operator all need to see and revoke their own sessions.
    Without a name for that, those four routes would need three copies each or
    would sit outside the route-table guard -- and a route outside the guard is
    the whole problem. Session ONLY: a header key has no session to list."""
    return _services(request).auth.resolve_any(request)


async def require_csrf(request: Request) -> None:
    """Double-submit check on mutating requests authenticated BY A SESSION.

    The exemption keys on `principal.via`, NEVER on 'a header was present':
    otherwise a browser carrying a session cookie plus an attacker-supplied
    X-Org-Key skips CSRF entirely.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    principal = getattr(request.state, "principal", None)
    if principal is None or principal.via != PrincipalVia.SESSION:
        return
    settings = _services(request).settings
    if not csrf_matches(
        request.cookies.get(settings.csrf_cookie_name),
        request.headers.get("X-CSRF-Token"),
    ):
        raise HTTPException(status_code=403, detail="missing or invalid CSRF token")
```

`resolve_principal` must set `request.state.principal` so `require_csrf` can read it. Add `Depends(require_csrf)` to the `router`, `org_router` and `candidate_router` dependency lists **after** the resolver, so ordering guarantees the principal exists.

- [ ] **Step 4: Add CORS in `app/main.py`**

```python
from fastapi.middleware.cors import CORSMiddleware

# after the routers are included, before the request_context middleware
    origins = (services or build_default_services()).settings.cors_allowed_origins
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_credentials=True,     # the session cookie must ride along
            allow_methods=["*"],
            allow_headers=["*", "X-CSRF-Token"],
        )
```

Read `cors_allowed_origins` from the settings the app is actually built with; **do not** call `build_default_services()` a second time — hoist the settings resolution that already happens for the lifespan.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_route_table_guard.py tests/test_auth_resolvers.py -q`
Expected: PASS.

- [ ] **Step 6: Run the FULL suite — this is the regression gate**

Run: `python -m pytest -q`
Expected: green. Every one of the ~33 files that hand-builds `X-Org-Key`/`X-Candidate-Key` now runs through `resolve_principal`. **A failure here is a real behaviour change, not a test to update** — investigate before touching any assertion.

- [ ] **Step 7: Commit**

```bash
git add app/api/routes.py app/main.py tests/test_route_table_guard.py tests/test_auth_resolvers.py
git commit -m "feat(s82): one resolver per plane + a route-table guard + CORS/CSRF

Sessions add a second entry point to every plane, which is PI-8's highest
regression risk. Rather than ~33 files of hand-written session twins, the three
require_* dependencies become thin wrappers over ONE resolver each, so all 63
endpoints gain session mode with zero handler edits and every existing
authorization test now executes THROUGH the new path.

The guard walks the FastAPI route table and fails for any non-public route that
establishes a principal another way -- so it covers routes not yet written.
That is the metadata-drift-guard pattern applied to authorization.

CSRF exemption keys on principal.via, never on 'a header was present'."
```

---

## Task 10: The auth HTTP surface

**Files:**
- Modify: `app/api/routes.py` (new `auth_router` + admin-user routes), `app/main.py` (include it)
- Test: `tests/test_auth_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_unknown_email_login_still_returns_202(client):
    """No account enumeration. Small, easy to skip, and the only thing standing
    between a stranger and a list of who has an account here."""
    r = client.post("/auth/candidate/login", json={"email": "nobody@nowhere.in"})
    assert r.status_code == 202


def test_signup_with_an_existing_org_email_returns_202_and_sends_nothing(
    client, capture_path, existing_org_user
):
    before = capture_path.read_text(encoding="utf-8") if capture_path.exists() else ""
    r = client.post(
        "/auth/org/signup",
        json={"email": existing_org_user.email, "organization_name": "Duplicate"},
    )
    assert r.status_code == 202
    after = capture_path.read_text(encoding="utf-8") if capture_path.exists() else ""
    assert after == before


def test_verify_sets_both_cookies(client, capture_path):
    client.post("/auth/candidate/signup", json={"email": "a@b.in"})
    r = client.post(
        "/auth/candidate/verify", json={"email": "a@b.in", "code": _code(capture_path)}
    )
    assert r.status_code == 200
    assert "dee_session" in r.cookies
    assert "dee_csrf" in r.cookies


def test_session_cookie_is_httponly_and_csrf_cookie_is_not(client, capture_path):
    client.post("/auth/candidate/signup", json={"email": "a@b.in"})
    r = client.post(
        "/auth/candidate/verify", json={"email": "a@b.in", "code": _code(capture_path)}
    )
    cookies = "; ".join(r.headers.get_list("set-cookie"))
    assert "dee_session=" in cookies and "HttpOnly" in cookies
    session_bit = [c for c in r.headers.get_list("set-cookie") if c.startswith("dee_session")][0]
    csrf_bit = [c for c in r.headers.get_list("set-cookie") if c.startswith("dee_csrf")][0]
    assert "HttpOnly" in session_bit
    assert "HttpOnly" not in csrf_bit   # the UI must be able to read it


def test_no_email_provider_returns_503(client_null_email):
    r = client_null_email.post("/auth/candidate/login", json={"email": "a@b.in"})
    assert r.status_code == 503
    assert r.json()["detail"] == "email_unavailable"


def test_auth_me_reports_the_principal(client, candidate_session):
    r = client.get("/auth/me", cookies={"dee_session": candidate_session.token})
    assert r.json()["kind"] == "candidate"


def test_logout_revokes_the_current_session(client, candidate_session):
    client.post(
        "/auth/logout",
        cookies={"dee_session": candidate_session.token,
                 "dee_csrf": candidate_session.csrf},
        headers={"X-CSRF-Token": candidate_session.csrf},
    )
    assert client.get(
        "/portal/me", cookies={"dee_session": candidate_session.token}
    ).status_code == 401


def test_sessions_list_shows_only_your_own(client, candidate_session, other_candidate_session):
    r = client.get("/auth/sessions", cookies={"dee_session": candidate_session.token})
    ids = {s["id"] for s in r.json()}
    assert candidate_session.id in ids
    assert other_candidate_session.id not in ids


def test_revoking_someone_elses_session_is_an_indistinguishable_404(
    client, candidate_session, other_candidate_session
):
    r = client.post(
        f"/auth/sessions/{other_candidate_session.id}/revoke",
        cookies={"dee_session": candidate_session.token,
                 "dee_csrf": candidate_session.csrf},
        headers={"X-CSRF-Token": candidate_session.csrf},
    )
    assert r.status_code == 404


def test_a_key_authenticated_caller_cannot_use_the_session_routes(client, candidate_key):
    r = client.get("/auth/sessions", headers={"X-Candidate-Key": candidate_key})
    assert r.status_code == 401


def test_admin_user_creation_requires_the_shared_key(client, admin_headers):
    assert client.post("/admin/users", json={"email": "op@veritas.in"}).status_code == 401
    r = client.post("/admin/users", json={"email": "op@veritas.in"}, headers=admin_headers)
    assert r.status_code == 200


def test_there_is_no_admin_signup(client):
    assert client.post(
        "/auth/admin/signup", json={"email": "attacker@evil.in"}
    ).status_code == 404
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_auth_api.py -q`
Expected: FAIL — 404 on every `/auth/*` route.

- [ ] **Step 3: Implement the routes**

Add a dependency-free `auth_router = APIRouter()` beside the existing routers, with request models (`OrgSignupRequest{email, organization_name}`, `EmailOnlyRequest{email}`, `VerifyRequest{email, code}`) and these handlers:

| Route | Behaviour |
|---|---|
| `POST /auth/org/signup` | `202` always; `503 email_unavailable` when `NullEmail` |
| `POST /auth/org/login` | `202` always |
| `POST /auth/org/verify` | `200` + both cookies, or `400 invalid_code` |
| `POST /auth/candidate/{signup,login,verify}` | same shapes |
| `POST /auth/admin/{login,verify}` | same shapes; **no signup route** |
| `GET /auth/me` | `Depends(require_any_principal)` |
| `POST /auth/logout` | `Depends(require_any_principal)` |
| `GET /auth/sessions` | `Depends(require_any_principal)` |
| `POST /auth/sessions/{id}/revoke` | `Depends(require_any_principal)`, 404 when not owned |
| `POST /admin/users`, `GET /admin/users`, `DELETE /admin/users/{id}` | on `router` (shared admin key or operator session) |

Cookie setting is one shared helper so the flags cannot drift between planes:

```python
def _set_session_cookies(response: Response, *, token: str, csrf: str, settings) -> None:
    common = dict(
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_minutes * 60,
        path="/",
    )
    response.set_cookie(settings.session_cookie_name, token, httponly=True, **common)
    # NOT httponly: the UI must read this to echo it in X-CSRF-Token.
    response.set_cookie(settings.csrf_cookie_name, csrf, httponly=False, **common)
```

`ChallengeRefused` maps to `400 invalid_code` **with no detail about which failure it was** — "expired" vs "wrong" vs "exhausted" is an oracle. `EmailUnavailableError` maps to `503 email_unavailable`.

Register in `app/main.py`: `app.include_router(auth_router)` and add the new paths to the `/` endpoint listing.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_auth_api.py -q`
Expected: PASS (12 tests).

- [ ] **Step 5: Run the route-table guard again**

Run: `python -m pytest tests/test_route_table_guard.py -q`
Expected: PASS — the new routes are either in `PUBLIC_PATHS` or behind a resolver.

- [ ] **Step 6: Commit**

```bash
git add app/api/routes.py app/main.py tests/test_auth_api.py
git commit -m "feat(s82): the auth HTTP surface -- OTP signup/login/verify + sessions

202 on signup and login regardless of whether the email is known, and signup on
a taken address sends nothing rather than silently mailing a login code: an
enumeration oracle and a confused-deputy flow respectively. ChallengeRefused
maps to a single 400 invalid_code, because distinguishing expired from wrong
from exhausted is itself an oracle.

Cookies are set through one helper so the flags cannot drift between planes.
There is no admin signup: operators are created by an existing operator."
```

---

## Task 11: Portal integration — sessions in `MyData`, challenges in erasure

**Files:**
- Modify: `app/portal/schema.py`, `app/portal/service.py`, `app/api/routes.py` (the `portal_erase` handler)
- Test: `tests/test_portal_sessions.py`

- [ ] **Step 1: Write the failing test**

```python
def test_my_data_lists_the_candidates_sessions(portal, candidate_with_session):
    cid, session_id = candidate_with_session
    data = portal.my_data(cid)
    assert [s.id for s in data.sessions] == [session_id]


def test_my_data_sessions_carry_no_token(portal, candidate_with_session):
    cid, _ = candidate_with_session
    dumped = portal.my_data(cid).model_dump_json()
    assert "token" not in dumped


def test_erasure_kills_every_session(client, candidate_session):
    client.delete("/portal/me",
                  cookies={"dee_session": candidate_session.token,
                           "dee_csrf": candidate_session.csrf},
                  headers={"X-CSRF-Token": candidate_session.csrf})
    assert client.get(
        "/portal/me", cookies={"dee_session": candidate_session.token}
    ).status_code == 401


def test_erasure_deletes_outstanding_login_challenges(client, auth_service, candidate_session):
    """login_challenges has NO FK, so nothing cascades. Without an explicit
    delete, a challenge keyed by an erased person's email_hash outlives them --
    the one guarantee in this sprint that is not structural, so it gets a test."""
    from app.auth.challenges import ChallengeScope
    from app.auth.schema import AuthPlane, LoginPurpose

    email = candidate_session.email
    auth_service.request_code(email=email, plane=AuthPlane.CANDIDATE,
                              purpose=LoginPurpose.LOGIN, at=NOW, rng=random.Random(1))
    client.delete("/portal/me",
                  cookies={"dee_session": candidate_session.token,
                           "dee_csrf": candidate_session.csrf},
                  headers={"X-CSRF-Token": candidate_session.csrf})
    scope = ChallengeScope(
        auth_service._hash_email(email), LoginPurpose.LOGIN, AuthPlane.CANDIDATE
    )
    assert auth_service._store.get_challenge(scope) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_portal_sessions.py -q`
Expected: FAIL — `MyData` has no `sessions` field.

- [ ] **Step 3: Implement**

In `app/portal/schema.py`, add to `MyData` (after `interviews`):

```python
    # S8.2 active sessions, so a candidate can see and revoke their own devices.
    # A transparency right, consistent with the access log. Never the token.
    sessions: list[SessionView] = Field(default_factory=list)
```

`PortalService` takes the `AuthStore` (or `AuthService`) and populates it. In `portal_erase`, before `delete_candidate`, look up the candidate's `email_hash` and call `auth.delete_challenges_for_email(email_hash)` — sessions themselves need nothing, they CASCADE.

Put the challenge deletion **inside the erasure path, not in the route handler**: the admin plane's `DELETE /candidates/{id}` erases too, and a rule applied at one entry point and not the other is the bug this sprint keeps citing. Add it to `CandidateStore.delete_candidate`'s caller in the service layer, and cover **both** routes with a test.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_portal_sessions.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/portal/schema.py app/portal/service.py app/api/routes.py tests/test_portal_sessions.py
git commit -m "feat(s82): MyData.sessions + erasure deletes login challenges

Sessions cascade with the candidate, but login_challenges has no FK by design
(at signup time no principal exists), so an outstanding challenge would outlive
an erased person. That deletion lives in the erasure path, not the route
handler -- both the portal and the admin plane erase, and a rule applied at one
entry point and not the other is this repo's recurring defect."
```

---

## Task 12: The six twins, the smoke, and `AUTH.md`

**Files:**
- Create: `scripts/smoke_s82.py`, `AUTH.md`
- Test: `tests/test_auth_session_twins.py`

- [ ] **Step 1: Write the six twins**

These are the cases where authorization means something beyond identity resolution, so the resolver suites do not reach them:

```python
def test_twin_cross_candidate_isolation_by_session(client, candidate_session, other_candidate):
    """Candidate B's SESSION cannot see candidate A -- 404, indistinguishable
    from 'no such thing'."""


def test_twin_consent_gated_org_read_by_session(client, org_session, candidate_id):
    """An org SESSION is refused a consent-gated read exactly as an org KEY is,
    and the denial is audited identically."""


def test_twin_revoked_session_is_refused_on_a_consent_gated_route(client, org_session):
    ...


def test_twin_erased_candidates_session_dies_with_them(client, candidate_session):
    ...


def test_twin_absolutely_expired_session_is_refused(client, candidate_session, frozen_clock):
    ...


def test_twin_idle_timed_out_session_is_refused(client, candidate_session, frozen_clock):
    ...
```

Every one of these injects the clock on **every** mutation, not just setup — the pinned-NOW time bomb from S8.1.

- [ ] **Step 2: Run them and confirm they fail before the behaviour exists, then pass**

Run: `python -m pytest tests/test_auth_session_twins.py -q`
Expected: PASS after Tasks 9–11.

- [ ] **Step 3: Write `scripts/smoke_s82.py`**

Model it on `scripts/smoke_s81.py`. Boot uvicorn with `DEE_API_AUTH_KEY` set (the app refuses to boot without it), `DEE_OPENROUTER_API_KEY=""`, `email_provider=capture`, `session_cookie_secure=false`, `session_cookie_samesite=lax`, and a temp `email_capture_path`. 18 checks, exit 0:

1. org signup → `202`
2. code read from the capture file
3. verify → `200`, both cookies set
4. an org call succeeds with **no `X-Org-Key` at all**
5. the same call with the cookie but **no CSRF token** → `403`
6. with the CSRF token → `200`
7. an org resume upload creates a candidate
8. candidate signs up with **that resume's email** → `202`
9. verify → `200`
10. `/portal/me` shows the resume the org uploaded (**the claim, proven end to end**)
11. `/auth/sessions` lists exactly one
12. a second candidate login from a different user-agent → two sessions
13. revoke the first → it `401`s
14. the second still works
15. admin mints an operator with `X-API-Key` → `200`
16. operator logs in by OTP → admin call succeeds **by session**
17. `DELETE /portal/me` → every candidate session `401`s
18. `POST /auth/candidate/login` for an unknown email → still `202`

- [ ] **Step 4: Run the smoke**

Run: `python scripts/smoke_s82.py`
Expected: `18/18 OK`, exit 0.

- [ ] **Step 5: Run the regression smokes**

Run: `python scripts/smoke_s13.py && python scripts/smoke_s41.py && python scripts/smoke_s53.py && python scripts/smoke_s64.py && python scripts/smoke_s73.py && python scripts/smoke_s81.py`
Expected: all exit 0. **These will need `DEE_API_AUTH_KEY` in their environment** — if any of them broke, it is because the resolver rewrite changed a real behaviour, so fix the code, not the smoke.

- [ ] **Step 6: Write `AUTH.md`**

Peer of `LEDGER.md` / `PORTAL.md` / `VERIFICATION.md` / `INTERVIEWS.md`. Cover: the two auth modes and why both are permanent; the four tables and the exclusive arc; the resolver + route-table guard (and how to add a route without breaking it); the CSRF exemption rule; the claim-on-signup decision and its trust boundary; the email seam and the three providers; **and the standing gap — no rate limiting until S8.3.**

- [ ] **Step 7: Full suite + commit**

Run: `python -m pytest -q`
Expected: green.

```bash
git add tests/test_auth_session_twins.py scripts/smoke_s82.py AUTH.md
git commit -m "test(s82): six session twins, smoke_s82 18/18, AUTH.md

The twins cover what the resolver suites cannot reach -- cross-candidate
isolation, consent-gated org reads, revocation, erasure, absolute expiry and
idle timeout -- each with the clock injected on every mutation, not just setup
(the S8.1 time bomb).

The smoke proves the claim end to end: an org uploads a resume, the candidate
signs up with that resume's email, and /portal/me shows them the record built
about them by someone else."
```

---

## Self-Review

**Spec coverage.** Every section maps to a task: §0.1/0.2 → the plan's ordering and the absence of any 501 task · §0.3 `admin_users` → Tasks 6, 7, 10 · §0.4 claim → Task 8 · §0.5 resolver/guard → Task 9 · §0.6 no rate limiting → absent by design, documented in Task 12's `AUTH.md` step · §2 → Task 9 · §3 tables → Task 6 · §4 cookies/CSRF/boot refusals → Tasks 1, 9, 10 · §5 OTP → Task 5 · §6 flows → Tasks 8, 10 · §7 CORS → Tasks 1, 9 · §8 DPDP + §8.1 erasure hole → Task 11 · §9 config → Task 1 · §10 email → Task 2 · §11 testing + smoke → Tasks 9, 12 · §13 definition of done → Tasks 9 (item 4, 5), 11 (item 6), 12 (items 1–3, 8).

**Two gaps found and closed while reviewing:**

1. **`require_api_key` changed return type** from `None` to `Principal`. It is used as a *router-level* dependency (`APIRouter(dependencies=[...])`), where the return value is discarded — so this is safe, but Task 9 must not miss that `Depends(require_csrf)` has to be ordered **after** it in the same list, or `request.state.principal` will not exist yet. Called out inline in Task 9 Step 3.
2. **Erasure had two entry points** (portal and admin) and the first draft put the challenge deletion in the portal handler only — reproducing the exact defect this sprint keeps citing. Task 11 Step 3 now puts it in the erasure path and requires both routes to be covered.

**Type consistency:** `Principal`, `PrincipalKind`, `PrincipalVia`, `AuthPlane`, `LoginPurpose`, `SessionStatus`, `SessionView`, `ChallengeScope`, `VerifyOutcome` are defined in Tasks 3 and 5 and used with those exact names in Tasks 6–12. `resolve_principal(request, *, kind)` and `resolve_any(request)` are consistent between Tasks 8 and 9. Cookie names come from settings in every task, never hardcoded outside tests.
