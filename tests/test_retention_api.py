"""The sweep's two doors: an admin route and a CLI (S8.3 Phase B).

There is no scheduler in `app/`, so both of these are how the sweep ever runs.
A rule enforced at one entry point and forgotten at the other is this repo's
signature defect, so the disabled-config refusal is asserted at BOTH.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import Base, make_engine
from app.main import create_app
from app.retention.sweep import main

ALL_CLASSES = {
    "resumes", "profile_sources", "verifications", "interviews",
    "interview_records", "coding_rounds", "observed_offers", "audit_log",
    "batch_item_text", "rate_limit_counters", "login_state",
}


@pytest.fixture
def client(services):
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c


def test_the_sweep_requires_the_admin_credential(client):
    assert client.post("/admin/retention/sweep", json={}).status_code == 401


def test_an_empty_body_is_a_DRY_RUN(client, admin_headers):
    """The most destructive operation in the repo must not delete because
    somebody posted an empty body. A cron passes {"dry_run": false} on purpose,
    which is one word of evidence that somebody meant it."""
    r = client.post("/admin/retention/sweep", json={}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["dry_run"] is True


def test_the_report_names_every_data_class(client, admin_headers):
    body = client.post("/admin/retention/sweep", json={}, headers=admin_headers).json()
    assert {c["data_class"] for c in body["by_class"]} == ALL_CLASSES
    assert body["truncated"] is False
    assert "at" in body


def test_a_real_run_is_refused_409_when_the_sweep_is_disabled(services, admin_headers):
    services.settings.retention_sweep_enabled = False
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        r = c.post("/admin/retention/sweep", json={"dry_run": False},
                   headers=admin_headers)
        assert r.status_code == 409
        assert r.json()["detail"] == "retention_sweep_disabled"


def test_a_DRY_RUN_still_works_when_the_sweep_is_disabled(services, admin_headers):
    """A count is safe, and it is the operator's only way to see what WOULD go
    before they decide to turn the knob on."""
    services.settings.retention_sweep_enabled = False
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        r = c.post("/admin/retention/sweep", json={}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["dry_run"] is True


# ── the second door: python -m app.retention.sweep ───────────────────────────


@pytest.fixture
def cli_env(monkeypatch, tmp_path):
    """A migrated-shaped database and a settings cache that does not leak.

    `get_settings` is lru_cached, so without the clears the CLI would read a
    Settings built by whichever test ran first -- and the disabled-sweep test
    would pass or fail on ordering rather than on behaviour.
    """
    url = f"sqlite:///{tmp_path.as_posix()}/cli.db"
    Base.metadata.create_all(make_engine(url))
    monkeypatch.setenv("DEE_CANDIDATES_DB_URL", url)
    monkeypatch.setenv("DEE_API_AUTH_KEY", "k" * 32)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _report(captured) -> dict:
    """The CLI's report is the LAST line of stdout.

    Found by this test rather than designed: the process shares stdout with
    the structured log, so run_sweep's own `retention_sweep` line lands there
    first and a json.loads of the whole buffer raises "Extra data". A cron
    piping to `jq` is unaffected (a stream of JSON documents is what jq eats);
    a caller doing json.loads(output) is, so the contract is asserted here.
    """
    lines = [x for x in captured.out.splitlines() if x.strip()]
    return json.loads(lines[-1])


def test_the_cli_defaults_to_a_dry_run_and_prints_the_report(capsys, cli_env):
    assert main([]) == 0
    printed = _report(capsys.readouterr())
    assert printed["dry_run"] is True
    assert {c["data_class"] for c in printed["by_class"]} == ALL_CLASSES


def test_the_cli_needs_an_explicit_flag_to_delete(capsys, cli_env):
    assert main(["--apply"]) == 0
    assert _report(capsys.readouterr())["dry_run"] is False


def test_the_cli_refuses_to_apply_when_the_sweep_is_disabled(capsys, monkeypatch,
                                                             cli_env):
    """The same refusal as the route's 409, at the SECOND door -- a rule
    enforced at one entry point and not the other is this repo's signature
    defect, and a cron is exactly the caller nobody watches."""
    monkeypatch.setenv("DEE_RETENTION_SWEEP_ENABLED", "false")
    get_settings.cache_clear()
    assert main(["--apply"]) == 2
    assert "retention_sweep_disabled" in capsys.readouterr().err


def test_the_cli_still_previews_when_the_sweep_is_disabled(capsys, monkeypatch,
                                                           cli_env):
    monkeypatch.setenv("DEE_RETENTION_SWEEP_ENABLED", "false")
    get_settings.cache_clear()
    assert main([]) == 0
    assert _report(capsys.readouterr())["dry_run"] is True
