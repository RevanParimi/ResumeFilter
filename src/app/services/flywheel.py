"""Flywheel — append-only record of every (claim → probe → verdict → outcome?).

Pluggable sink for future model training. M0 ships a JSONL writer and an
in-memory sink (tests). The ``outcome`` field is left open for later
human/hiring feedback to close the loop.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional, Protocol

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

_log = get_logger("flywheel")


class Flywheel(Protocol):
    def log(self, record: dict) -> None: ...


def _stamp(record: dict) -> dict:
    return {"logged_at": datetime.now(timezone.utc).isoformat(), **record}


class JsonlFlywheel:
    """One JSON object per line. Cheap, greppable, trivially ingestible."""

    def __init__(self, path: Optional[str] = None, settings: Optional[Settings] = None) -> None:
        settings = settings or get_settings()
        self.path = path or settings.flywheel_path
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        except OSError as exc:
            # Same reasoning as log(): construction happens during service
            # build, so raising here would refuse a whole working app over an
            # advisory sink.
            _log.error("flywheel_mkdir_failed", path=self.path, error=str(exc))

    def log(self, record: dict) -> None:
        # json.dumps runs OUTSIDE the guard on purpose: a record that cannot be
        # serialized is a real bug in the caller and must stay loud. Only the
        # IO is tolerated -- S9.3 adds observability, never tolerance.
        line = json.dumps(_stamp(record), ensure_ascii=False) + "\n"
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:
            # An audit sink that cannot write must not take an evaluation down
            # with it -- but it must not disappear either. On Windows/OneDrive
            # a locked file is a recorded trap in this repo, and a flywheel
            # that has silently stopped recording looks identical to a quiet
            # week right up until someone tries to train on it.
            _log.error("flywheel_write_failed", path=self.path, error=str(exc))


class InMemoryFlywheel:
    """Test/inspection sink; keeps records in a list."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def log(self, record: dict) -> None:
        self.records.append(_stamp(record))


def build_flywheel(settings: Optional[Settings] = None) -> Flywheel:
    return JsonlFlywheel(settings=settings or get_settings())
