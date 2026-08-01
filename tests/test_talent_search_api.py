"""S4.3 talent-search HTTP surface — offline TestClient over injected stores."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.candidates.extractor import extract_profile
from app.features.materialize import MaterializedVector
from app.features.schema import FeatureVector
from app.main import create_app
from tests.conftest import ADMIN_HEADERS, make_services

_AS_OF = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _seed(services, tag, values):
    # Distinct email per tag => distinct candidates (no phone: identical phones
    # would merge via identity resolution). Feature values are set explicitly
    # below, so extraction quality is irrelevant — ingest only creates the FK row.
    text = (f"{tag} Kumar\nEmail: {tag}@example.com\n"
            "EXPERIENCE\n- Engineer, Acme (2020 - Present)\nSKILLS\nPython\n")
    result = await extract_profile(text, llm=services.llm, settings=services.settings)
    cid = services.candidates.ingest(result, text).candidate_id
    services.features.upsert_vector(MaterializedVector(
        vector=FeatureVector(candidate_id=cid, as_of=_AS_OF, view_name="core_v1",
                             view_version=1, values=values,
                             missing=tuple(k for k, v in values.items() if v is None)),
        consent_state={"allowed": True}, materialized_at=_AS_OF))
    return cid


@pytest.fixture
def api(settings, flywheel):
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False, headers=ADMIN_HEADERS) as client:
        yield client, services


def _search(client, **body):
    return client.post("/talent/search", json=body)


def test_ranks_desc_and_is_advisory(api):
    client, services = api
    ids = {}
    for tag, yrs in (("aaa", 2.0), ("bbb", 8.0), ("ccc", 5.0)):
        ids[tag] = asyncio.run(_seed(services, tag, {"candidate.years_experience": yrs}))
    resp = _search(client, ranking={"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["advisory"] is True and body["pool_size"] == 3 and body["filtered_size"] == 3
    order = [r["candidate_id"] for r in body["ranked"]]
    assert order == [ids["bbb"], ids["ccc"], ids["aaa"]]
    assert body["ranked"][0]["contributions"][0]["feature"] == "candidate.years_experience"


def test_filter_narrows_pool(api):
    client, services = api
    for tag, yrs in (("aaa", 2.0), ("bbb", 8.0), ("ccc", 5.0)):
        asyncio.run(_seed(services, tag, {"candidate.years_experience": yrs}))
    resp = _search(
        client,
        filters=[{"feature": "candidate.years_experience", "op": "gte", "value": 5}],
        ranking={"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]},
    )
    body = resp.json()
    assert body["pool_size"] == 3 and body["filtered_size"] == 2


def test_limit_is_honored(api):
    client, services = api
    for tag, yrs in (("aaa", 2.0), ("bbb", 8.0)):
        asyncio.run(_seed(services, tag, {"candidate.years_experience": yrs}))
    resp = _search(client, limit=1, ranking={"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]})
    assert len(resp.json()["ranked"]) == 1


def test_unknown_feature_is_400(api):
    client, _ = api
    resp = _search(client, ranking={"terms": [{"feature": "nope.bad", "weight": 1.0}]})
    assert resp.status_code == 400


def test_empty_ranking_is_422(api):
    client, _ = api
    assert _search(client, ranking={"terms": []}).status_code == 422


def test_malformed_filter_value_is_400_not_500(api):
    client, services = api
    asyncio.run(_seed(services, "aaa", {"candidate.years_experience": 8.0}))
    # a numeric feature compared against a non-numeric string is a client error
    resp = _search(
        client,
        filters=[{"feature": "candidate.years_experience", "op": "gt", "value": "five"}],
        ranking={"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]},
    )
    assert resp.status_code == 400


def test_empty_pool_when_nothing_materialized_is_200_advisory(api):
    client, _ = api
    resp = _search(client, ranking={"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]})
    body = resp.json()
    assert resp.status_code == 200 and body["advisory"] is True
    assert body["pool_size"] == 0 and body["ranked"] == []


def test_requires_admin_key(settings, flywheel):
    locked = settings.model_copy(update={"api_auth_key": SecretStr("s3cret")})
    services = make_services(locked, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        body = {"ranking": {"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]}}
        assert client.post("/talent/search", json=body).status_code == 401
        assert client.post("/talent/search", json=body, headers={"X-API-Key": "s3cret"}).status_code == 200


def test_as_of_selects_the_cut(api):
    client, services = api
    # one candidate materialized only at _AS_OF; a query at a different cut sees an empty pool
    asyncio.run(_seed(services, "aaa", {"candidate.years_experience": 8.0}))
    other = datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat()
    resp = _search(client, as_of=other, ranking={"terms": [{"feature": "candidate.years_experience", "weight": 1.0}]})
    assert resp.json()["pool_size"] == 0
