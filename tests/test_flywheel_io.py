"""The default observer cannot retain or write another copy of candidate data."""

from __future__ import annotations

from app.services.flywheel import InMemoryFlywheel, build_flywheel


def test_default_observer_never_opens_a_file(settings, monkeypatch):

    def _boom(*a, **kw):
        raise AssertionError("the observer must not perform file I/O")

    monkeypatch.setattr("builtins.open", _boom)
    build_flywheel(settings).log({"claim_text": "private candidate detail"})


def test_legacy_path_does_not_create_directories(settings, tmp_path):
    parent = tmp_path / "unused"
    fw = build_flywheel(settings.model_copy(update={"flywheel_path": str(parent / "fw.jsonl")}))
    fw.log({"claim_text": "private detail", "probes": ["private follow-up"]})
    assert not parent.exists()


def test_explicit_test_observer_keeps_synthetic_events():
    observer = InMemoryFlywheel()
    observer.log({"claim_text": "synthetic test claim"})
    assert observer.records[0]["claim_text"] == "synthetic test claim"
    assert "logged_at" in observer.records[0]
