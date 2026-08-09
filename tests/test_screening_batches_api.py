"""S8.4 Phase B: the screening surface over HTTP."""

from __future__ import annotations

import base64
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
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
