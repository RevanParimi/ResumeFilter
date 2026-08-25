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


def test_log_output_reaches_a_logger_bound_and_used_before_the_fixture(log_output):
    """Every module in src/app binds `log = get_logger(__name__)` at import, so
    a seam that only works for loggers created inside its own block would be
    useless to all 179 of them.

    THIS TEST WAS ITSELF VACUOUS WHEN FIRST WRITTEN, and the mutation step of
    the next task is what caught it: it called `capture_logs` directly instead
    of taking the `log_output` fixture, so it exercised structlog and never the
    seam it is named after. With production's `cache_logger_on_first_use=True`
    the real fixture collected `''` from exactly this shape. It now takes the
    fixture, and the warmup call below is the part that must not break it --
    that first call is what froze the factory before `_uncached_loggers`.
    """
    pre_bound = get_logger("app.pre.bound")
    pre_bound.info("warmup_that_would_have_frozen_the_factory")
    pre_bound.warning("after_warmup", k="v")
    assert "after_warmup" in log_output.text


def test_the_seams_disagree_by_design(log_output):
    """The two seams answer different questions, and a redaction processor is
    the case that separates them. Kept as a live demonstration because the
    whole sprint turns on nobody confusing the two again."""
    with structlog.testing.capture_logs() as events:
        get_logger("probe").warning("evt", secret="hunter2")
    # capture_logs sees the PRE-processor event dict...
    assert events[0]["secret"] == "hunter2"
    # ...while the rendered seam is the artifact an operator or a log shipper
    # actually receives. Nothing was captured into it inside that block.
    assert "hunter2" not in log_output.text
