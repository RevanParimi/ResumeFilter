"""Approved D2a input/log boundaries; ownership and TTL are separate work."""

import base64
import csv
import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.candidates.models import CandidateRow
from app.candidates.normalize.skills import clear_curated_overlay, norm_key
from app.main import create_app
from app.services.github import GitHubRepoRaw, GitHubUserRaw
from tests.conftest import ADMIN_HEADERS, FakeGitHub, make_services
from tests.curation_helpers import saved_source


def teardown_function():
    clear_curated_overlay()


def export(names):
    csv_text = io.StringIO(newline="")
    writer = csv.writer(csv_text)
    writer.writerow(["Name"])
    writer.writerows([name] for name in names)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("Skills.csv", csv_text.getvalue())
    return buf.getvalue()


def candidate(services):
    with services.candidates._session_factory() as session:
        row = CandidateRow(full_name="Synthetic contributor")
        session.add(row)
        session.commit()
        return row.id


@pytest.mark.parametrize("raw", [
    "COBOL" + "!" * 5008,
    "COBOL" + "!" * 124,
    " " * 124 + "COBOL",
    "COBOL" + "\t", "\nCOBOL", "CO\x00BOL", "CO\x7fBOL", "CO\x85BOL",
], ids=["punctuation-5013", "punctuation-129", "padding-129", "tab", "newline", "nul", "del", "c1-control"])
def test_raw_guard_prevents_persistence_before_normalization(services, raw):
    assert 2 <= len(norm_key(raw)) <= 64  # old key-only guard accepts each case
    services.curation.record_unmapped(raw, source_id=saved_source(services.candidates._session_factory)[1])
    assert services.curation.list_unmapped().terms == []


def test_rejected_variant_cannot_overwrite_an_existing_term(services):
    services.curation.record_unmapped("COBOL", source_id=saved_source(services.candidates._session_factory)[1])
    before = services.curation.list_unmapped().terms
    services.curation.record_unmapped("COBOL" + "!" * 5000, source_id=saved_source(services.candidates._session_factory)[1])
    assert services.curation.list_unmapped().terms == before


@pytest.mark.parametrize("raw", ["COBOL" + "!" * 123, "測量" + "。" * 126, "𐐀𐐁" + "!" * 126])
def test_exact_limit_counts_unicode_code_points_and_preserves_raw_form(services, raw):
    assert len(raw) == 128
    services.curation.record_unmapped(raw, source_id=saved_source(services.candidates._session_factory)[1])
    term, = services.curation.list_unmapped().terms
    assert term.display_name == raw
    assert term.norm_key == norm_key(raw)


@pytest.mark.parametrize("kind", ["github", "linkedin"])
async def test_adapters_skip_bad_raw_variants_without_losing_valid_terms(settings, kind):
    names = [" " * 124 + "COBOL", "COBOL\t", "COBOL", "cobol", "COBOL",
             "SyntheticNovel" + "!" * 5000, "測量", "𐐀𐐁", "Python"]
    gh = FakeGitHub(user_signals={"dev": GitHubUserRaw(
        login="dev", available=True,
        repos=[GitHubRepoRaw(name="demo", languages={name: 100 for name in names})],
    )})
    services = make_services(settings, github=gh)
    cid = candidate(services)
    if kind == "github":
        signal = await services.profile_sources.ingest_github(cid, handle="dev")
    else:
        signal = await services.profile_sources.ingest_linkedin(cid, export(names))
    assert any(s.name == "SyntheticNovel" + "!" * 5000 for s in signal.skills)
    assert services.profile_sources.list_sources(cid) == [signal]
    terms = {t.norm_key: t for t in services.curation.list_unmapped().terms}
    assert set(terms) == {"cobol", "測量", "𐐨𐐩"}
    assert terms["cobol"].occurrences == (2 if kind == "github" else 1)
    assert terms["cobol"].display_name in {"COBOL", "cobol"}


@pytest.mark.parametrize("kind", ["github", "linkedin"])
async def test_capture_failure_is_observable_without_rendering_private_text(settings, log_output, monkeypatch, kind):
    sentinel = "SyntheticPrivateSkill"
    gh = FakeGitHub(user_signals={"dev": GitHubUserRaw(
        login="dev", available=True,
        repos=[GitHubRepoRaw(name="demo", languages={sentinel: 100})],
    )})
    services = make_services(settings, github=gh)
    cid = candidate(services)

    def fail(*args, **kwargs):
        raise IntegrityError("INSERT_PRIVATE_STATEMENT", {"name": sentinel}, RuntimeError("PRIVATE_ERROR"))

    monkeypatch.setattr(services.curation._store, "record_observation", fail)
    if kind == "github":
        signal = await services.profile_sources.ingest_github(cid, handle="dev")
    else:
        signal = await services.profile_sources.ingest_linkedin(cid, export([sentinel]))
    assert services.profile_sources.list_sources(cid) == [signal]
    assert "unmapped_skill_capture_failed" in log_output.text
    assert '"source_type":' in log_output.text
    for private in (sentinel, "INSERT_PRIVATE_STATEMENT", "PRIVATE_ERROR", "Traceback"):
        assert private not in log_output.text


def test_linkedin_api_uses_original_cell_and_keeps_admin_boundary(services):
    cid = candidate(services)
    raw_names = [" " * 124 + "PaddingSkill", "\tControlSkill", "LongSkill" + "!" * 5000,
                 "COBOL" + "!" * 123, "測量", "Python"]
    with TestClient(create_app(services)) as client:
        assert client.get("/curation/skills/unmapped").status_code == 401
        response = client.post(f"/candidates/{cid}/sources/linkedin", headers=ADMIN_HEADERS,
                               json={"export_b64": base64.b64encode(export(raw_names)).decode()})
        assert response.status_code == 200
        assert any(s["name"] == "PaddingSkill" for s in response.json()["skills"])
        queued = client.get("/curation/skills/unmapped", headers=ADMIN_HEADERS)
        assert queued.status_code == 200
        assert {t["norm_key"] for t in queued.json()["terms"]} == {"cobol", "測量"}
        assert client.get(f"/candidates/{cid}/sources", headers=ADMIN_HEADERS).status_code == 200
