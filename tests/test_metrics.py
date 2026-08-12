"""S8.3 Phase A: in-process counters. Per-app, never module-global."""

from __future__ import annotations

from app.metrics.registry import Metrics, build_metrics


def test_counters_start_at_zero_and_increment():
    m = Metrics()
    m.increment("http_requests", route="/healthz", method="GET", status="200")
    m.increment("http_requests", route="/healthz", method="GET", status="200")
    key = ("http_requests",
           (("method", "GET"), ("route", "/healthz"), ("status", "200")))
    assert m.snapshot()[key] == 2


def test_label_sets_are_distinct_series():
    m = Metrics()
    m.increment("http_requests", route="/a", method="GET", status="200")
    m.increment("http_requests", route="/b", method="GET", status="200")
    assert len(m.snapshot()) == 2


def test_add_accumulates_and_increment_is_add_of_one():
    m = build_metrics()
    m.add("retention_deleted", 5, data_class="resumes")
    m.increment("retention_deleted", data_class="resumes")
    assert m.snapshot()[("retention_deleted", (("data_class", "resumes"),))] == 6


def test_add_refuses_to_move_a_counter_BACKWARDS():
    """Counters only go up. A negative amount would rewrite a series a scraper
    has already read as monotonic, and rate() over it would answer nonsense."""
    import pytest

    m = build_metrics()
    with pytest.raises(ValueError):
        m.add("retention_deleted", -1, data_class="resumes")


def test_adding_zero_creates_no_series_at_all():
    """A class that swept nothing must not appear as a `0` line: absent and
    zero read the same to a human and differently to a scraper, and the honest
    one here is absent."""
    m = build_metrics()
    m.add("retention_deleted", 0, data_class="resumes")
    assert m.snapshot() == {}


def test_two_registries_do_not_share_state():
    """A module-level counter would be shared by every test in the suite, and
    the first ordering-dependent assertion would be an unreproducible flake.
    This is why Metrics hangs off the injected Services bundle."""
    a, b = build_metrics(), build_metrics()
    a.increment("http_requests", route="/x", method="GET", status="200")
    assert b.snapshot() == {}


def test_render_is_prometheus_text():
    m = Metrics()
    m.increment("rate_limit_decisions", rule="login_request", scope="email",
                decision="denied")
    out = m.render()
    assert "# TYPE veritas_rate_limit_decisions_total counter" in out
    assert (
        'veritas_rate_limit_decisions_total'
        '{decision="denied",rule="login_request",scope="email"} 1'
    ) in out


def test_render_emits_a_type_line_once_per_metric():
    m = Metrics()
    m.increment("http_requests", route="/a", method="GET", status="200")
    m.increment("http_requests", route="/b", method="GET", status="200")
    assert m.render().count("# TYPE veritas_http_requests_total counter") == 1


def test_label_values_are_escaped():
    """A label value carrying a quote or a backslash would produce a document
    no parser can read -- route templates are ours, but the __unmatched__
    fallback is only as safe as the escaping behind it."""
    m = Metrics()
    m.increment("http_requests", route='/a"b\\c', method="GET", status="200")
    line = [
        x for x in m.render().splitlines()
        if x.startswith("veritas_http_requests")
    ][0]
    assert '\\"' in line and "\\\\" in line


def test_duration_renders_as_a_sum_and_a_count():
    """An average, deliberately: no buckets, no quantiles, and OPERATING.md
    says so rather than letting a reader assume a histogram."""
    m = Metrics()
    m.observe_duration("/healthz", 10.0)
    m.observe_duration("/healthz", 30.0)
    out = m.render()
    assert 'veritas_http_request_duration_ms_sum{route="/healthz"} 40' in out
    assert 'veritas_http_request_duration_ms_count{route="/healthz"} 2' in out


def test_an_empty_registry_renders_an_empty_document():
    assert build_metrics().render() == ""


# ── _HELP declares only metrics that exist ───────────────────────────────────

import re  # noqa: E402
from pathlib import Path  # noqa: E402

from app.metrics.registry import _HELP  # noqa: E402

#: `increment("some_name", ...)` OR `add("some_name", n, ...)` anywhere under
#: app/. The registry's own `def increment(self, name: str, ...)` carries no
#: quote and cannot match.
#:
#: The `add` arm is not cosmetic: a counter that moves N at a time is written
#: that way, and a scanner blind to it would report a declared-inert metric as
#: clean -- passing by not looking, which is the failure the guard exists to
#: prevent. S8.3 Phase B's `retention_deleted` is exactly that shape.
_CALL_SITE = re.compile(r"""(?:increment|add)\(\s*["']([a-z_]+)["']""")


def _incremented_names() -> set[str]:
    root = Path(__file__).resolve().parent.parent / "app"
    return {
        name
        for path in root.rglob("*.py")
        for name in _CALL_SITE.findall(path.read_text(encoding="utf-8"))
    }


def test_every_declared_metric_has_a_call_site():
    """THE REVIEW FINDING, turned into a rule the next sprint cannot break.

    `llm_calls`, `asr_calls`, `screening_items` and `retention_deleted` were
    declared here with nothing incrementing them -- in the same branch whose
    headline finding was that `auth_sessions.ip_hash` had been "declared,
    plumbed through two layers, and never populated" while the docs described
    it as implemented. Disclosing the gap in OPERATING.md was better than
    hiding it and still was not the fix.

    A declared-inert metric is worse than a missing one: a scraper shows the
    series as absent, an operator reads absent as "nothing happened", and the
    runbook step that tells them to read it quietly cannot answer.

    Phase B adds `retention_deleted` in the same commit as the sweep that
    increments it, and this test is what makes that ordering mandatory rather
    than remembered.
    """
    declared = set(_HELP)
    incremented = _incremented_names()
    assert declared - incremented == set(), (
        f"declared in _HELP with no call site: "
        f"{sorted(declared - incremented)}"
    )


def test_the_call_site_scanner_can_actually_find_something():
    """Guards the test above from passing because the regex matches nothing --
    a scanner that finds zero call sites would call any _HELP table clean."""
    assert "rate_limit_decisions" in _incremented_names()
    assert "http_requests" in _incremented_names()


def test_the_call_site_scanner_sees_add_as_well_as_increment():
    """A counter that moves N at a time is written `add(...)`, so a scanner
    that only knew `increment(` would call a declared-inert `retention_deleted`
    clean -- passing BY NOT LOOKING, which is the exact failure the guard above
    exists to prevent. `retention_deleted` has no `increment` call site
    anywhere, so this assertion is only satisfiable through the `add` arm."""
    assert "retention_deleted" in _incremented_names()


# ── the route and the counting middleware ────────────────────────────────────

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from tests.conftest import make_services  # noqa: E402


@pytest.fixture
def client(services):
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c


def test_metrics_requires_the_admin_credential(client):
    """It is on the admin router, so the gate is INHERITED rather than
    remembered -- there is no second place to forget it."""
    assert client.get("/metrics").status_code == 401


def test_metrics_renders_prometheus_text(client, admin_headers):
    client.get("/healthz")
    resp = client.get("/metrics", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "veritas_http_requests_total" in resp.text


def test_requests_are_labelled_by_ROUTE_TEMPLATE_not_by_path(client, admin_headers):
    """THE cardinality decision. Labelling by raw path makes one series per
    batch id, and a scanner walking random URLs is an unbounded memory leak
    dressed as observability."""
    client.get("/screening/batches/aaaaaaaa-0000-0000-0000-000000000000")
    client.get("/screening/batches/bbbbbbbb-0000-0000-0000-000000000000")
    text = client.get("/metrics", headers=admin_headers).text
    assert 'route="/screening/batches/{batch_id}"' in text
    assert "aaaaaaaa" not in text and "bbbbbbbb" not in text


def test_the_template_label_comes_from_the_request_scope(client, admin_headers):
    """THE TRIPWIRE for `_route_template`'s one remaining line.

    The S8.3 review deleted a fallback that re-resolved the route by scanning
    the table, having measured that its successful branch never executes on
    starlette 1.3.1 -- the router populates `scope["route"]` before the
    endpoint runs, and BaseHTTPMiddleware shares that dict. Deleting it makes
    the label depend entirely on that one framework behaviour, so this test
    exists to fail loudly if an upgrade ever changes it, instead of every label
    quietly degrading to `__unmatched__` and looking like working code.

    A two-parameter route, deliberately: it cannot be produced by echoing the
    raw path back.
    """
    client.get("/candidates/cand-1/resumes/res-1")
    text = client.get("/metrics", headers=admin_headers).text
    assert 'route="/candidates/{candidate_id}/resumes/{resume_id}"' in text
    assert "cand-1" not in text and "res-1" not in text


def test_a_405_is_still_labelled_by_its_template(client, admin_headers):
    """A method mismatch never reaches the endpoint, but the router HAS set the
    route by then (it matches partially to answer 405). Measured, because the
    deleted fallback's whole premise was that cases like this one needed it."""
    client.post("/healthz")
    text = client.get("/metrics", headers=admin_headers).text
    assert 'veritas_http_requests_total{method="POST",route="/healthz",status="405"} 1' in text


def test_an_unmatched_path_gets_one_shared_label(client, admin_headers):
    client.get("/no/such/thing/1")
    client.get("/no/such/thing/2")
    text = client.get("/metrics", headers=admin_headers).text
    assert 'route="__unmatched__"' in text
    assert "no/such/thing" not in text


def test_a_rate_limited_request_is_counted_as_denied(
    settings, fake_github, flywheel, admin_headers, tmp_path
):
    """The pairing that justifies the phase: a limit you cannot observe is a
    guess."""
    tuned = settings.model_copy(update={
        "email_provider": "capture",
        "email_capture_path": str(tmp_path / "mail.jsonl"),
        "rate_limit_login_per_hour_per_email": 1,
    })
    services = make_services(tuned, github=fake_github, flywheel=flywheel)
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        c.post("/auth/org/login", json={"email": "a@example.com"})
        c.post("/auth/org/login", json={"email": "a@example.com"})
        text = c.get("/metrics", headers=admin_headers).text
    assert 'decision="denied"' in text
    assert 'rule="login_request"' in text


def test_durations_are_recorded_against_the_template_too(client, admin_headers):
    client.get("/healthz")
    text = client.get("/metrics", headers=admin_headers).text
    assert 'veritas_http_request_duration_ms_count{route="/healthz"}' in text
