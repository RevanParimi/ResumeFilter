"""Recorded erasure refusals must not leave input available to batch retry."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from sqlalchemy import event, select

from app.candidates.models import ResumeRow
from app.core.db import make_session_factory
from app.screening.models import BatchItemRow
from app.screening.store import ScreeningStore
from tests.test_report_erasure_concurrency import database
from tests.test_screening_batches_api import _client, _key, _register
from tests.test_screening_erasure_concurrency import NOW, assert_scrubbed, seed


@pytest.mark.parametrize("parent", ["candidate", "resume", "report"])
def test_erasure_failure_scrubs_input_and_prevents_retry(database, parent):
    _, factory = database
    org, batch, item, kwargs = seed(factory)
    store = ScreeningStore(factory)
    # Include old linked fields: a refusal must remove all retained payload.
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        row.candidate_id = kwargs["candidate_id"]
        row.resume_id = kwargs["resume_id"]
        row.report_id = kwargs["report_id"]
        row.risk_score = 0.4
        row.signals = {"risk_confidence": 0.6}
        session.commit()
    assert store.fail(item.id, lease=item.claimed_at, error=f"{parent}_erased", at=NOW)
    assert_scrubbed(factory, item.id, parent)
    assert store.requeue_failed(org, batch) == (0, 1)
    assert store.claim(org, batch, limit=1, now=NOW, timeout_seconds=900) == []


@pytest.mark.parametrize("error", ["internal_error", "unknown_domain", "candidate_erased_extra"])
def test_ordinary_failure_keeps_retry_input(database, error):
    _, factory = database
    org, batch, item, _ = seed(factory)
    store = ScreeningStore(factory)
    assert store.fail(item.id, lease=item.claimed_at, error=error, at=NOW)
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        assert row.raw_text == "private resume" and row.text_sha256
    assert store.requeue_failed(org, batch) == (1, 0)
    assert store.claim(org, batch, limit=1, now=NOW, timeout_seconds=900)[0].raw_text == "private resume"


@pytest.mark.parametrize("replacement", ["new_lease", "deleted_batch"])
def test_stale_refusal_does_not_scrub_another_claim(database, replacement):
    engine, factory = database
    org, batch, item, _ = seed(factory)
    writer_factory = make_session_factory(engine)
    ready, release = Event(), Event()

    def pause(*_):
        ready.set()
        assert release.wait(20)

    event.listen(writer_factory, "do_orm_execute", pause, once=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        writing = executor.submit(ScreeningStore(writer_factory).fail, item.id,
                                  lease=item.claimed_at, error="candidate_erased", at=NOW)
        try:
            assert ready.wait(20)
            other = ScreeningStore(factory)
            if replacement == "deleted_batch":
                assert other.delete_batch(org, batch)
            else:
                later = NOW + timedelta(seconds=901)
                claimed = other.claim(org, batch, limit=1, now=later, timeout_seconds=900)[0]
        finally:
            release.set()
        assert writing.result(timeout=20) is False
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        if replacement == "deleted_batch":
            assert row is None
        else:
            assert row.status == "processing" and row.error is None
            assert row.raw_text == "private resume" and row.text_sha256
    if replacement == "new_lease":
        assert other.fail(item.id, lease=claimed.claimed_at, error="resume_erased", at=later)
        assert_scrubbed(factory, item.id, "resume")


def test_failure_status_and_scrub_commit_together(database):
    engine, factory = database
    _, _, item, _ = seed(factory)
    writer_factory = make_session_factory(engine)

    def interrupt(*_):
        raise RuntimeError("synthetic interruption before commit")

    event.listen(writer_factory, "before_commit", interrupt, once=True)
    store = ScreeningStore(writer_factory)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        store.fail(item.id, lease=item.claimed_at, error="candidate_erased", at=NOW)
    with factory() as session:
        row = session.get(BatchItemRow, item.id)
        # No false durable failure: pre-commit crashes still need D3b2 recovery.
        assert row.status == "processing" and row.error is None
        assert row.raw_text == "private resume" and row.text_sha256
    assert store.fail(item.id, lease=item.claimed_at, error="candidate_erased", at=NOW)
    assert_scrubbed(factory, item.id, "candidate")


@pytest.mark.parametrize("stage", ["resolved", "candidate_fingerprint", "resume_fingerprint"])
def test_actual_ingest_refusal_cannot_recreate_input(services, monkeypatch, farm_resume_a, stage):
    org, key = _key(services)
    other_org, other_key = _key(services, "Other")
    headers = {"X-Org-Key": key}
    erased = []
    with _client(services) as http:
        saved = http.post("/screening/candidates", headers=headers,
                          json={"resume_text": farm_resume_a, "evaluate": False})
        assert saved.status_code == 200
        cid = saved.json()["candidate_id"]
        batch = _register(http, key, [farm_resume_a]).json()["id"]
        kept = _register(http, other_key, ["unrelated private input"]).json()["id"]
        if stage == "resolved":
            original = services.candidates._resolve_candidate

            def refuse(session, profile):
                row, matched = original(session, profile)
                assert row.id == cid
                assert services.candidates.delete_candidate(row.id)
                erased.append(row.id)
                return row, matched

            target = "_resolve_candidate"
        else:
            original = services.candidates.save_fingerprint

            def refuse(fp, *, resume_id, candidate_id):
                assert candidate_id == cid
                if stage == "candidate_fingerprint":
                    assert services.portal.erase(candidate_id)["deleted"]
                else:
                    assert services.candidates.delete_resume(resume_id)
                erased.append(candidate_id)
                return original(fp, resume_id=resume_id, candidate_id=candidate_id)

            target = "save_fingerprint"
        with monkeypatch.context() as patch:
            patch.setattr(services.candidates, target, refuse)
            path = f"/screening/batches/{batch}"
            ran = http.post(path + "/process", headers=headers)
        assert ran.status_code == 200
        assert (ran.json()["processed"], ran.json()["failed"], ran.json()["remaining"]) == (0, 1, 0)
        assert erased == [cid]
        row = http.get(path + "/queue", headers=headers).json()["rows"][0]
        parent = "resume" if stage == "resume_fingerprint" else "candidate"
        assert row["advisory"] and row["human_review_required"]
        assert_scrubbed(services.candidates._session_factory, row["item_id"], parent)
        retry = http.post(path + "/retry", headers=headers).json()
        assert (retry["requeued"], retry["skipped"]) == (0, 1)
        assert http.post(path + "/process", headers=headers).json()["processed"] == 0
        assert http.post(path + "/retry", headers={"X-Org-Key": other_key}).status_code == 404
        assert http.get(path + "/queue", headers={"X-Org-Key": other_key}).status_code == 404
        with services.candidates._session_factory() as session:
            assert list(session.scalars(select(ResumeRow))) == []
        if parent == "candidate":
            assert services.candidates.get_candidate(cid) is None
        kept_row = services.screening._store.all_items(other_org, kept, now=NOW)[0]
        assert kept_row.raw_text == "unrelated private input" and kept_row.status.value == "failed"
        assert kept_row.error == "fresh_upload_required"
