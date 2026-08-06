"""S8.4 Phase A: the ONE redaction. Similarity and count survive; identity
does not. Both org-facing readers call this same function."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.fabrication import (
    DuplicationBand, ResumeFarmAssessment, ResumeMatch,
)
from app.schemas.report import Report
from app.screening.projection import redact_for_org


def _report_with_matches() -> Report:
    return Report(
        id="rep-1",
        domain="genai",
        created_at=datetime.now(timezone.utc),
        resume_farm=ResumeFarmAssessment(
            score=0.82,
            confidence=0.7,
            band=DuplicationBand.NEAR_DUPLICATE,
            corpus_size=1200,
            reasoning="two near-duplicates in the corpus",
            matches=[
                ResumeMatch(candidate_id="cand-x", resume_id="res-x", similarity=0.82),
                ResumeMatch(candidate_id="cand-y", resume_id="res-y", similarity=0.61),
            ],
        ),
    )


def test_identity_is_stripped_from_every_match():
    out = redact_for_org(_report_with_matches())
    assert [m.candidate_id for m in out.resume_farm.matches] == [None, None]
    assert [m.resume_id for m in out.resume_farm.matches] == [None, None]


def test_similarity_count_and_the_rest_of_the_signal_survive():
    out = redact_for_org(_report_with_matches())
    assert [m.similarity for m in out.resume_farm.matches] == [0.82, 0.61]
    assert len(out.resume_farm.matches) == 2
    assert out.resume_farm.score == 0.82
    assert out.resume_farm.band == DuplicationBand.NEAR_DUPLICATE
    assert out.resume_farm.corpus_size == 1200
    assert out.resume_farm.reasoning == "two near-duplicates in the corpus"


def test_the_rest_of_the_report_is_untouched():
    """The org sees the FULL report -- verdicts, missing_signals, probes."""
    source = _report_with_matches()
    out = redact_for_org(source)
    assert out.id == source.id
    assert out.verdicts == source.verdicts
    assert out.depth_score == source.depth_score
    assert out.fabrication_risk == source.fabrication_risk


def test_the_input_report_is_not_mutated():
    source = _report_with_matches()
    redact_for_org(source)
    assert source.resume_farm.matches[0].candidate_id == "cand-x", (
        "redaction must not corrupt the admin-plane object it was handed"
    )


def test_a_report_with_no_matches_is_returned_unharmed():
    r = Report(id="rep-2", domain="genai", created_at=datetime.now(timezone.utc))
    out = redact_for_org(r)
    assert out.resume_farm.matches == []


def test_admin_plane_still_gets_identity(services, farm_resume_a, farm_resume_b, admin_headers):
    """Widening ResumeMatch to Optional must not silently empty the admin view."""
    from contextlib import contextmanager
    from fastapi.testclient import TestClient
    from app.main import create_app

    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=admin_headers) as c:
        c.post("/candidates", json={"resume_text": farm_resume_a, "domain": "genai"})
        second = c.post("/candidates",
                        json={"resume_text": farm_resume_b, "domain": "genai"})
        matches = second.json()["resume_farm"]["matches"]
        assert matches, "fixture pair must produce a near-duplicate match"
        assert all(m["candidate_id"] is not None for m in matches)
        assert all(m["resume_id"] is not None for m in matches)
