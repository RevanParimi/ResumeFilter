"""structlog configuration.

One call to :func:`configure_logging` at process start wires structlog to emit
either JSON (prod) or pretty console (dev) lines, and routes the stdlib logging
used by our dependencies (openai, httpx, chromadb, uvicorn) through the same
pipeline. Everywhere else, just::

    from app.core.logging import get_logger
    log = get_logger(__name__)
    log.info("claim_extracted", claim_id=c.id, claim_type=c.claim_type)

Structured key/values (not f-strings) so the flywheel and ops can query logs.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import get_settings

_CONFIGURED = False


def build_processors(settings) -> list[structlog.types.Processor]:
    """The processor chain, WITHOUT a renderer, as one source of truth.

    Extracted so tests can render through the REAL chain instead of a second
    copy of it. A copy is free to drift, and the drift is invisible: the tests
    keep passing while they stop describing production. That is precisely the
    failure S9.3 exists to close -- the OTP-leak guard asserted a string was
    absent from an empty string for eight PIs -- so the fixture is wired to the
    shipped list by construction rather than by anyone remembering.
    """
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]


def configure_logging() -> None:
    """Idempotently configure structlog + stdlib logging from settings."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level, logging.INFO)

    shared_processors = build_processors(settings)

    if settings.log_json:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (deps) through a plain handler at the same level so
    # our JSON/console output stays consistent and noisy libs are tamed.
    handler = logging.StreamHandler(sys.stdout)
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "chromadb", "urllib3"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))

    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger, configuring logging on first use."""
    if not _CONFIGURED:
        configure_logging()
    return structlog.get_logger(name)
