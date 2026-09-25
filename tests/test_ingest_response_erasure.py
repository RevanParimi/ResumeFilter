"""Observed late erasure must not be returned as a successful upload."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import select

from app.candidates.models import FingerprintRow
from app.candidates.store import CandidateErasedError, CandidateStore, ResumeErasedError
from app.core.config import Settings
from app.graph.build import EvaluationEngine
from app.reports.store import SqlReportStore
from app.screening.ingest import IngestDeps, IngestRefused, ingest_resume
from app.services.llm import NullLLM
from tests.test_report_erasure_concurrency import database
from tests.test_candidate_store import extraction
from tests.test_screening_batches_api import _client, _key, _register
from tests.test_screening_erasure_concurrency import assert_scrubbed

SHORT = "Synthetic Short\nEmail: short@example.com\nSkills: Python"
LONG = SHORT + "\n" + " ".join(f"synthetic{i}" for i in range(90))


def test_subject_guard_checks_both_parents_and_ownership(database):
    _, factory = database
    store = CandidateStore(factory)
    saved = store.ingest(extraction(email="owner@example.com"), SHORT)
    assert store.require_ingest_subject(saved.candidate_id, saved.resume_id) is None
    with pytest.raises(ValueError, match="resume_candidate_mismatch"):
        store.require_ingest_subject("b", saved.resume_id)
    with pytest.raises(ResumeErasedError):
        store.require_ingest_subject(saved.candidate_id, "missing")
    assert store.delete_resume(saved.resume_id)
    with pytest.raises(ResumeErasedError):
        store.require_ingest_subject(saved.candidate_id, saved.resume_id)
    assert store.delete_candidate(saved.candidate_id)
    with pytest.raises(CandidateErasedError):
        store.require_ingest_subject(saved.candidate_id, saved.resume_id)


@pytest.mark.asyncio
async def test_unrelated_guard_lookup_failure_propagates(services, monkeypatch):
    def broken(*_):
        raise LookupError("unrelated lookup failure")
    monkeypatch.setattr(services.candidates, "require_ingest_subject", broken)
    deps = IngestDeps(services.candidates, services.report_store, services.llm, services.settings)
    with pytest.raises(LookupError, match="unrelated lookup failure"):
        await ingest_resume(deps, None, text=SHORT, domain="genai", evaluate=False, org_id=None)


def arm(services, monkeypatch, parent, boundary):
    saved = []
    original = services.candidates.ingest

    def erase():
        outcome = saved[-1]
        if parent == "candidate":
            assert services.portal.erase(outcome.candidate_id)["deleted"]
        else:
            assert services.candidates.delete_resume(outcome.resume_id)

    def ingest(*args, **kwargs):
        result = original(*args, **kwargs)
        saved.append(result)
        if boundary == "short":
            erase()
        return result
    monkeypatch.setattr(services.candidates, "ingest", ingest)
    if boundary in ("fingerprint", "comparison", "report"):
        target, method = ((services.report_store, "save") if boundary == "report" else
                          (services.candidates, "save_fingerprint" if boundary == "fingerprint" else "similar_resumes"))
        original_method = getattr(target, method)

        def call_then_erase(*args, **kwargs):
            result = original_method(*args, **kwargs)
            erase()
            return result
        monkeypatch.setattr(target, method, call_then_erase)
    elif boundary == "evaluation":
        original_eval = EvaluationEngine.evaluate

        async def evaluate(self, **kwargs):
            result = await original_eval(self, **kwargs)
            erase()
            return result
        monkeypatch.setattr(EvaluationEngine, "evaluate", evaluate)
    return saved


@pytest.mark.parametrize("parent", ["candidate", "resume"])
@pytest.mark.parametrize("door", ["admin", "org"])
@pytest.mark.parametrize("boundary,evaluate", [
    ("short", False), ("short", True), ("fingerprint", False), ("fingerprint", True),
    ("comparison", False), ("comparison", True), ("evaluation", True), ("report", True),
])
def test_upload_refuses_subject_erased_after_ingest(services, monkeypatch, parent, door, boundary, evaluate):
    _, key = _key(services)
    path = "/candidates" if door == "admin" else "/screening/candidates"
    headers = {} if door == "admin" else {"X-Org-Key": key}
    with _client(services) as client:
        kept = client.post(path, headers=headers, json={"resume_text":
            "Survivor\nEmail: survivor@example.com\nSkills: Java", "evaluate": False}).json()
        with monkeypatch.context() as scoped:
            saved = arm(services, scoped, parent, boundary)
            if boundary in ("short", "fingerprint", "comparison"):
                async def forbidden(*args, **kwargs):
                    pytest.fail("observed erasure must stop evaluation")
                scoped.setattr(EvaluationEngine, "evaluate", forbidden)
            response = client.post(path, headers=headers, json={"resume_text":
                SHORT if boundary == "short" else LONG, "evaluate": evaluate})
        assert response.status_code == 422, response.text
        assert response.json() == {"detail": f"{parent}_erased"}
        assert len(saved) == 1
        cid = saved[0].candidate_id
        assert services.candidates.list_resumes(cid) == []
        if parent == "candidate":
            assert services.candidates.get_candidate(cid) is None
            assert services.report_store.for_candidate(cid) == []
        elif boundary != "report":
            assert services.report_store.for_candidate(cid) == []
        else:
            # Deleting a resume does not change independently retained reports.
            assert len(services.report_store.for_candidate(cid)) == 1
        with services.candidates._session_factory() as session:
            assert not list(session.scalars(select(FingerprintRow).where(FingerprintRow.candidate_id == cid)))
        assert services.candidates.get_candidate(kept["candidate_id"]) is not None
        retry = client.post(path, headers=headers, json={"resume_text":
            SHORT if boundary == "short" else LONG, "evaluate": False})
        assert retry.status_code == 200  # distinct fresh upload remains permitted
        duplicate = client.post(path, headers=headers, json={"resume_text":
            SHORT if boundary == "short" else LONG, "evaluate": False})
        assert duplicate.status_code == 200 and duplicate.json()["duplicate_resume"]


@pytest.mark.parametrize("parent", ["candidate", "resume"])
@pytest.mark.parametrize("boundary", ["comparison", "evaluation", "report"])
def test_batch_late_refusal_scrubs_retry_and_next_batch_proceeds(services, monkeypatch, parent, boundary):
    _, key = _key(services)
    _, other_key = _key(services, "Other")
    headers = {"X-Org-Key": key}
    with _client(services) as client:
        batch = _register(client, key, [LONG]).json()["id"]
        with monkeypatch.context() as scoped:
            arm(services, scoped, parent, boundary)
            result = client.post(f"/screening/batches/{batch}/process", headers=headers)
        assert result.status_code == 200
        assert (result.json()["processed"], result.json()["failed"]) == (0, 1)
        row = client.get(f"/screening/batches/{batch}/queue", headers=headers).json()["rows"][0]
        assert_scrubbed(services.candidates._session_factory, row["item_id"], parent)
        assert client.get(f"/screening/batches/{batch}/queue", headers={"X-Org-Key": other_key}).status_code == 404
        retry = client.post(f"/screening/batches/{batch}/retry", headers=headers).json()
        assert (retry["requeued"], retry["skipped"]) == (0, 1)
        next_batch = _register(client, key, ["Survivor\nEmail: next@example.com\nSkills: Java"]).json()["id"]
        result = client.post(f"/screening/batches/{next_batch}/process", headers=headers).json()
        assert (result["processed"], result["failed"]) == (1, 0)


@pytest.mark.parametrize("door", ["admin", "org"])
def test_upload_refuses_erasure_between_subject_check_and_report_save(services, monkeypatch, door):
    _, key = _key(services)
    path = "/candidates" if door == "admin" else "/screening/candidates"
    headers = {} if door == "admin" else {"X-Org-Key": key}
    original_save = services.report_store.save
    attempted = []

    def erase_then_save(report, **kwargs):
        attempted.append(report)
        assert services.portal.erase(report.candidate_id)["deleted"]
        return original_save(report, **kwargs)

    with _client(services) as client:
        with monkeypatch.context() as scoped:
            scoped.setattr(services.report_store, "save", erase_then_save)
            response = client.post(path, headers=headers, json={"resume_text": LONG, "evaluate": True})
        assert len(attempted) == 1
        assert response.status_code == 422, response.text
        assert response.json() == {"detail": "candidate_erased"}
        assert services.report_store.get(attempted[0].id) is None
        assert services.candidates.get_candidate(attempted[0].candidate_id) is None
        assert client.post(path, headers=headers, json={
            "resume_text": LONG, "evaluate": True}).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["evaluation", "report"])
async def test_unrelated_late_failure_propagates(services, monkeypatch, boundary):
    def broken_save(*args, **kwargs):
        raise RuntimeError("unrelated report failure")

    async def broken_evaluation(*args, **kwargs):
        raise RuntimeError("unrelated evaluation failure")

    if boundary == "report":
        monkeypatch.setattr(services.report_store, "save", broken_save)
    else:
        monkeypatch.setattr(EvaluationEngine, "evaluate", broken_evaluation)
    deps = IngestDeps(services.candidates, services.report_store, services.llm, services.settings)
    with pytest.raises(RuntimeError, match=f"unrelated {boundary} failure"):
        await ingest_resume(deps, EvaluationEngine(services), text=LONG,
                            domain="genai", evaluate=True, org_id=None)


@pytest.mark.parametrize("parent", ["candidate", "resume"])
def test_competing_erasure_after_fingerprint_before_response(database, monkeypatch, parent):
    _, factory = database
    candidates = CandidateStore(factory)
    deps = IngestDeps(candidates, SqlReportStore(factory), NullLLM(),
                     Settings(_env_file=None, openrouter_api_key=""))
    ready, release = Event(), Event()
    saved = []
    original = candidates.ingest

    def ingest(*args, **kwargs):
        result = original(*args, **kwargs)
        saved.append(result)
        return result

    original_compare = candidates.similar_resumes

    def compare(*args, **kwargs):
        result = original_compare(*args, **kwargs)
        ready.set()
        assert release.wait(20)
        return result
    monkeypatch.setattr(candidates, "ingest", ingest)
    monkeypatch.setattr(candidates, "similar_resumes", compare)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(lambda: asyncio.run(ingest_resume(
            deps, None, text=LONG, domain="genai", evaluate=False, org_id=None)))
        try:
            assert ready.wait(20)
            assert getattr(CandidateStore(factory), f"delete_{parent}")(getattr(saved[0], f"{parent}_id"))
        finally:
            release.set()
        with pytest.raises(IngestRefused) as exc:
            pending.result(timeout=20)
        assert exc.value.reason == f"{parent}_erased"
    assert candidates.get_candidate("b") is not None
