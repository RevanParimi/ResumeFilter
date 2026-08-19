"""`python -m app.signal_quality.report` (S9.1 Task 11).

A CLI as well as a route, for the same reason the retention sweep has both:
there is no scheduler anywhere in app/, so this is an INVOCABLE thing and never
a daemon. And a cron is the caller nobody is watching when it goes wrong, which
is why the unmigrated-database case gets a sentence and exit 3 from the start
-- S8.6 found the retention sweep answering it with a forty-line traceback.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.migrate import upgrade_to_head
from app.signal_quality.report import main


@pytest.fixture
def migrated_settings(monkeypatch, tmp_path):
    """An ACTUALLY migrated database, and a settings cache that does not leak
    -- get_settings is lru_cached, so without the clears this CLI would read a
    Settings built by whichever test ran first."""
    url = f"sqlite:///{tmp_path.as_posix()}/sq.db"
    monkeypatch.setenv("DEE_CANDIDATES_DB_URL", url)
    monkeypatch.setenv("DEE_API_AUTH_KEY", "k" * 32)
    get_settings.cache_clear()
    upgrade_to_head(get_settings())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def unmigrated_settings(monkeypatch, tmp_path):
    """A real file with no alembic_version row -- the state a cron container
    meets when it starts before the web service has migrated anything."""
    url = f"sqlite:///{tmp_path.as_posix()}/empty.db"
    monkeypatch.setenv("DEE_CANDIDATES_DB_URL", url)
    monkeypatch.setenv("DEE_API_AUTH_KEY", "k" * 32)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_cli_prints_the_report_as_the_last_line_of_stdout(capsys, migrated_settings):
    assert main([]) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["population"]["label_source"] == "outcomes"
    assert len(payload["signals"]) == 12


def test_cli_refuses_an_unmigrated_database_with_exit_3(capsys, unmigrated_settings):
    assert main([]) == 3
    assert "not migrated" in capsys.readouterr().err


def test_the_refusal_is_a_SENTENCE_not_a_stack(tmp_path):
    """IN A REAL PROCESS, deliberately. In-process capsys cannot answer this:
    a logging handler bound to a previous test's captured stream emits its own
    '--- Logging error --- Traceback' into stderr, so an in-process assertion
    reads pytest's plumbing rather than the CLI's output. The retention CLI's
    identical claim is asserted the same way, for the same reason.

    An operator reading a cron log at 3am gets one sentence. S8.6 found the
    retention sweep answering this case with a forty-line stack and exit 1.
    """
    env = os.environ.copy()
    env.update({
        "DEE_API_AUTH_KEY": "sq-cli-key",
        "DEE_OPENROUTER_API_KEY": "",
        "DEE_VECTORSTORE_BACKEND": "memory",
        "DEE_CANDIDATES_DB_URL": f"sqlite:///{tmp_path.as_posix()}/empty.db",
    })
    proc = subprocess.run(
        [sys.executable, "-m", "app.signal_quality.report"],
        cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 3, (proc.returncode, proc.stdout, proc.stderr)
    assert "not migrated" in proc.stderr
    assert "Traceback" not in proc.stderr, proc.stderr


def test_the_refusal_reads_NOTHING(capsys, unmigrated_settings):
    """It must refuse BEFORE opening a session. A refusal that already queried
    is a refusal that can raise on the way to refusing."""
    assert main([]) == 3
    assert "Nothing was read" in capsys.readouterr().err


def test_cli_accepts_the_ledger_source(capsys, migrated_settings):
    assert main(["--source", "ledger"]) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["population"]["label_kind"] == "hire"


def test_operator_labels_are_off_unless_asked_for(capsys, migrated_settings):
    assert main([]) == 0
    off = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert off["population"]["include_operator_labels"] is False

    assert main(["--include-operator-labels"]) == 0
    on = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert on["population"]["include_operator_labels"] is True


def test_an_unknown_source_is_refused_by_argparse(migrated_settings):
    with pytest.raises(SystemExit):
        main(["--source", "nonsense"])
