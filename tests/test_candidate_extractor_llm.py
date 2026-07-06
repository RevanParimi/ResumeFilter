"""LLM extraction path (S1.1): scripted FakeLLM, fallback on abstain/garbage."""

import json
from pathlib import Path

import pytest

from app.candidates.extractor import extract_profile
from app.services.llm import NullLLM
from tests.conftest import FakeLLM

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def full_resume() -> str:
    return (FIXTURES / "full_profile_resume.txt").read_text(encoding="utf-8")


def _llm_payload() -> str:
    return json.dumps(
        {
            "full_name": {
                "value": "Arjun Mehta",
                "confidence": 0.97,
                "source_excerpt": "Arjun Mehta",
            },
            "headline": None,
            "contact": {
                "email": {
                    "value": "arjun.mehta@example.com",
                    "confidence": 0.99,
                    "source_excerpt": "arjun.mehta@example.com",
                },
                "phone": {
                    "value": "+91 98765 43210",
                    "confidence": 0.95,
                    "source_excerpt": "+91 98765 43210",
                },
                "location": {
                    "value": "Bengaluru, Karnataka",
                    "confidence": 0.9,
                    "source_excerpt": "Bengaluru, Karnataka",
                },
            },
            "education": [
                {
                    "degree": "B.Tech",
                    "field_of_study": "Computer Science",
                    "institution": "NIT Trichy",
                    "grade_value": 8.6,
                    "grade_scale": "cgpa_10",
                    "start": "2014",
                    "end": "2018",
                    "is_current": False,
                    "confidence": 0.92,
                    "source_excerpt": "B.Tech in Computer Science, NIT Trichy",
                }
            ],
            "experience": [
                {
                    "employer": "Flipkart",
                    "title": "Senior Data Engineer",
                    "seniority": "senior",
                    "employment_type": "full_time",
                    "start": "2021-06",
                    "end": None,
                    "is_current": True,
                    "confidence": 1.7,
                    "source_excerpt": "Senior Data Engineer, Flipkart",
                }
            ],
            "skills": [{"name": "Kafka", "confidence": 0.9, "source_excerpt": "Kafka"}],
            "projects": [],
            "certifications": [],
            "links": [{"type": "github", "url": "https://github.com/arjun-mehta"}],
        }
    )


async def test_llm_path_parses_profile_and_locates_spans(settings, full_resume):
    llm = FakeLLM({"RESUME:": _llm_payload()}, settings=settings)
    result = await extract_profile(full_resume, llm=llm, settings=settings)
    assert result.method == "llm"
    p = result.profile
    assert p.full_name is not None and p.full_name.value == "Arjun Mehta"
    # source_excerpt was re-located to a real character span:
    assert p.full_name.span is not None
    s = p.full_name.span
    assert full_resume[s.start : s.end] == "Arjun Mehta"
    edu_span = p.education[0].span
    assert edu_span is not None
    assert full_resume[edu_span.start : edu_span.end] == edu_span.text
    assert p.contact.location is not None
    assert p.experience[0].dates.is_current is True
    assert p.links[0].type == "github"


async def test_llm_confidence_is_clamped_to_unit_interval(settings, full_resume):
    llm = FakeLLM({"RESUME:": _llm_payload()}, settings=settings)
    result = await extract_profile(full_resume, llm=llm, settings=settings)
    assert result.profile.experience[0].confidence == 1.0  # 1.7 clamped


async def test_llm_path_computes_contact_hashes(settings, full_resume):
    llm = FakeLLM({"RESUME:": _llm_payload()}, settings=settings)
    result = await extract_profile(full_resume, llm=llm, settings=settings)
    assert result.profile.contact.email_hash is not None
    assert result.profile.contact.phone_hash is not None


async def test_null_llm_falls_back_to_heuristic(settings, full_resume):
    result = await extract_profile(full_resume, llm=NullLLM(settings), settings=settings)
    assert result.method == "heuristic"
    assert result.profile.contact.email is not None
    assert result.profile.contact.email_hash is not None


async def test_garbage_llm_output_falls_back_to_heuristic(settings, full_resume):
    llm = FakeLLM({"RESUME:": "sorry, I cannot help with that"}, settings=settings)
    result = await extract_profile(full_resume, llm=llm, settings=settings)
    assert result.method == "heuristic"
    assert len(result.profile.experience) == 2


async def test_llm_exception_degrades_with_warning(settings, full_resume):
    class BoomLLM(NullLLM):
        async def _araw(self, *, model, system, prompt, max_tokens):
            raise RuntimeError("provider down")

    result = await extract_profile(full_resume, llm=BoomLLM(settings), settings=settings)
    assert result.method == "heuristic"
    assert any("provider down" in w for w in result.warnings)
