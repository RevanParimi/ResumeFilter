"""A FIXED sign-in code for local testing, and the three guards that keep it there.

This is a deliberate auth backdoor: with it set, one known six-digit string signs
in as any account on any plane. That is exactly what makes it useful for driving
the UI, and exactly why it is shaped like `login_otp_debug_echo` rather than like
an ordinary setting -- honored only under `env=local`, refused at BOOT in prod,
and empty in the shipped config.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.core.boot import LaunchConfigError, verify_launch_config
from app.core.config import Settings


def _cfg(settings, **over) -> Settings:
    return settings.model_copy(update=over)


# ── the knob itself ───────────────────────────────────────────────────────────
def test_the_static_code_is_empty_by_default(settings):
    """Off unless someone turns it on. A backdoor that ships armed is not a
    testing affordance, it is a vulnerability with a docstring."""
    assert settings.login_otp_static_code == ""


def test_a_malformed_static_code_is_refused_at_construction(settings):
    """Digits only, and exactly login_otp_length of them. A code that can never
    match is worse than none: the developer sees 'invalid code' and goes looking
    at the auth flow rather than at their own config."""
    for bad in ("12345", "1234567", "abcdef", "12 34 56", "12-345"):
        with pytest.raises(ValidationError):
            Settings(login_otp_static_code=bad)


def test_a_well_formed_static_code_is_accepted(settings):
    assert Settings(login_otp_static_code="000000").login_otp_static_code == "000000"


# ── guard 1: it only applies under env=local ──────────────────────────────────
def test_the_static_code_is_used_when_env_is_local(settings):
    from app.auth import challenges as challenge_logic

    cfg = _cfg(settings, env="local", login_otp_static_code="424242")
    code, _digest = challenge_logic.mint_code_for(cfg)
    assert code == "424242"


def test_the_static_code_is_ignored_outside_local(settings):
    """Defence in depth. Even if the boot refusal is somehow bypassed, a
    non-local process must mint a real random code."""
    from app.auth import challenges as challenge_logic

    cfg = _cfg(settings, env="staging", login_otp_static_code="424242")
    code, _digest = challenge_logic.mint_code_for(cfg)
    assert code != "424242"
    assert len(code) == cfg.login_otp_length and code.isdigit()


def test_an_unset_static_code_still_mints_randomly_in_local(settings):
    from app.auth import challenges as challenge_logic

    cfg = _cfg(settings, env="local", login_otp_static_code="")
    seen = {challenge_logic.mint_code_for(cfg)[0] for _ in range(20)}
    assert len(seen) > 1, "an empty static code must not freeze the generator"


def test_the_digest_matches_the_static_code(settings):
    """The digest is what verification compares against, so a static code whose
    digest was computed from something else would mint a code that cannot log
    in -- the failure mode this whole feature exists to remove."""
    from app.auth import challenges as challenge_logic
    from app.verification import otp as otp_logic

    cfg = _cfg(settings, env="local", login_otp_static_code="424242")
    code, digest = challenge_logic.mint_code_for(cfg)
    assert digest == otp_logic.hash_code(code, cfg.contact_hash_salt)


# ── guard 2: prod refuses to BOOT ─────────────────────────────────────────────
def test_prod_refuses_to_boot_with_a_static_code(settings):
    cfg = _cfg(
        settings,
        env="prod",
        login_otp_static_code="424242",
        api_auth_key=SecretStr("k"),
        candidates_db_url="postgresql+psycopg://u:p@h/db",
        session_cookie_secure=True,
        email_provider="smtp",
        email_smtp_host="smtp.example.com",
        grievance_officer_email="dpo@example.com",
    )
    with pytest.raises(LaunchConfigError) as exc:
        verify_launch_config(cfg)
    assert "login_otp_static_code" in str(exc.value).lower()


def test_local_boots_fine_with_a_static_code(settings):
    """The refusal is about prod, not about the knob existing."""
    verify_launch_config(_cfg(settings, env="local", login_otp_static_code="424242"))


# ── guard 3: it is not armed in the shipped config ────────────────────────────
def test_the_shipped_config_does_not_arm_it():
    """config.yaml is what a deployment actually reads. Documented there, never
    set there -- the same posture as login_otp_debug_echo."""
    import pathlib

    import yaml

    root = pathlib.Path(__file__).resolve().parent.parent
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8")) or {}
    assert not cfg.get("login_otp_static_code"), (
        "config.yaml must not ship an armed static sign-in code"
    )


def test_the_static_code_has_exactly_one_production_door():
    """One mint path for login codes, pinned.

    This repo's signature defect is a rule applied at one entry point and not
    the other -- it has appeared in every PI review. Here the rule is
    `env == "local"`, and a second mint site that called the raw `mint_code`
    would silently ignore it, producing a login door the static code does not
    open (confusing) or, if the check were inverted, one that ignores env
    (dangerous).

    `mint_code` itself stays public: it is the pure primitive, used by the
    verification-OTP path and by tests. What must stay singular is the number
    of PRODUCTION callers minting a LOGIN code.
    """
    import pathlib
    import re

    src_root = pathlib.Path(__file__).resolve().parent.parent / "src" / "app"
    raw, wrapped = [], []
    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("def "):
                continue  # the definition is not a call site
            if re.search(r"\bmint_code_for\s*\(", line):
                wrapped.append(f"{path.name}:{i}")
            elif re.search(r"\bmint_code\s*\(", line):
                raw.append(f"{path.name}:{i}")

    assert len(wrapped) == 1, f"expected ONE login mint door, found {wrapped}"
    assert raw == [], (
        f"a production call to the raw mint_code bypasses the env=local guard: {raw}"
    )
