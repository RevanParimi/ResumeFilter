"""Optional evaluation observer; production retains no duplicate event stream.

Reports and outcomes already live in SQL with explicit deletion/retention.
The former JSONL writer duplicated candidate text outside that lifecycle.
Keep the observer seam for offline tests, but never write a second durable copy.
Existing JSONL files require separate legacy cleanup; this module leaves them alone.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Protocol

from app.core.config import Settings


class Flywheel(Protocol):
    def log(self, record: dict) -> None: ...


def _stamp(record: dict) -> dict:
    return {"logged_at": datetime.now(timezone.utc).isoformat(), **record}


class NullFlywheel:
    """No retention or I/O. SQL reports/outcomes are the durable source."""

    def log(self, record: dict) -> None:
        pass


class InMemoryFlywheel:
    """Explicit test-only observer for synthetic records; never built at runtime."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def log(self, record: dict) -> None:
        self.records.append(_stamp(record))


def build_flywheel(settings: Optional[Settings] = None) -> Flywheel:
    """The legacy flywheel_path setting is accepted but no longer opens a file."""
    return NullFlywheel()
