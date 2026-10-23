"""Screening batches api regressions, grouped by behavior."""

from __future__ import annotations

import base64
import asyncio
from contextlib import contextmanager
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from tests.conftest import ADMIN_HEADERS
from app.screening.models import BatchItemRow
from app.screening.schema import ItemStatus
from tests.test_screening_service import _PausedEngine


# Screening batches api

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


def test_register_then_process_then_read_the_queue(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        created = _register(c, key, [genuine_resume])
        assert created.status_code == 200, created.text
        bid = created.json()["id"]
        assert created.json()["counts"]["pending"] == 1
        assert created.json()["status"] == "pending"

        ran = c.post(f"/screening/batches/{bid}/process", headers={"X-Org-Key": key})
        assert ran.status_code == 200
        assert ran.json()["processed"] == 1 and ran.json()["remaining"] == 0

        queue = c.get(f"/screening/batches/{bid}/queue", headers={"X-Org-Key": key})
        row = queue.json()["rows"][0]
        assert row["status"] == "done" and row["reason"]
        assert row["advisory"] is True

        summary = c.get(f"/screening/batches/{bid}/summary", headers={"X-Org-Key": key})
        assert summary.status_code == 200 and summary.json()["n_screened"] == 1


@pytest.mark.asyncio
async def test_two_process_requests_share_unstarted_work_and_report_saved_counts(services, genuine_resume, monkeypatch):
    monkeypatch.setattr(services.settings, "screening_max_items_per_call", 2)
    org, key = _key(services)
    _, other_key = _key(services, "Other lease actor")
    app = create_app(services)
    slow = _PausedEngine(services)
    async with app.router.lifespan_context(app):
        app.state.engine = slow
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                    headers={"X-Org-Key": key}) as actor:
            created = await actor.post("/screening/batches", json={"name": "Two requests", "items": [
                {"resume_text": genuine_resume + f"\nSynthetic request {i}"} for i in range(3)]})
            assert created.status_code == 200
            path = "/screening/batches/" + created.json()["id"]
            pending = asyncio.create_task(actor.post(path + "/process"))
            try:
                await asyncio.wait_for(slow.entered.wait(), 10)
                current = (await actor.get(path)).json()["counts"]
                assert (current["processing"], current["pending"]) == (1, 2)
                assert (await actor.post(path + "/process", headers={"X-Org-Key": other_key})).status_code == 404
                app.state.engine = slow.real
                second = await actor.post(path + "/process")
                assert second.status_code == 200
                assert (second.json()["processed"], second.json()["failed"], second.json()["remaining"]) == (2, 0, 1)
                assert (await actor.post(path + "/retry")).json()["requeued"] == 0
            finally:
                slow.release.set()
                first = await pending
            assert first.status_code == 200
            assert (first.json()["processed"], first.json()["failed"], first.json()["remaining"]) == (1, 0, 0)
            saved = (await actor.get(path)).json()
            assert saved["counts"] == {"pending": 0, "processing": 0, "failed": 0, "done": 3}
            assert (await actor.get(path + "/summary")).json()["n_screened"] == 3
            assert (await actor.post(path + "/process")).json()["processed"] == 0


def test_an_empty_batch_is_422(services):
    _, key = _key(services)
    with _client(services) as c:
        r = c.post("/screening/batches", headers={"X-Org-Key": key},
                   json={"name": "x", "domain": "genai", "items": []})
        assert r.status_code == 422


def test_an_oversize_batch_is_422(services):
    _, key = _key(services)
    cap = services.settings.screening_max_batch_items
    with _client(services) as c:
        r = _register(c, key, ["resume"] * (cap + 1))
        assert r.status_code == 422


def test_a_corrupt_pdf_refuses_the_whole_registration_and_names_the_item(services):
    """A half-registered batch would leave the org unable to say which files
    made it in."""
    _, key = _key(services)
    with _client(services) as c:
        r = c.post("/screening/batches", headers={"X-Org-Key": key}, json={
            "name": "x", "domain": "genai",
            "items": [
                {"resume_text": "a real resume"},
                {"resume_pdf_b64": base64.b64encode(b"not a pdf").decode()},
            ],
        })
        assert r.status_code == 422
        assert "1" in str(r.json()["detail"]), "the failing item's index is named"
        assert c.get("/screening/batches", headers={"X-Org-Key": key}).json()["batches"] == []


def test_the_item_count_cap_runs_before_any_pdf_is_decoded(services):
    """The bound must cost arithmetic, not work: an over-cap batch of corrupt
    PDFs was decoded item by item and only THEN counted, so the cap protected
    nothing. The cap message -- not pdf_parse_failed -- proves the ordering."""
    _, key = _key(services)
    cap = services.settings.screening_max_batch_items
    items = [{"resume_pdf_b64": "bm90IGEgcGRm"} for _ in range(cap + 1)]
    with _client(services) as c:
        r = c.post("/screening/batches", headers={"X-Org-Key": key},
                   json={"name": "x", "domain": "genai", "items": items})
        assert r.status_code == 422
        detail = str(r.json()["detail"])
        assert "at most" in detail, detail
        assert "pdf_parse_failed" not in detail, "a PDF was decoded before the cap"


def test_a_malformed_cursor_is_422_not_500(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        for path in ("/screening/batches?cursor=!!!",
                     f"/screening/batches/{bid}/queue?cursor=!!!"):
            r = c.get(path, headers={"X-Org-Key": key})
            assert r.status_code == 422, f"{path} -> {r.status_code}"


def test_a_type_forged_cursor_is_422_not_500(services, genuine_resume):
    """A cursor that DECODES but carries the wrong types. base64+arity is not
    validation: `[1,"x"]` reached datetime.fromisoformat as an int and raised
    TypeError -- which `except (InvalidCursor, ValueError)` does not catch --
    so a hand-built cursor was a 500 on demand."""
    import base64 as b64
    import json

    def forge(values):
        raw = json.dumps(values).encode()
        return b64.urlsafe_b64encode(raw).decode().rstrip("=")

    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        cases = [
            (f"/screening/batches?cursor={forge([1, 'x'])}", "int where ISO string"),
            (f"/screening/batches?cursor={forge(['garbage', 'x'])}", "non-ISO string"),
            (f"/screening/batches?cursor={forge([None, None])}", "nulls"),
            (f"/screening/batches/{bid}/queue?cursor={forge(['x', 'y'])}",
             "string where score"),
            (f"/screening/batches/{bid}/queue?cursor={forge([[0.5], 'y'])}",
             "nested list where score"),
        ]
        for path, why in cases:
            r = c.get(path, headers={"X-Org-Key": key})
            assert r.status_code == 422, f"{why}: {path} -> {r.status_code}"


def test_the_queue_pages_with_a_cursor(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        texts = [f"{genuine_resume}\nRef {i}" for i in range(3)]
        bid = _register(c, key, texts).json()["id"]
        while c.post(f"/screening/batches/{bid}/process",
                     headers={"X-Org-Key": key}).json()["remaining"]:
            pass

        first = c.get(f"/screening/batches/{bid}/queue?limit=2",
                      headers={"X-Org-Key": key}).json()
        assert len(first["rows"]) == 2 and first["next_cursor"]
        second = c.get(
            f"/screening/batches/{bid}/queue?cursor={first['next_cursor']}",
            headers={"X-Org-Key": key},
        ).json()
        ids = [r["item_id"] for r in first["rows"] + second["rows"]]
        assert len(ids) == len(set(ids)) == 3


def test_delete_removes_the_batch(services, genuine_resume):
    _, key = _key(services)
    with _client(services) as c:
        bid = _register(c, key, [genuine_resume]).json()["id"]
        gone = c.delete(f"/screening/batches/{bid}", headers={"X-Org-Key": key})
        assert gone.status_code == 200 and gone.json()["deleted"] is True
        assert c.get(f"/screening/batches/{bid}",
                     headers={"X-Org-Key": key}).status_code == 404


def test_a_machine_caller_records_no_human_creator(services, genuine_resume):
    """X-Org-Key is an ORGANISATION credential. Inventing an actor would be a
    false audit trail."""
    _, key = _key(services)
    with _client(services) as c:
        created = _register(c, key, [genuine_resume])
        assert created.json()["created_by_org_user_id"] is None


# Screening retry

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


# Screening tenancy

def _screening_tenancy_key(services, name):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def test_every_batch_route_is_404_for_another_org_and_matches_absence(
    services, genuine_resume
):
    _, key_a = _screening_tenancy_key(services, "Agency A")
    _, key_b = _screening_tenancy_key(services, "Agency B")
    with _client(services) as c:
        bid = _register(c, key_a, [genuine_resume]).json()["id"]
        b = {"X-Org-Key": key_b}

        cases = [
            ("get", f"/screening/batches/{bid}", "/screening/batches/nope"),
            ("get", f"/screening/batches/{bid}/queue", "/screening/batches/nope/queue"),
            ("get", f"/screening/batches/{bid}/summary", "/screening/batches/nope/summary"),
            ("post", f"/screening/batches/{bid}/process", "/screening/batches/nope/process"),
            ("delete", f"/screening/batches/{bid}", "/screening/batches/nope"),
        ]
        for method, theirs, absent in cases:
            got = getattr(c, method)(theirs, headers=b)
            missing = getattr(c, method)(absent, headers=b)
            assert got.status_code == 404, f"{method} {theirs} -> {got.status_code}"
            assert got.json() == missing.json(), (
                f"{method} {theirs}: a different body from a genuinely absent "
                f"batch confirms this one exists"
            )


def test_listing_shows_only_my_own_batches(services, genuine_resume):
    _, key_a = _screening_tenancy_key(services, "Agency A")
    _, key_b = _screening_tenancy_key(services, "Agency B")
    with _client(services) as c:
        _register(c, key_a, [genuine_resume], name="A's batch")
        mine = c.get("/screening/batches", headers={"X-Org-Key": key_b}).json()
        assert mine["batches"] == []


def test_a_cursor_from_another_org_reaches_nothing(services, genuine_resume):
    """A cursor is a sort position, not a capability -- the org filter is what
    protects the boundary, so a stolen cursor buys nothing."""
    _, key_a = _screening_tenancy_key(services, "Agency A")
    _, key_b = _screening_tenancy_key(services, "Agency B")
    with _client(services) as c:
        # TWO batches, so a limit=1 page actually has a next_cursor to steal.
        _register(c, key_a, [genuine_resume], name="first")
        _register(c, key_a, [genuine_resume + "\nRef 2"], name="second")
        page = c.get("/screening/batches?limit=1", headers={"X-Org-Key": key_a}).json()
        stolen = page["next_cursor"]
        assert stolen, "two batches and limit=1 must produce a cursor"

        theirs = c.get(f"/screening/batches?cursor={stolen}",
                       headers={"X-Org-Key": key_b})
        assert theirs.status_code == 200
        assert theirs.json()["batches"] == []


def test_all_batch_routes_require_an_org_credential(services):
    with _client(services) as c:
        assert c.get("/screening/batches").status_code == 401
        assert c.post("/screening/batches", json={}).status_code == 401
        assert c.get("/screening/batches/x/queue").status_code == 401
        assert c.post("/screening/batches/x/process").status_code == 401
        assert c.delete("/screening/batches/x").status_code == 401
