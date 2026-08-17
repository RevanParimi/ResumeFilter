"""The cron calls this CLI, so its output contract is load-bearing (S8.6 §4).

The last-line rule was FOUND BY A TEST, not designed: the process shares stdout
with the structured log, so the stream is a SEQUENCE of JSON documents and
json.loads of the whole buffer raises "Extra data". jq is unaffected; a caller
doing json.loads(output) is not. Pinned here because a cron is exactly such a
caller, and it would fail in production at 3am with nobody reading stderr.

EVERY RUN GETS ITS OWN DATABASE. The plan's version of this file inherited
`DEE_CANDIDATES_DB_URL` from the developer's environment, which would have made
these tests pass or fail on whether `data/veritas.db` happened to be migrated --
the exact shape of S8.3B Finding 1, a test that passed in its file and failed
alone. The migrated fixture below is created and thrown away per test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.migrate import upgrade_to_head

ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str, db_url: str, **env_over: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update({
        "DEE_API_AUTH_KEY": "cli-contract-key",
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_CANDIDATES_DB_URL": db_url,
    })
    env.update(env_over)
    return subprocess.run(
        [sys.executable, "-m", "app.retention.sweep", *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300,
    )


@pytest.fixture
def unmigrated_db(tmp_path) -> str:
    """A database URL whose file does not exist yet -- what a cron container
    sees when it starts before (or without) the web service that migrates."""
    return f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"


@pytest.fixture
def migrated_db(settings, unmigrated_db) -> str:
    upgrade_to_head(settings.model_copy(update={"candidates_db_url": unmigrated_db}))
    return unmigrated_db


def test_the_report_is_the_last_line_and_is_json(migrated_db):
    proc = _run(db_url=migrated_db)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout.strip().splitlines()[-1])
    assert report["dry_run"] is True


def test_loading_the_whole_buffer_is_not_the_contract(migrated_db):
    """Documents the trap rather than leaving the next person to find it."""
    proc = _run(db_url=migrated_db)
    lines = proc.stdout.strip().splitlines()
    if len(lines) > 1:
        with pytest.raises(json.JSONDecodeError):
            json.loads(proc.stdout)


def test_a_disabled_sweep_exits_2_on_apply(migrated_db):
    """The cron must be able to tell 'refused' from 'ran and deleted nothing'.
    Both would otherwise be exit 0 with a plausible report."""
    proc = _run("--apply", db_url=migrated_db, DEE_RETENTION_SWEEP_ENABLED="false")
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)


def test_a_disabled_sweep_still_previews(migrated_db):
    """A count is safe, and it is how an operator sees what WOULD go before
    turning the knob on."""
    proc = _run(db_url=migrated_db, DEE_RETENTION_SWEEP_ENABLED="false")
    assert proc.returncode == 0, proc.stderr


def test_an_unmigrated_database_is_refused_by_name(unmigrated_db):
    """FOUND BY RUNNING IT: on a database that has never been migrated the CLI
    died with a forty-line SQLAlchemy traceback and exit 1.

    The web service migrates on boot; this process deliberately does not, and
    on Railway the cron is a SEPARATE container that can run first, or against
    a database a deploy left behind. What the operator gets must therefore be a
    sentence, not a stack trace -- this is the caller its own docstring calls
    'precisely the caller nobody is watching when it goes wrong'.

    Exit 3 is distinct from 2 (disabled) and 0 (ran): a cron alert should be
    able to tell 'nothing to do' from 'refused' from 'the schema is wrong'.
    """
    proc = _run("--apply", db_url=unmigrated_db)
    assert proc.returncode == 3, (proc.returncode, proc.stdout, proc.stderr)
    assert "Traceback" not in proc.stderr, proc.stderr
    assert "not migrated" in proc.stderr.lower(), proc.stderr


def test_the_migration_guard_does_not_block_a_healthy_database(migrated_db):
    """The other half: a guard that refused everything would also pass the test
    above, and would silently stop every purge the portal promises."""
    proc = _run("--apply", db_url=migrated_db)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    assert json.loads(proc.stdout.strip().splitlines()[-1])["dry_run"] is False
