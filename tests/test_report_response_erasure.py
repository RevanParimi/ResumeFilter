"""Report-only deletion must be observed before returning a saved evaluation."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import select

from app.candidates.store import CandidateStore
from app.core.config import Settings
from app.reports.schema import OutcomeRecord
from app.reports.store import SqlReportStore
from app.screening.ingest import IngestDeps, IngestRefused, ingest_resume
from app.screening.models import ScreeningInputRow
from app.services.llm import NullLLM
from tests.test_report_erasure_concurrency import database
from tests.test_report_store import _report
from tests.test_screening_batches_api import _client, _key, _register
from tests.test_screening_erasure_concurrency import assert_scrubbed

SHORT = "Synthetic Engineer\nEmail: report@example.com\nSkills: Python"
LONG = SHORT + "\n" + " ".join(f"synthetic{i}" for i in range(90))
PATHS = {"admin": "/candidates", "org": "/screening/candidates", "standalone": "/evaluate"}


def request_parts(services, door):
    _, key = _key(services)
    return PATHS[door], {"X-Org-Key": key} if door == "org" else {}


@pytest.mark.parametrize("door", PATHS)
@pytest.mark.parametrize("text", [SHORT, LONG], ids=["short", "long"])
def test_http_refuses_report_erased_after_save(services, monkeypatch, door, text):
    path, headers = request_parts(services, door)
    keeper = _report()
    services.report_store.save(keeper)
    original = services.report_store.save
    saved = []

    def save_then_erase(report, **kwargs):
        original(report, **kwargs)
        saved.append(report)
        eraser = SqlReportStore(services.candidates._session_factory)
        assert eraser.add_outcome(OutcomeRecord(report_id=report.id,
                                              outcome="inconclusive", recorded_by="operator"))
        assert eraser.delete(report.id)

    with _client(services) as client:
        with monkeypatch.context() as scoped:
            scoped.setattr(services.report_store, "save", save_then_erase)
            response = client.post(path, headers=headers, json={"resume_text": text})
        assert len(saved) == 1
        assert response.status_code == 422, response.text
        assert response.json() == {"detail": "report_erased"}
        assert services.report_store.get(saved[0].id) is None
        assert services.report_store.outcomes(saved[0].id) == []
        assert services.report_store.get(keeper.id) == keeper
        if door != "standalone":
            assert services.candidates.get_candidate(saved[0].candidate_id) is not None
            assert len(services.candidates.list_resumes(saved[0].candidate_id)) == 1
        # A fresh request remains allowed and may reuse the surviving resume.
        fresh = client.post(path, headers=headers, json={"resume_text": text})
        assert fresh.status_code == 200, fresh.text
        if door != "standalone":
            assert fresh.json()["duplicate_resume"]
            assert fresh.json()["candidate_id"] == saved[0].candidate_id
            assert fresh.json()["report"]["id"] != saved[0].id
        else:
            assert fresh.json()["id"] != saved[0].id


def test_batch_report_refusal_precedes_completion_and_clears_retry(services, monkeypatch):
    _, key = _key(services)
    _, other_key = _key(services, "Other agency")
    original = services.report_store.save
    saved = []

    def save_then_erase(report, **kwargs):
        original(report, **kwargs)
        saved.append(report)
        assert services.report_store.delete(report.id)

    def forbidden(*args, **kwargs):
        pytest.fail("shared ingest must refuse before completion")

    with _client(services) as client:
        batch = _register(client, key, [LONG]).json()["id"]
        headers = {"X-Org-Key": key}
        with monkeypatch.context() as scoped:
            scoped.setattr(services.report_store, "save", save_then_erase)
            scoped.setattr(services.screening._store, "complete", forbidden)
            response = client.post(f"/screening/batches/{batch}/process", headers=headers)
        assert response.status_code == 200, response.text
        assert (response.json()["processed"], response.json()["failed"]) == (0, 1)
        row = client.get(f"/screening/batches/{batch}/queue", headers=headers).json()["rows"][0]
        assert_scrubbed(services.candidates._session_factory, row["item_id"], "report")
        with services.candidates._session_factory() as session:
            assert list(session.scalars(select(ScreeningInputRow))) == []
        assert services.candidates.get_candidate(saved[0].candidate_id) is not None
        assert services.candidates.list_resumes(saved[0].candidate_id)
        denied = client.get(f"/screening/batches/{batch}/queue", headers={"X-Org-Key": other_key})
        assert denied.status_code == 404
        retry = client.post(f"/screening/batches/{batch}/retry", headers=headers).json()
        assert (retry["requeued"], retry["skipped"]) == (0, 1)
        fresh = _register(client, key, [LONG]).json()["id"]
        result = client.post(f"/screening/batches/{fresh}/process", headers=headers).json()
        assert (result["processed"], result["failed"]) == (1, 0)


@pytest.mark.parametrize("door", ["admin", "org"])
def test_non_evaluated_upload_needs_no_report_lookup(services, monkeypatch, door):
    path, headers = request_parts(services, door)

    def forbidden(*args, **kwargs):
        pytest.fail("evaluate=False has no report to check")

    monkeypatch.setattr(services.report_store, "get", forbidden)
    with _client(services) as client:
        response = client.post(path, headers=headers, json={"resume_text": SHORT, "evaluate": False})
        assert response.status_code == 200
        assert response.json()["report"] is None


@pytest.mark.parametrize("door", PATHS)
def test_unrelated_lookup_failure_is_not_erasure(services, monkeypatch, door):
    path, headers = request_parts(services, door)

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic private database detail")

    with _client(services) as client:
        with monkeypatch.context() as scoped:
            scoped.setattr(services.report_store, "get", broken)
            response = client.post(path, headers=headers, json={"resume_text": SHORT})
        assert response.status_code == 500
        assert "synthetic private" not in response.text
        assert "report_erased" not in response.text
        assert client.post(path, headers=headers, json={"resume_text": SHORT}).status_code == 200


@pytest.mark.parametrize("door", PATHS)
def test_deletion_after_final_report_read_leaves_only_a_response_snapshot(services, monkeypatch, door):
    path, headers = request_parts(services, door)
    original = services.report_store.get
    read = []

    def read_then_erase(report_id):
        result = original(report_id)
        assert result is not None
        read.append(report_id)
        assert services.report_store.delete(report_id)
        return result

    with _client(services) as client:
        with monkeypatch.context() as scoped:
            scoped.setattr(services.report_store, "get", read_then_erase)
            response = client.post(path, headers=headers, json={"resume_text": SHORT})
        assert response.status_code == 200, response.text
        report = response.json() if door == "standalone" else response.json()["report"]
        assert read == [report["id"]]
        assert original(report["id"]) is None  # no durable resurrection


@pytest.mark.parametrize("order", ["erase_first", "response_first"])
def test_competing_report_erasure_and_ingest_response(database, monkeypatch, order):
    _, factory = database
    candidates = CandidateStore(factory)
    reports = SqlReportStore(factory)
    keeper = _report(candidate_id="b")
    reports.save(keeper)
    deps = IngestDeps(candidates, reports, NullLLM(), Settings(_env_file=None, openrouter_api_key=""))
    ready, release = Event(), Event()
    original = reports.save
    saved = []

    class Engine:
        async def evaluate(self, **kwargs):
            return _report()

    def save_and_pause(report, **kwargs):
        original(report, **kwargs)
        saved.append(report)
        ready.set()
        assert release.wait(20)

    monkeypatch.setattr(reports, "save", save_and_pause)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(lambda: asyncio.run(ingest_resume(
            deps, Engine(), text=SHORT, domain="genai", evaluate=True, org_id=None)))
        try:
            assert ready.wait(20)
            if order == "erase_first":
                assert SqlReportStore(factory).delete(saved[0].id)
        finally:
            release.set()
        if order == "erase_first":
            with pytest.raises(IngestRefused) as exc:
                pending.result(timeout=20)
            assert exc.value.reason == "report_erased"
        else:
            assert pending.result(timeout=20).report.id == saved[0].id
            assert SqlReportStore(factory).delete(saved[0].id)
    assert reports.get(saved[0].id) is None
    assert candidates.get_candidate(saved[0].candidate_id) is not None
    assert candidates.list_resumes(saved[0].candidate_id)
    assert reports.get(keeper.id) == keeper
