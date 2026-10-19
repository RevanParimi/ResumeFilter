"""S4.3 talent-search HTTP surface — offline TestClient over injected stores."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.candidates.extractor import extract_profile
from app.features import default_view
from app.features.materialize import MaterializedVector
from app.features.schema import FeatureVector
from app.ledger.schema import ConsentPurpose
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
                             view_version=default_view(settings=services.settings).version, values=values,
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


@pytest.mark.parametrize("denial", ["revoked", "expired", "wrong_purpose", "future"])
def test_historical_search_uses_current_candidate_consent(api, denial):
    client, services = api
    now = datetime.now(timezone.utc)
    org_a = services.ledger.create_organization("Consent A")
    org_b = services.ledger.create_organization("Consent B")
    denied = asyncio.run(_seed(services, "denied", {
        "candidate.years_experience": 8.0, "reputation.score": 0.99,
        "ledger.interview_record_count": 999,
    }))
    allowed = asyncio.run(_seed(services, "allowed", {
        "candidate.years_experience": 2.0, "reputation.score": 0.2,
        "ledger.interview_record_count": 10,
    }))
    grant = services.ledger.grant_consent(
        candidate_id=denied, org_id=org_a.id,
        purpose=ConsentPurpose.VERIFICATION_READ if denial == "wrong_purpose" else ConsentPurpose.LEDGER_READ,
        now=now + timedelta(days=1) if denial == "future" else _AS_OF,
        expires_at=now if denial == "expired" else now + timedelta(days=7),
    )
    if denial == "revoked":
        services.ledger.revoke_consent(grant.id, now=now)
    services.ledger.grant_consent(
        candidate_id=allowed, org_id=org_b.id, purpose=ConsentPurpose.LEDGER_READ,
        now=_AS_OF, expires_at=now + timedelta(days=7),
    )
    terms = [{"feature": name, "weight": 1.0} for name in
             ("candidate.years_experience", "reputation.score", "ledger.interview_record_count")]
    response = _search(client, as_of=_AS_OF.isoformat(), ranking={"terms": terms})
    assert response.status_code == 200, response.text
    rows = {r["candidate_id"]: r for r in response.json()["ranked"]}
    assert rows[denied]["score"] == pytest.approx(8.0 / 60.0)
    assert rows[denied]["coverage"] == pytest.approx(1.0 / 3.0)
    assert [c["feature"] for c in rows[denied]["contributions"]] == ["candidate.years_experience"]
    assert set(rows[denied]["missing"]) == {"reputation.score", "ledger.interview_record_count"}
    # The withheld 999 must not enter the allowed candidate's min/max pool.
    ledger_term = next(c for c in rows[allowed]["contributions"]
                       if c["feature"] == "ledger.interview_record_count")
    assert ledger_term["raw"] == 10 and ledger_term["normalized"] == 0.5
    for op, value, expected in [("exists", None, [allowed]), ("gte", 0.1, [allowed]),
                                ("missing", None, [denied]), ("ne", 0.0, [allowed])]:
        filtered = _search(client, as_of=_AS_OF.isoformat(), ranking={"terms": terms},
                           filters=[{"feature": "reputation.score", "op": op, "value": value}])
        assert filtered.status_code == 200, filtered.text
        assert [r["candidate_id"] for r in filtered.json()["ranked"]] == expected
    stored = services.features.get_vector(denied, view_name="core_v1",
        view_version=default_view(settings=services.settings).version, as_of=_AS_OF)
    assert stored.consent_state["allowed"] is True
    assert stored.vector.values["reputation.score"] == 0.99


def test_search_consent_read_failure_does_not_return_cached_ranking(api, monkeypatch):
    client, services = api
    asyncio.run(_seed(services, "cached", {"reputation.score": 0.9}))
    def unavailable(_):
        raise RuntimeError("synthetic consent storage failure")
    monkeypatch.setattr(services.ledger, "consents_for_candidate", unavailable)
    response = _search(client, ranking={"terms": [{"feature": "reputation.score", "weight": 1}]})
    assert response.status_code == 500
    assert "ranked" not in response.text and "synthetic consent storage failure" not in response.text
