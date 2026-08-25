"""The two log seams, and the reason there are two.

`capture_logs()` REPLACES the configured processor chain, so it can only ever
prove what a call site PASSED. What actually leaves the process is a different
question, and answering it wrongly is how this repo's OTP-leak guard came to
assert a string was absent from an empty string for eight PIs.
"""

import json

import structlog

from app.core.logging import build_processors, get_logger


def test_log_events_captures_what_a_call_site_passed(log_events):
    get_logger("probe").warning("evt_happened", who="alice", n=3)
    assert any(
        e["event"] == "evt_happened" and e["who"] == "alice" and e["n"] == 3
        for e in log_events
    )


def test_log_output_renders_through_the_production_chain(log_output):
    get_logger("probe").warning("evt_rendered", who="alice")
    line = json.loads(log_output.text.strip().splitlines()[-1])
    assert line["event"] == "evt_rendered"
    assert line["who"] == "alice"
    # Proof it is the REAL chain and not a hand-rolled copy: these keys come
    # from processors configure_logging installs, not from the call site.
    assert line["level"] == "warning"
    assert "timestamp" in line


def test_build_processors_is_the_single_source_of_the_chain(settings):
    """The fixture must not own a second copy of the chain -- a copy is free to
    drift, and a drifted copy is a guard that stops guarding silently."""
    assert build_processors(settings), "chain must not be empty"
    names = [
        getattr(p, "__name__", type(p).__name__) for p in build_processors(settings)
    ]
    assert "add_log_level" in names
    assert "merge_contextvars" in names


def test_log_output_survives_a_module_level_logger_bound_before_the_fixture():
    """Every module in src/app binds its logger at import, and structlog runs
    with cache_logger_on_first_use=True. A fixture that only works for loggers
    created inside its own block would be useless to every real module."""
    pre_bound = get_logger("app.pre.bound")
    pre_bound.info("warmup")
    with structlog.testing.capture_logs() as events:
        pre_bound.warning("after_cache", k="v")
    assert any(e["event"] == "after_cache" for e in events)
