"""A runbook that names a variable the code does not read -- or omits one it
requires -- is the GET / endpoints defect wearing a different hat (S8.6 §7.1).

Both directions, for the same reason tests/test_retention_plan.py asserts set
equality both ways: a one-directional check lets the drift happen in the
direction nobody is watching.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "DEPLOY.md"

#: Settings the ten boot refusals read. If a refusal starts reading a new
#: one, DEPLOY.md must name it -- otherwise the checklist cannot satisfy it.
REFUSAL_SETTINGS = {
    "api_auth_key",
    "candidates_db_url",
    "session_cookie_secure",
    "cors_allowed_origins",
    "email_provider",
    "rate_limit_enabled",
    "grievance_officer_email",
    "email_smtp_host",
    "login_otp_debug_echo",
    "login_otp_static_code",
}


def _named_vars() -> set[str]:
    return set(re.findall(r"\bDEE_([A-Z0-9_]+)\b", DOC.read_text(encoding="utf-8")))


def test_every_variable_named_is_a_real_setting():
    fields = {f.upper() for f in Settings.model_fields}
    unknown = _named_vars() - fields
    assert unknown == set(), (
        f"DEPLOY.md names {sorted(unknown)}, which no Settings field reads. "
        "An operator would set them and nothing would happen."
    )


def test_every_setting_a_refusal_reads_is_documented():
    named = {v.lower() for v in _named_vars()}
    missing = REFUSAL_SETTINGS - named
    assert missing == set(), (
        f"the boot refusals read {sorted(missing)} but DEPLOY.md never names "
        "them, so following the checklist cannot produce a bootable config"
    )


def test_the_refusal_list_here_matches_the_code():
    """REFUSAL_SETTINGS is itself a hand-maintained list, and this file's whole
    argument is that those drift.

    Derived from the source of app/core/boot.py: every `settings.<field>` it
    reads. Without this, a ninth refusal reading a ninth variable would leave
    both tests above passing while the checklist silently stopped being
    sufficient -- which is the exact failure they exist to prevent.
    """
    source = (ROOT / "src" / "app" / "core" / "boot.py").read_text(encoding="utf-8")
    read = {
        m for m in re.findall(r"settings\.([a-z_][a-z0-9_]*)", source)
        if m in Settings.model_fields
    } - {"env"}  # env selects WHICH refusals run; it is not one of their knobs
    assert read == REFUSAL_SETTINGS, (
        f"boot.py reads {sorted(read)}; this file lists {sorted(REFUSAL_SETTINGS)}"
    )


def test_the_checklist_names_the_retention_cron():
    text = DOC.read_text(encoding="utf-8")
    assert "app.retention.sweep" in text and "--apply" in text, (
        "the sweep has no scheduler; without the cron the portal promises a "
        "purge nobody invokes"
    )


def test_the_checklist_names_the_ibm_check():
    """It has no better home, and it is materially worse retrofitted after a
    customer signs (GTM section 8.3)."""
    assert "IBM" in DOC.read_text(encoding="utf-8")


def test_every_ui_path_the_runbook_names_actually_loads(services):
    """A runbook that sends an operator to a 404 is the same defect as one
    naming a variable the code does not read -- this file's own premise, one
    column over.

    FOUND BY HAND, AFTER FOUR REVIEW PASSES MISSED IT. Step 7 said "Sign up
    through the UI at `/ui`", and `/ui` redirected to `/ui/` which answered
    404. Nothing caught it because every check on that mount fetched an ASSET:
    the smoke, tests/test_ui_mount.py's access test and the CI image job all
    asked for `api.js`. Proving a JavaScript file is reachable is not proving
    the UI loads.

    The paths are READ OUT OF THE DOC rather than hardcoded, so rewording step
    7 to name a different URL moves this test with it instead of leaving it
    pinned to a string the runbook no longer contains.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    paths = sorted(set(re.findall(r"`(/ui[^`\s]*)`", DOC.read_text(encoding="utf-8"))))
    assert paths, "DEPLOY.md names no /ui path -- this guard would pass vacuously"

    client = TestClient(create_app(services))
    for path in paths:
        resp = client.get(path)
        assert resp.status_code == 200, (
            f"DEPLOY.md tells the operator to open {path}, which answers "
            f"{resp.status_code}"
        )
