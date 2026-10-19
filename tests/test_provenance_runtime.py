"""Production evaluation needs only request-local first-party observations."""

import builtins

import pytest

from app.core.config import Settings
from app.graph.build import EvaluationEngine
from app.schemas.report import Evidence, EvidenceSource
from app.services import build_default_services
from tests.test_services_features import production  # noqa: F401


RETIRED = {
    "vectorstore_backend": "chroma",
    "vectorstore_init_timeout_seconds": 15,
    "chroma_persist_dir": "./legacy-evidence",
    "chroma_collection": "legacy-evidence",
}


@pytest.mark.parametrize("backend", [None, "chroma", "memory"])
async def test_production_evaluation_never_attempts_chroma(
    production, genuine_resume, monkeypatch, tmp_path, backend,
):
    attempts = []
    original = builtins.__import__

    def without_chroma(name, *args, **kwargs):
        if name == "chromadb" or name.startswith("chromadb."):
            attempts.append(name)
            raise ImportError("Chroma deliberately unavailable")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_chroma)
    values = production.model_dump(exclude=set(RETIRED))
    legacy_dir = tmp_path / "legacy-evidence"
    legacy_dir.mkdir()
    sentinel = legacy_dir / "preserved.bin"
    sentinel.write_bytes(b"synthetic pre-existing legacy data")
    if backend is not None:
        values.update(RETIRED, vectorstore_backend=backend, chroma_persist_dir=str(legacy_dir))
    cfg = Settings(_env_file=None, **values)
    svc = build_default_services(cfg)
    try:
        report = await EvaluationEngine(svc).evaluate(
            resume_text=genuine_resume, github_url="https://github.com/alice/project",
        )
        assert report.verdicts
        assert report.advisory and report.human_review_required
        assert all(v.status.value != "incoherent" for v in report.verdicts)
    finally:
        await svc.aclose()
    assert attempts == [], "unused provenance storage must never initialize"
    assert sentinel.read_bytes() == b"synthetic pre-existing legacy data"
    assert list(legacy_dir.iterdir()) == [sentinel]


@pytest.mark.parametrize("source", ["constructor", "yaml", "dotenv", "environment"])
@pytest.mark.parametrize("backend", ["chroma", "memory"])
def test_retired_settings_are_ignored_without_changing_live_precedence(
    tmp_path, monkeypatch, source, backend,
):
    values = dict(RETIRED, vectorstore_backend=backend)
    yaml = tmp_path / "config.yaml"
    yaml.write_text("page_max_limit: 31\n", encoding="utf-8")
    monkeypatch.setenv("DEE_CONFIG_FILE", str(yaml))
    dotenv = tmp_path / ".env"
    dotenv.write_text("DEE_PAGE_MAX_LIMIT=32\n", encoding="utf-8")
    monkeypatch.setenv("DEE_PAGE_MAX_LIMIT", "33")
    kwargs = {}
    if source == "constructor":
        kwargs.update(values)
    elif source == "yaml":
        with yaml.open("a", encoding="utf-8") as out:
            out.write("".join(f"{key}: {value}\n" for key, value in values.items()))
    elif source == "dotenv":
        with dotenv.open("a", encoding="utf-8") as out:
            out.write("".join(f"DEE_{key.upper()}={value}\n" for key, value in values.items()))
    else:
        for key, value in values.items():
            monkeypatch.setenv("DEE_" + key.upper(), str(value))
    cfg = Settings(_env_file=dotenv, **kwargs)
    assert set(RETIRED).isdisjoint(cfg.model_dump())
    assert cfg.page_max_limit == 33
    assert Settings(_env_file=dotenv, page_max_limit=34, **kwargs).page_max_limit == 34
    monkeypatch.delenv("DEE_PAGE_MAX_LIMIT")
    assert Settings(_env_file=dotenv, **kwargs).page_max_limit == 32
    assert Settings(_env_file=None, **kwargs).page_max_limit == 31


def test_historical_vector_evidence_still_deserializes():
    evidence = Evidence.model_validate({
        "source": "vectorstore", "polarity": "neutral", "detail": "Historical observation",
    })
    assert evidence.source is EvidenceSource.VECTORSTORE
