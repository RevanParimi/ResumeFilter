"""The flywheel is append-only audit, and its writer was unguarded.

On this machine -- Windows, under OneDrive -- a locked file is a recorded trap
rather than a hypothetical, and a blocked audit write raised straight out into
whatever pipeline node called it.
"""

from __future__ import annotations

import pytest

from app.services.flywheel import JsonlFlywheel


def test_a_blocked_write_does_not_take_the_pipeline_down(
    settings, tmp_path, log_events, monkeypatch
):
    fw = JsonlFlywheel(path=str(tmp_path / "fw.jsonl"), settings=settings)

    def _boom(*a, **kw):
        raise OSError("file is locked by another process")

    monkeypatch.setattr("builtins.open", _boom)
    fw.log({"event": "claim_verified"})  # must not raise
    assert any(e["event"] == "flywheel_write_failed" for e in log_events)


def test_a_normal_write_still_lands(settings, tmp_path):
    path = tmp_path / "fw.jsonl"
    fw = JsonlFlywheel(path=str(path), settings=settings)
    fw.log({"event": "claim_verified"})
    assert "claim_verified" in path.read_text(encoding="utf-8")


def test_a_non_serializable_record_still_raises(settings, tmp_path):
    """OSError only. A record that cannot be serialized is a REAL BUG in the
    caller, and this sprint does not convert loud bugs into quiet ones -- that
    is the trade the whole design refused."""
    fw = JsonlFlywheel(path=str(tmp_path / "fw.jsonl"), settings=settings)
    with pytest.raises(TypeError):
        fw.log({"event": "bad", "obj": object()})
