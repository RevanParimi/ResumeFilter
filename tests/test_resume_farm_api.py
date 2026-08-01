"""Farm detection over the API: cross-candidate matches, self-exclusion,
evaluate=False visibility. Offline: NullLLM => heuristic extraction."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services


@pytest.fixture
def api(settings, flywheel):
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False, headers=ADMIN_HEADERS) as client:
        yield client, services


def _post(client, text, **extra):
    resp = client.post("/candidates", json={"resume_text": text, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_first_upload_is_unique(api, farm_resume_a):
    client, _ = api
    body = _post(client, farm_resume_a)
    farm = body["resume_farm"]
    assert farm is not None
    assert farm["band"] == "unique"
    assert farm["corpus_size"] == 0
    assert farm["advisory"] is True
    assert body["report"]["resume_farm"]["band"] == "unique"


def test_identity_swapped_copy_flags_near_duplicate(api, farm_resume_a, farm_resume_b):
    client, _ = api
    first = _post(client, farm_resume_a)
    second = _post(client, farm_resume_b)
    assert second["candidate_id"] != first["candidate_id"]
    farm = second["resume_farm"]
    assert farm["band"] == "near_duplicate"
    assert farm["matches"][0]["candidate_id"] == first["candidate_id"]
    assert farm["matches"][0]["similarity"] >= 0.85
    # The advisory note reached the report summary.
    assert "Resume-farm signals" in second["report"]["summary"]
    assert "never a rejection signal" in second["report"]["summary"]


def test_own_reupload_never_self_matches(api, farm_resume_a):
    client, _ = api
    first = _post(client, farm_resume_a)
    again = _post(client, farm_resume_a)  # same contact -> same candidate, dedup
    assert again["candidate_id"] == first["candidate_id"]
    assert again["duplicate_resume"] is True
    assert again["resume_farm"]["band"] == "unique"


def test_new_version_of_own_resume_never_self_matches(api, farm_resume_a):
    client, _ = api
    first = _post(client, farm_resume_a)
    v2 = _post(client, farm_resume_a + "\nCERTIFICATIONS\n\nAWS Solutions Architect Associate\n")
    assert v2["candidate_id"] == first["candidate_id"]
    assert v2["resume_version"] == 2
    assert v2["resume_farm"]["band"] == "unique"


def test_bulk_import_still_sees_the_signal(api, farm_resume_a, farm_resume_b):
    client, _ = api
    _post(client, farm_resume_a, evaluate=False)
    second = _post(client, farm_resume_b, evaluate=False)
    assert second["report"] is None
    assert second["resume_farm"]["band"] == "near_duplicate"


def test_genuine_resume_stays_unique_next_to_the_farm(api, farm_resume_a, genuine_resume):
    client, _ = api
    _post(client, farm_resume_a)
    body = _post(client, genuine_resume)
    assert body["resume_farm"]["band"] == "unique"


def test_short_resume_is_insufficient_data(api):
    client, _ = api
    body = _post(client, "Asha Rao\nEmail: asha@example.com\nSKILLS\nPython")
    assert body["resume_farm"]["band"] == "insufficient_data"


def test_post_evaluate_has_no_farm_assessment(api, farm_resume_a):
    client, _ = api
    _post(client, farm_resume_a)
    rep = client.post("/evaluate", json={"resume_text": farm_resume_a}).json()
    assert rep["resume_farm"] is None  # no identity to exclude -> not assessed
