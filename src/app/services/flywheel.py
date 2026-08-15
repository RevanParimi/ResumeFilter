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


class Flywheel(Protocol):
    def log(self, record: dict) -> None: ...


def _stamp(record: dict) -> dict:
    return {"logged_at": datetime.now(timezone.utc).isoformat(), **record}


class JsonlFlywheel:
    """One JSON object per line. Cheap, greppable, trivially ingestible."""

    def __init__(self, path: Optional[str] = None, settings: Optional[Settings] = None) -> None:
        settings = settings or get_settings()
        self.path = path or settings.flywheel_path
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

    def log(self, record: dict) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(_stamp(record), ensure_ascii=False) + "\n")


class InMemoryFlywheel:
    """Test/inspection sink; keeps records in a list."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def log(self, record: dict) -> None:
        self.records.append(_stamp(record))


def build_flywheel(settings: Optional[Settings] = None) -> Flywheel:
    return JsonlFlywheel(settings=settings or get_settings())
