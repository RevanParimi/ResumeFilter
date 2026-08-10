"""S8.3 Phase A: in-place retry.

SCREENING.md §7 has been admitting since S8.4 Phase B that batch_items.raw_text
is "kept on failure -- for a retry path that DOES NOT EXIST YET". This is that
path, and it is what justifies retaining the text at all.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from app.screening.models import BatchItemRow
from app.screening.schema import ItemStatus
from tests.conftest import ADMIN_HEADERS


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def _key(services, name="Agency A"):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def _register(c, key, texts, name="Q3"):
    return c.post("/screening/batches", headers={"X-Org-Key": key},
                  json={"name": name, "domain": "genai",
                        "items": [{"resume_text": t} for t in texts]})


def _items(services):
    with services.candidates._session_factory() as session:
        return session.query(BatchItemRow).order_by(BatchItemRow.created_at).all()


def _fail_item(services, item_id: str, *, error="internal_error", clear_text=False):
    with services.candidates._session_factory() as session:
        row = session.get(BatchItemRow, item_id)
        row.status = ItemStatus.FAILED.value
        row.error = error
        if clear_text:
            row.raw_text = ""
        session.commit()


def test_a_failed_item_is_requeued_and_becomes_claimable(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        item_id = _items(services)[0].id
        _fail_item(services, item_id)

        resp = c.post(f"/screening/batches/{bid}/retry", headers={"X-Org-Key": key})
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"batch_id": bid, "requeued": 1, "skipped": 0}

    with services.candidates._session_factory() as session:
        row = session.get(BatchItemRow, item_id)
        assert row.status == ItemStatus.PENDING.value
        assert row.error is None
        assert row.claimed_at is None
        assert row.processed_at is None


def test_an_item_with_no_text_is_SKIPPED_not_requeued(services, genuine_resume):
    """Either the text was cleared on success or the failure was empty_resume.
    Re-queueing it would report requeued:1 and then fail identically -- a
    promise the next process call breaks."""
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        item_id = _items(services)[0].id
        _fail_item(services, item_id, error="empty_resume", clear_text=True)

        body = c.post(f"/screening/batches/{bid}/retry",
                      headers={"X-Org-Key": key}).json()
    assert body == {"batch_id": bid, "requeued": 0, "skipped": 1}
    with services.candidates._session_factory() as session:
        assert session.get(BatchItemRow, item_id).status == ItemStatus.FAILED.value


def test_done_and_pending_items_are_untouched(services, genuine_resume):
    """Retry means 'try the failures again', not 'run everything again'. A
    finished item has had its text cleared and is not re-runnable at all."""
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume, genuine_resume]).json()["id"]
        rows = _items(services)
        done_id, pending_id = rows[0].id, rows[1].id
        with services.candidates._session_factory() as session:
            row = session.get(BatchItemRow, done_id)
            row.status = ItemStatus.DONE.value
            row.raw_text = ""
            session.commit()

        body = c.post(f"/screening/batches/{bid}/retry",
                      headers={"X-Org-Key": key}).json()

    assert body["requeued"] == 0 and body["skipped"] == 0
    with services.candidates._session_factory() as session:
        assert session.get(BatchItemRow, done_id).status == ItemStatus.DONE.value
        assert session.get(BatchItemRow, pending_id).status == ItemStatus.PENDING.value


def test_another_org_gets_404_never_403(services, genuine_resume):
    """403 confirms the batch exists to anyone guessing ids. The same rule S8.5
    asserted on both outcome verbs, and the two answers must be
    byte-identical."""
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        bid = _register(c, key_a, [genuine_resume]).json()["id"]
        theirs = c.post(f"/screening/batches/{bid}/retry",
                        headers={"X-Org-Key": key_b})
        unknown = c.post(
            "/screening/batches/00000000-0000-0000-0000-000000000000/retry",
            headers={"X-Org-Key": key_b},
        )
    assert theirs.status_code == unknown.status_code == 404
    assert theirs.json() == unknown.json()


def test_a_requeued_item_is_actually_picked_up_by_process(services, genuine_resume):
    """The point of the whole task: retry re-queues, and the EXISTING process
    door does the work. There is no second processing path."""
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        item_id = _items(services)[0].id
        _fail_item(services, item_id)
        c.post(f"/screening/batches/{bid}/retry", headers={"X-Org-Key": key})
        result = c.post(f"/screening/batches/{bid}/process",
                        headers={"X-Org-Key": key}).json()
    assert result["processed"] + result["failed"] == 1


def test_retrying_a_batch_with_nothing_failed_is_a_no_op(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        body = c.post(f"/screening/batches/{bid}/retry",
                      headers={"X-Org-Key": key}).json()
    assert body == {"batch_id": bid, "requeued": 0, "skipped": 0}
