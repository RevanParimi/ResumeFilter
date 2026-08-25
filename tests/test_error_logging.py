"""Every refusal is findable.

`routes.py` raises HTTPException 138 times and binds no logger. Starlette
answers those itself, so not one of them ever reached the `Exception` handler
in main.py: every 4xx veritas issued left exactly one artifact, a status
integer in the access line. One boundary handler closes that, and routes.py is
not edited to make it true.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services


@pytest.fixture
def client(settings, flywheel):
    services = make_services(settings, flywheel=flywheel)
    with TestClient(
        create_app(services), raise_server_exceptions=False, headers=ADMIN_HEADERS
    ) as c:
        yield c


def _refusals(events):
    return [e for e in events if e.get("event") == "request_refused"]


def test_a_matched_404_is_logged_with_status_and_request_id(client, log_events):
    r = client.get("/report/rep_does_not_exist")
    assert r.status_code == 404
    hits = _refusals(log_events)
    assert hits, "a 404 must leave a refusal line"
    assert hits[0]["status"] == 404
    assert hits[0]["request_id"], "must carry the id the caller was given"


def test_the_refusal_line_carries_the_request_id_the_caller_received(client, log_events):
    """The correlation the runbook promises: a customer quoting X-Request-ID is
    handing the operator an exact grep key."""
    r = client.get("/report/rep_does_not_exist")
    assert _refusals(log_events)[0]["request_id"] == r.headers["X-Request-ID"]


def test_a_refusal_is_logged_exactly_once(client, log_events):
    client.get("/report/rep_does_not_exist")
    assert len(_refusals(log_events)) == 1, "a double-registered handler double-logs"


def test_the_refusal_line_carries_the_reason(client, log_events):
    """`reason` is the same detail string the caller received. Without it the
    line says a refusal happened and still cannot say why."""
    client.get("/report/rep_does_not_exist")
    assert _refusals(log_events)[0]["reason"], "a refusal with no reason is a status code"


def test_an_unmatched_path_is_labelled_by_template_not_by_the_raw_path(client, log_events):
    """Bounded cardinality, the rule OPERATING.md §5 already sets for metrics:
    a scanner walking random URLs must not become unbounded log volume."""
    for suffix in ("aaa", "bbb", "ccc"):
        client.get(f"/no/such/route/{suffix}")
    routes = {e["route"] for e in _refusals(log_events)}
    assert routes == {"__unmatched__"}


def test_an_unmatched_path_logs_at_info_not_warning(client, log_events):
    """Scanner noise at warning is how an operator learns to ignore the
    channel, and then misses the customer being refused."""
    client.get("/no/such/route/at/all")
    assert _refusals(log_events)[0]["log_level"] == "info"


def test_a_matched_refusal_logs_at_warning(client, log_events):
    """A real request to a real route, refused, is the line an operator wants."""
    client.get("/report/rep_does_not_exist")
    assert _refusals(log_events)[0]["log_level"] == "warning"


def test_a_matched_refusal_is_labelled_by_its_route_template(client, log_events):
    """The template, so every missing report is ONE series rather than one per
    report id -- the same reason metrics label this way."""
    client.get("/report/rep_does_not_exist")
    route = _refusals(log_events)[0]["route"]
    assert "{" in route and "rep_does_not_exist" not in route, route


def test_the_response_body_is_unchanged_by_the_handler(client):
    """The wired UI and every smoke parse these bodies. Logging must be
    invisible on the wire."""
    r = client.get("/report/rep_does_not_exist")
    assert r.status_code == 404
    assert "detail" in r.json()


def test_routes_py_contains_no_logging_call():
    """The 138 refusals are logged BECAUSE THEY HAPPENED, not because someone
    remembered. If this ever fails, the boundary handler has been bypassed and
    the next refusal added will be silent again."""
    import app.api.routes as routes_mod

    src = Path(routes_mod.__file__).read_text(encoding="utf-8")
    assert "log.warning" not in src and "log.error" not in src


def test_a_validation_failure_is_logged_with_the_field_locations(client, log_events):
    r = client.post("/evaluate", json={"resume_text": 12345})
    assert r.status_code == 422, r.text
    hits = [e for e in log_events if e.get("event") == "request_invalid"]
    assert hits, "a 422 must leave a line"
    assert any("resume_text" in f for f in hits[0]["fields"])


def test_a_validation_failure_never_logs_the_submitted_value(client, log_output):
    """RequestValidationError.errors() carries an `input` key holding the RAW
    submitted value -- probed, not assumed:

        {"type": "int_parsing", "loc": ["body", "age"],
         "input": "alice@example.in-SECRET-OTP-123456"}

    Logging errors() wholesale would write resume text, candidate addresses and
    login codes into the log -- committing, in the sprint that closes the
    OTP-leak gap, exactly the leak that gap was about.
    """
    secret = "alice@example.in-SECRET-OTP-123456"
    r = client.post("/evaluate", json={"resume_text": {"nested": secret}})
    assert r.status_code == 422, r.text
    assert secret not in log_output.text
    assert "SECRET-OTP" not in log_output.text
