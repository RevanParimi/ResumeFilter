"""Session-mode twins for the six cases where authorization means more than
identity resolution (S8.2 spec 2.5).

Most twins are unnecessary by construction: after the resolver rewrite an
existing header-key test already executes every line a cookie request executes
once the principal is established. These six do NOT fall into that category --
they reach CASCADE behaviour, consent enforcement and read-time expiry, which
the resolver suites never touch.

Clocks: rather than mocking `now`, these age the stored row. That exercises the
real read-time evaluation on a real database, and it cannot rot into the
pinned-NOW time bomb that detonated mid-session during S8.1.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.auth.models import AuthSessionRow
from app.ledger.schema import ConsentPurpose
from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services

RESUME = "Priya Sharma\npriya@example.in\nEXPERIENCE\n- ML Engineer, Acme (2021-)\n"


@pytest.fixture
def capture_path(tmp_path):
    return tmp_path / "mail.jsonl"


@pytest.fixture
def cfg(settings, capture_path):
    return settings.model_copy(update={
        "email_provider": "capture",
        "email_capture_path": str(capture_path),
        "session_cookie_secure": False,
        "session_cookie_samesite": "lax",
    })


@pytest.fixture
def services(cfg, flywheel):
    return make_services(cfg, flywheel=flywheel)


@pytest.fixture
def client(services):
    with TestClient(create_app(services), raise_server_exceptions=False) as c:
        yield c


def _code(capture_path) -> str:
    line = json.loads(capture_path.read_text(encoding="utf-8").splitlines()[-1])
    return re.search(r"\b(\d{6})\b", line["body"]).group(1)


def _candidate_session(client, capture_path, email="a@b.in") -> str:
    client.post("/auth/candidate/signup", json={"email": email})
    r = client.post(
        "/auth/candidate/verify", json={"email": email, "code": _code(capture_path)}
    )
    assert r.status_code == 200
    return r.json()["csrf_token"]


def _org_session(client, capture_path, email="ops@acme.in", name="Acme") -> str:
    client.post(
        "/auth/org/signup", json={"email": email, "organization_name": name}
    )
    r = client.post(
        "/auth/org/verify", json={"email": email, "code": _code(capture_path)}
    )
    assert r.status_code == 200
    return r.json()["csrf_token"]


def _age_session(services, *, session_id: str, **shift) -> None:
    """Move a stored session's timestamps into the past.

    Nothing writes a status -- expiry and idleness are computed at READ time
    (the S7.1 effective_status precedent) -- so shifting the row is exactly how
    a real lapse looks to the resolver.
    """
    with services.candidates._session_factory() as s:
        row = s.get(AuthSessionRow, session_id)
        delta = timedelta(**shift)
        row.expires_at = row.expires_at - delta
        row.last_seen_at = row.last_seen_at - delta
        row.issued_at = row.issued_at - delta
        s.commit()


def _current_session_id(client) -> str:
    return client.get("/auth/me").json()["session_id"]


# ── 1. cross-candidate isolation, by session ────────────────────────────────


def test_twin_a_session_cannot_read_another_candidate(
    client, capture_path, services
):
    """Candidate B's SESSION must not reach candidate A. Structural: the handler
    resolves the id from the credential, never from a path param -- but that has
    to remain true for the cookie path too."""
    _candidate_session(client, capture_path, "one@example.in")
    mine = client.get("/portal/me").json()["candidate_id"]

    with TestClient(create_app(services), raise_server_exceptions=False) as other:
        _candidate_session(other, capture_path, "two@example.in")
        theirs = other.get("/portal/me").json()["candidate_id"]
        # There is no route that takes another candidate's id on this plane --
        # that IS the isolation. What the other session sees is only itself.
        assert theirs != mine
        assert other.get("/portal/me").json()["candidate_id"] == theirs


def test_twin_a_candidate_session_cannot_reach_the_admin_plane(
    client, capture_path
):
    # /domains, not /candidates: the latter has no GET, so FastAPI answers 405
    # before auth runs and the test would pass without proving anything.
    _candidate_session(client, capture_path)
    assert client.get("/domains").status_code == 401


def test_twin_a_candidate_session_cannot_reach_the_org_plane(client, capture_path):
    _candidate_session(client, capture_path)
    assert client.get("/dashboard/overview").status_code == 401


# ── 2. consent-gated org read, by session ───────────────────────────────────


def test_twin_consent_is_enforced_identically_for_a_session(
    client, capture_path, services
):
    """An org SESSION is refused a consent-gated read exactly as an org KEY is.

    Sessions change how a principal is ESTABLISHED and nothing about what it may
    do (PI-8 4.7). This is that sentence, tested.
    """
    # An org-uploaded candidate exists.
    with TestClient(create_app(services), raise_server_exceptions=False) as admin:
        created = admin.post(
            "/candidates", json={"resume_text": RESUME}, headers=ADMIN_HEADERS
        )
        assert created.status_code == 200
        candidate_id = created.json()["candidate_id"]

    csrf = _org_session(client, capture_path)
    denied = client.get(f"/ledger/candidates/{candidate_id}/records")
    assert denied.status_code == 403      # no ledger_read grant

    # Grant it, then the SAME session is allowed.
    org_id = client.get("/auth/me").json()["organization_id"]
    with TestClient(create_app(services), raise_server_exceptions=False) as admin:
        assert admin.post(
            f"/ledger/candidates/{candidate_id}/consent",
            json={"purpose": ConsentPurpose.LEDGER_READ.value, "org_id": org_id},
            headers=ADMIN_HEADERS,
        ).status_code == 200

    assert client.get(
        f"/ledger/candidates/{candidate_id}/records"
    ).status_code == 200


# ── 3. revocation ───────────────────────────────────────────────────────────


def test_twin_a_revoked_session_is_refused_on_a_consent_gated_route(
    client, capture_path
):
    csrf = _org_session(client, capture_path)
    assert client.get("/dashboard/overview").status_code == 200
    client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    assert client.get("/dashboard/overview").status_code == 401


# ── 4. erasure ──────────────────────────────────────────────────────────────


def test_twin_an_erased_candidates_session_dies_with_them(
    client, capture_path, services
):
    csrf = _candidate_session(client, capture_path, "gone@example.in")
    session_id = _current_session_id(client)

    client.delete("/portal/me", headers={"X-CSRF-Token": csrf})

    assert client.get("/portal/me").status_code == 401
    # Structural, not incidental: the row itself is gone via CASCADE.
    with services.candidates._session_factory() as s:
        assert s.get(AuthSessionRow, session_id) is None


# ── 5. absolute expiry ──────────────────────────────────────────────────────


def test_twin_an_absolutely_expired_session_is_refused(
    client, capture_path, services
):
    _candidate_session(client, capture_path)
    session_id = _current_session_id(client)
    assert client.get("/portal/me").status_code == 200

    _age_session(services, session_id=session_id, hours=13)   # ttl is 720 min
    assert client.get("/portal/me").status_code == 401


# ── 6. idle timeout ─────────────────────────────────────────────────────────


def test_twin_an_idle_timed_out_session_is_refused(client, capture_path, services):
    """Distinct from absolute expiry: this session is still inside its TTL and
    is refused purely for having gone quiet."""
    _candidate_session(client, capture_path)
    session_id = _current_session_id(client)

    with services.candidates._session_factory() as s:
        row = s.get(AuthSessionRow, session_id)
        row.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=121)
        expires = row.expires_at
        s.commit()
    # Still well inside its absolute TTL -- so a pass here would prove the idle
    # rule never fired, rather than proving the session was simply old.
    assert expires.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)

    assert client.get("/portal/me").status_code == 401
