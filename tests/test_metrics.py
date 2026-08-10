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
