"""S1.4 end-to-end: extractor lifts location/notice, extract_profile
normalizes both paths, API exposes normalized fields. Fully offline."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.candidates.extractor import extract_profile, heuristic_profile
from app.main import create_app
from app.services.llm import NullLLM
from tests.conftest import FakeLLM, make_services

FIXTURES = Path(__file__).parent / "fixtures"

_BASE = (FIXTURES / "full_profile_resume.txt").read_text(encoding="utf-8")
# Notice period sits in the resume header, where candidates actually put it —
# appending at the tail would land it inside the CERTIFICATIONS section.
RESUME = _BASE.replace("\n\nEXPERIENCE", "\nNotice Period: 30 days\n\nEXPERIENCE", 1)


def test_heuristic_lifts_location_with_span():
    profile = heuristic_profile(RESUME)
    loc = profile.contact.location
    assert loc is not None and loc.value == "Bengaluru"
    assert RESUME[loc.span.start : loc.span.end] == "Bengaluru"


def test_heuristic_lifts_notice_period_with_span():
    profile = heuristic_profile(RESUME)
    notice = profile.notice_period
    assert notice is not None and "30 days" in notice.value
    assert RESUME[notice.span.start : notice.span.end] == notice.value


async def test_extract_profile_normalizes_offline(settings):
    result = await extract_profile(RESUME, llm=NullLLM(settings), settings=settings)
    assert result.method == "heuristic"
    p = result.profile
    canon = {s.canonical for s in p.skills}
    assert {"python", "sql", "apache_spark", "kafka", "airflow", "aws"} <= canon
    edu = p.education[0]
    assert edu.degree_canonical == "btech" and edu.degree_level == "bachelor"
    assert edu.grade_cgpa_10 == 8.6
    assert edu.institution_canonical == "NIT Trichy"
    assert edu.institution_tier == "tier_2"
    assert {e.employer_canonical for e in p.experience} == {"Flipkart", "Infosys"}
    assert p.contact.location_city == "Bengaluru"
    assert p.contact.location_tier == "metro"
    assert p.notice_period_days == 30


async def test_llm_path_notice_period_normalized(settings):
    payload = json.dumps(
        {
            "full_name": {"value": "Arjun Mehta", "confidence": 0.9,
                          "source_excerpt": "Arjun Mehta"},
            "headline": None,
            "contact": {
                "email": {"value": "arjun.mehta@example.com", "confidence": 0.9,
                          "source_excerpt": "arjun.mehta@example.com"},
                "phone": None,
                "location": {"value": "Bengaluru, Karnataka", "confidence": 0.9,
                             "source_excerpt": "Bengaluru, Karnataka"},
            },
            "notice_period": {"value": "30 days", "confidence": 0.9,
                              "source_excerpt": "Notice Period: 30 days"},
            "education": [],
            "experience": [],
            "skills": [{"name": "PySpark", "confidence": 0.9, "source_excerpt": "Spark"}],
            "projects": [],
            "certifications": [],
            "links": [],
        }
    )
    llm = FakeLLM({"RESUME:": payload}, settings=settings)
    result = await extract_profile(RESUME, llm=llm, settings=settings)
    assert result.method == "llm"
    p = result.profile
    assert p.notice_period is not None and p.notice_period.value == "30 days"
    assert p.notice_period_days == 30  # bare-value form parsed
    assert p.contact.location_city == "Bengaluru"
    assert p.skills[0].canonical == "apache_spark"


def test_api_exposes_normalized_profile(settings, flywheel):
    services = make_services(settings, flywheel=flywheel)
    app = create_app(services)
    with TestClient(app, raise_server_exceptions=False) as client:
        cid = client.post(
            "/candidates", json={"resume_text": RESUME, "evaluate": False}
        ).json()["candidate_id"]
        detail = client.get(f"/candidates/{cid}").json()
    lp = detail["latest_profile"]
    assert lp["contact"]["location_city"] == "Bengaluru"
    assert lp["notice_period_days"] == 30
    assert lp["education"][0]["institution_canonical"] == "NIT Trichy"
    canon = {s["canonical"] for s in lp["skills"]}
    assert {"python", "apache_spark"} <= canon
