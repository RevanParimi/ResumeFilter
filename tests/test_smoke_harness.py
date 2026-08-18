"""The smoke harness is SHARED, and this is what keeps it that way.

Every smoke re-implemented the same four helpers. Measured at the S8.6 review:
8 scripts declared their own `CHECKS`/`check()`, 21 their own `_wait_healthy`,
33 built their own `httpx.Client`, and 34 files hand-copied the key-less
environment dict.

That last number is the one that matters. `DEE_OPENROUTER_API_KEY: ""` was
MISSING from five smokes and had to be retrofitted sprint by sprint -- a smoke
claiming to prove the no-key path while shipping a developer's real key to a
live vendor. An invariant living in 34 copies is an invariant nothing can
test. Here it has one home and a test.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts._smoke import Smoke, base_env, boot_until_exit, wait_healthy

ROOT = Path(__file__).resolve().parents[1]


class _FakeClient:
    """Answers /healthz on the Nth try; raises the transport error before."""

    def __init__(self, ok_on: int, exc=None):
        self.ok_on, self.calls, self.exc = ok_on, 0, exc

    def get(self, path):
        self.calls += 1
        if self.calls < self.ok_on:
            raise (self.exc or __import__("httpx").TransportError("refused"))
        return type("R", (), {"status_code": 200})()


def test_check_records_and_returns_the_verdict(capsys):
    s = Smoke("demo")
    assert s.check("a", True) is True
    assert s.check("b", False, "why") is False
    out = capsys.readouterr().out
    assert "OK   a" in out
    assert "FAIL b -- why" in out


def test_summary_is_the_exit_code(capsys):
    s = Smoke("demo")
    s.check("a", True)
    assert s.summary() == 0
    assert "1/1 OK" in capsys.readouterr().out

    s.check("b", False)
    assert s.summary() == 1
    assert "FAILED: b" in capsys.readouterr().out


def test_an_empty_smoke_is_a_FAILURE_not_a_pass(capsys):
    """A harness that ran nothing must not report success. The S8.6 review
    found a check that 'passed for the wrong reason'; zero checks is that
    failure mode taken to its limit, and every hand-rolled copy returned 0."""
    assert Smoke("demo").summary() == 1
    assert "no checks ran" in capsys.readouterr().out.lower()


def test_base_env_pins_the_api_key_empty(tmp_path):
    """THE invariant. Five smokes shipped without it."""
    env = base_env(tmp_path, "sqlite:///x.db")
    assert env["DEE_OPENROUTER_API_KEY"] == ""


def test_base_env_keeps_chroma_out_of_the_smokes(tmp_path):
    """PersistentClient hangs on the maintainer's machine; every smoke has
    always had to say so, 34 times."""
    assert base_env(tmp_path, "sqlite:///x.db")["DEE_VECTORSTORE_BACKEND"] == "memory"


def test_base_env_scopes_the_database_and_flywheel_to_the_scratch(tmp_path):
    env = base_env(tmp_path, "sqlite:///scoped.db")
    assert env["DEE_CANDIDATES_DB_URL"] == "sqlite:///scoped.db"
    # posix form, as the original _base_env wrote it: uvicorn is handed this
    # as a string and Windows backslashes are not safe to round-trip through it
    assert env["DEE_FLYWHEEL_PATH"] == (tmp_path / "flywheel.jsonl").as_posix()


def test_base_env_takes_no_arguments_at_all(tmp_path):
    """How the 33 older smokes migrate: they each built the dict inline and
    then called env.update({...}) with their own settings, so the swap is one
    call and their update still wins. The pins hold for what they forgot."""
    env = base_env()
    assert env["DEE_OPENROUTER_API_KEY"] == ""
    assert env["DEE_VECTORSTORE_BACKEND"] == "memory"
    assert "DEE_FLYWHEEL_PATH" not in env or "flywheel.jsonl" not in env["DEE_FLYWHEEL_PATH"]


def test_base_env_overrides_win_but_the_key_pin_is_not_accidental(tmp_path):
    """Overrides are how a smoke asks for its own posture -- s86 needs prod
    values -- so they must apply. Including, deliberately, to the key: the
    refusal smokes set it to prove the boot guard."""
    env = base_env(tmp_path, "sqlite:///x.db", DEE_ENV="staging", DEE_OPENROUTER_API_KEY="k")
    assert env["DEE_ENV"] == "staging"
    assert env["DEE_OPENROUTER_API_KEY"] == "k"


def test_base_env_does_not_leak_a_real_key_from_the_ambient_environment(tmp_path, monkeypatch):
    """The exact S7.3 incident: a developer with a real key in .env."""
    monkeypatch.setenv("DEE_OPENROUTER_API_KEY", "sk-real-key")
    assert base_env(tmp_path, "sqlite:///x.db")["DEE_OPENROUTER_API_KEY"] == ""


def test_wait_healthy_retries_through_transport_errors():
    c = _FakeClient(ok_on=3)
    assert wait_healthy(c, tries=10, delay=0) is True
    assert c.calls == 3


def test_wait_healthy_gives_up_and_says_so():
    c = _FakeClient(ok_on=999)
    assert wait_healthy(c, tries=4, delay=0) is False
    assert c.calls == 4


def test_boot_until_exit_returns_the_code_and_the_output():
    code, out = boot_until_exit(
        [sys.executable, "-c", "import sys; print('bye'); sys.exit(3)"], {}, timeout=60
    )
    assert code == 3
    assert "bye" in out


def test_boot_until_exit_reports_a_process_that_REFUSES_to_die():
    """A server that stays up is the guard NOT firing. The hand-rolled copies
    returned False here; this returns a code no exit status can collide with,
    so a caller cannot mistake a hang for a clean refusal."""
    code, _ = boot_until_exit(
        [sys.executable, "-c", "import time; time.sleep(30)"], {}, timeout=2
    )
    assert code == -1


SMOKES = sorted(p for p in (ROOT / "scripts").glob("*.py") if p.name != "_smoke.py")


@pytest.mark.parametrize("path", SMOKES, ids=lambda p: p.name)
def test_no_script_hand_rolls_the_shared_harness(path):
    """The drift guard. Every helper below existed in 8-34 copies before the
    S8.6 review; without this test the 35th copy lands in the next sprint and
    nobody notices, which is exactly how the key pin went missing five times.
    """
    src = path.read_text(encoding="utf-8")
    # `os.environ.copy()` rather than a function NAME: a smoke composing its
    # own posture on top of base_env (smoke_s86 needs prod values) is reuse,
    # not duplication. What must not come back is a second place that decides
    # what a smoke environment starts as -- that is where the key pin went
    # missing five times.
    for banned in ("def _wait_healthy", "def check(", "os.environ.copy()"):
        assert banned not in src, (
            f"{path.name} re-implements `{banned}`. It lives in scripts/_smoke.py "
            "-- import it instead of copying it."
        )


def test_the_drift_guard_is_not_vacuous():
    """It must be looking at real files: a glob that went empty would pass."""
    assert len(SMOKES) >= 30


def test_client_passes_headers_through():
    """A smoke carries its admin key on every request; a helper that dropped
    `headers=` would 401 the whole run."""
    from scripts._smoke import client
    with client("http://127.0.0.1:1", headers={"X-API-Key": "k"}) as c:
        assert c.headers["X-API-Key"] == "k"
        assert c.timeout.connect == 5
