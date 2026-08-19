"""The one smoke harness. Import it; do not copy it.

WHY THIS FILE EXISTS. Every smoke grew its own copy of the same four helpers.
Counted at the S8.6 review: 8 scripts declared `CHECKS` + `check()`, 21 wrote
`_wait_healthy`, 33 built an `httpx.Client` by hand, and 34 files across
`scripts/` and `tests/` transcribed the key-less environment dict.

The cost was never the duplicated lines. `DEE_OPENROUTER_API_KEY: ""` went
MISSING from five smokes and was retrofitted one sprint at a time -- a smoke
whose stated claim was "the no-key path works" quietly shipping a developer's
real key to a live vendor. An invariant that lives in 34 places is an
invariant nothing can test. Here it lives once, and
`tests/test_smoke_harness.py` tests it.

HOW THE IMPORT WORKS, because it looks odd. Smokes run as plain files
(`python scripts/smoke_s86.py`), so `sys.path[0]` is `scripts/` and this
module is `_smoke`. Tests run from the repo root, where the same file is
`scripts._smoke`. Both work, and nothing here holds module-level mutable
state -- the check list belongs to a `Smoke` INSTANCE -- so the two names
cannot drift into two half-filled tallies.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

import httpx


class Smoke:
    """A named tally of checks, printed as it goes and summarised at the end."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.checks: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        """Record one check, print it, and RETURN the verdict.

        The copies returned None, so a smoke could not branch on a result
        without evaluating the condition twice.
        """
        ok = bool(ok)
        self.checks.append((name, ok, detail))
        print(f"{'OK  ' if ok else 'FAIL'} {name}{(' -- ' + detail) if detail else ''}")
        return ok

    def summary(self) -> int:
        """Print the tally; return the process exit code.

        AN EMPTY RUN IS A FAILURE. Every hand-rolled copy returned 0 here, so a
        smoke that crashed before its first check -- or whose checks were all
        skipped by an early `return` -- reported success. The S8.6 review found
        a check that "passed for the wrong reason"; this is that same failure
        with nothing left to pass for.
        """
        if not self.checks:
            print(f"\n0/0 -- no checks ran, which is a FAILURE, not a pass ({self.name})")
            return 1
        failed = [n for n, ok, _ in self.checks if not ok]
        print(f"\n{len(self.checks) - len(failed)}/{len(self.checks)} OK")
        if failed:
            print("FAILED: " + ", ".join(failed))
        return 1 if failed else 0


def base_env(scratch: Optional[Path] = None, url: Optional[str] = None,
             **overrides: str) -> dict:
    """The environment every smoke starts from, with the two standing pins.

    `DEE_OPENROUTER_API_KEY` is pinned EMPTY because a smoke's whole claim is
    that the offline path works, and a developer with a real key in `.env`
    would otherwise bill a live vendor from a test run (S7.3, five sprints
    running). `DEE_VECTORSTORE_BACKEND` is `memory` because Chroma's
    PersistentClient can hang on init and a smoke has to stay bounded.

    `overrides` are applied LAST and may override either -- deliberately: the
    refusal smokes set the key precisely to prove the boot guard fires. What
    the pins prevent is a smoke inheriting a real key by saying nothing.

    BOTH ARGUMENTS ARE OPTIONAL so that the older smokes, which each built the
    dict inline and then called `env.update({...})` with their own settings,
    migrate by swapping ONE call: `os.environ.copy()` -> `base_env()`. Their
    own update still runs afterwards and still wins, so behaviour is unchanged
    for every value they set -- and the two pins now hold for the ones they
    forgot, which is the entire point.
    """
    env = os.environ.copy()
    env.update({
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_OPENROUTER_API_KEY": "",
    })
    if url is not None:
        env["DEE_CANDIDATES_DB_URL"] = url
    if scratch is not None:
        env["DEE_FLYWHEEL_PATH"] = (Path(scratch) / "flywheel.jsonl").as_posix()
    env.update(overrides)
    return env


def wait_healthy(client, tries: int = 60, delay: float = 0.5) -> bool:
    """Poll /healthz until it answers 200, or give up after `tries`."""
    for _ in range(tries):
        try:
            if client.get("/healthz").status_code == 200:
                return True
        except httpx.TransportError:
            pass
        time.sleep(delay)
    return False


def client(base: str, timeout: float = 180, connect: float = 5, **kw) -> httpx.Client:
    """An httpx client with the timeouts every smoke had been retyping.

    Generous read timeout because a first LLM-less evaluation still walks the
    whole graph; short connect timeout because a server that is not there
    should fail fast rather than eat the read budget.

    `kw` passes through to httpx -- `headers=` above all, which is how a smoke
    carries its admin key on every request.
    """
    return httpx.Client(
        base_url=base, timeout=httpx.Timeout(timeout, connect=connect), **kw
    )


def uvicorn_argv(port: int, host: str = "127.0.0.1",
                  target: str = "app.main:app") -> list[str]:
    """The uvicorn command line, written once.

    `sys.executable` rather than a bare `uvicorn`, so a smoke runs against the
    interpreter it was launched with instead of whatever is first on PATH.
    """
    return [sys.executable, "-m", "uvicorn", target, "--host", host, "--port", str(port)]


def boot_until_exit(
    argv: Sequence[str], env: dict, timeout: float = 90.0, cwd: Optional[Path] = None
) -> tuple[int, str]:
    """Start a process, wait for it to DIE, return (exit code, combined output).

    The shape every boot-refusal check needs: the refusal is only real if the
    operator sees it as a non-zero exit, not as a log line under a server that
    kept serving.

    A process still alive at `timeout` is killed and reported as -1 -- a value
    no real exit status produces on either platform -- so a HANG can never be
    read as a clean refusal. That distinction is not theoretical: S8.6 found a
    check passing because the harness killed a process hanging on a dead
    Postgres, and `code != 0` was true for the wrong reason.
    """
    proc = subprocess.Popen(
        list(argv), env=env, cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        out = proc.communicate(timeout=timeout)[0]
    except subprocess.TimeoutExpired:
        proc.kill()
        out = proc.communicate()[0]
        return -1, out
    return proc.returncode, out
