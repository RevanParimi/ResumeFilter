"""Sessions in the DPDP portal, and erasure of the state that cannot cascade
(S8.2 spec 8, 8.1).

Sessions CASCADE with the candidate row. login_challenges CANNOT -- they carry
no foreign key, because at signup time no principal exists yet. That single
exception is the only non-structural guarantee in this sprint, so it gets a
direct test at BOTH erasure entry points rather than a comment.
"""

from __future__ import annotations

import json
import random
import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth.challenges import ChallengeScope
from app.auth.schema import AuthPlane, LoginPurpose
from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


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


def _signup(client, capture_path, email="a@b.in") -> str:
    client.post("/auth/candidate/signup", json={"email": email})
    r = client.post(
        "/auth/candidate/verify", json={"email": email, "code": _code(capture_path)}
    )
    assert r.status_code == 200
    return r.json()["csrf_token"]


def _challenge(services, email, purpose=LoginPurpose.LOGIN):
    return services.auth._store.get_challenge(
        ChallengeScope(
            services.auth.hash_email(email), purpose, AuthPlane.CANDIDATE
        )
    )


# ── MyData.sessions ─────────────────────────────────────────────────────────


def test_my_data_lists_the_candidates_sessions(client, capture_path):
    _signup(client, capture_path)
    data = client.get("/portal/me").json()
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["status"] == "active"


def test_my_data_sessions_never_carry_a_token(client, capture_path):
    """A transparency view is not a place to hand back credentials."""
    _signup(client, capture_path)
    body = client.get("/portal/me").text
    assert "token" not in body.lower() or "token_hash" not in body
    for session in client.get("/portal/me").json()["sessions"]:
        assert set(session) == {
            "id", "issued_at", "expires_at", "last_seen_at", "status",
            "user_agent", "current",
        }


def test_sessions_are_scoped_to_the_caller(client, capture_path, services):
    """Another candidate's devices must not appear in this candidate's view."""
    _signup(client, capture_path, "one@example.in")
    with TestClient(create_app(services), raise_server_exceptions=False) as other:
        _signup(other, capture_path, "two@example.in")
        theirs = {s["id"] for s in other.get("/portal/me").json()["sessions"]}
    mine = {s["id"] for s in client.get("/portal/me").json()["sessions"]}
    assert mine.isdisjoint(theirs)


# ── erasure, at BOTH entry points ───────────────────────────────────────────


def test_portal_erasure_kills_sessions_and_challenges(
    client, capture_path, services
):
    csrf = _signup(client, capture_path, "erase@example.in")
    # An outstanding challenge on a DIFFERENT purpose, so it cannot have been
    # consumed by the signup above.
    services.auth.request_code(
        email="erase@example.in", plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.LOGIN, at=NOW, rng=random.Random(1),
    )
    assert _challenge(services, "erase@example.in") is not None

    assert client.delete(
        "/portal/me", headers={"X-CSRF-Token": csrf}
    ).status_code == 200

    assert client.get("/portal/me").status_code == 401        # session died
    assert _challenge(services, "erase@example.in") is None   # challenge died


def test_admin_erasure_kills_sessions_and_challenges_TOO(
    client, capture_path, services
):
    """THE POINT OF THIS TEST.

    Erasure has two entry points -- the portal and the admin plane -- and this
    repo's recurring defect is a rule applied at one and not the other. It has
    shipped in S7.1, S7.2 and S7.3. If the challenge deletion had been written
    into the portal handler, this test would fail and that is exactly why it
    exists.
    """
    _signup(client, capture_path, "victim@example.in")
    candidate_id = client.get("/portal/me").json()["candidate_id"]
    services.auth.request_code(
        email="victim@example.in", plane=AuthPlane.CANDIDATE,
        purpose=LoginPurpose.LOGIN, at=NOW, rng=random.Random(1),
    )
    assert _challenge(services, "victim@example.in") is not None

    with TestClient(create_app(services), raise_server_exceptions=False) as admin:
        assert admin.delete(
            f"/candidates/{candidate_id}", headers=ADMIN_HEADERS
        ).status_code == 200

    assert client.get("/portal/me").status_code == 401
    assert _challenge(services, "victim@example.in") is None


def test_erasure_still_reports_the_report_count(client, capture_path, services):
    """The S8.1 behaviour must survive the refactor: reports_deleted is a count
    READ taken before the cascade, not a delete this handler performs."""
    csrf = _signup(client, capture_path)
    body = client.delete("/portal/me", headers={"X-CSRF-Token": csrf}).json()
    assert body["deleted"] is True
    assert "reports_deleted" in body
