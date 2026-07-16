"""S1.4 schema growth + normalize_profile orchestration (pure, offline)."""

from app.candidates.normalize import normalize_profile
from app.candidates.schema import (
    CandidateProfile,
    ContactInfo,
    EducationEntry,
    ExperienceEntry,
    ExtractedStr,
    SkillItem,
)


def test_legacy_profile_payload_still_validates():
    """Pre-S1.4 extractions (stored JSON) must load with the new fields None."""
    legacy = {
        "id": "cand_legacy1",
        "skills": [{"name": "Python", "confidence": 0.7}],
        "education": [{"degree": "B.Tech", "grade_value": 8.0, "grade_scale": "cgpa_10"}],
        "experience": [{"employer": "Infosys"}],
    }
    p = CandidateProfile.model_validate(legacy)
    assert p.skills[0].canonical is None
    assert p.education[0].grade_cgpa_10 is None
    assert p.experience[0].employer_canonical is None
    assert p.notice_period is None and p.notice_period_days is None


def test_skills_enriched():
    p = CandidateProfile(skills=[SkillItem(name="PySpark"), SkillItem(name="K8s")])
    normalize_profile(p)
    assert [(s.canonical, s.category) for s in p.skills] == [
        ("apache_spark", "data"),
        ("kubernetes", "devops"),
    ]


def test_education_enriched():
    p = CandidateProfile(
        education=[
            EducationEntry(
                degree="B.Tech",
                institution="National Institute of Technology, Tiruchirappalli",
                grade_value=8.6,
                grade_scale="cgpa_10",
            )
        ]
    )
    normalize_profile(p)
    edu = p.education[0]
    assert edu.degree_canonical == "btech" and edu.degree_level == "bachelor"
    assert edu.grade_cgpa_10 == 8.6
    assert edu.institution_canonical == "NIT Trichy"
    assert edu.institution_tier == "tier_2"
    # Claims stay verbatim:
    assert edu.degree == "B.Tech"
    assert edu.institution == "National Institute of Technology, Tiruchirappalli"


def test_experience_employer_enriched():
    p = CandidateProfile(
        experience=[
            ExperienceEntry(employer="Infosys Ltd"),
            ExperienceEntry(employer="Chai Point"),
        ]
    )
    normalize_profile(p)
    assert p.experience[0].employer_canonical == "Infosys"
    assert p.experience[1].employer_canonical is None
    assert p.experience[1].employer == "Chai Point"


def test_location_and_notice_enriched():
    p = CandidateProfile(
        contact=ContactInfo(location=ExtractedStr(value="Bangalore, Karnataka")),
        notice_period=ExtractedStr(value="Notice Period: 30 days"),
    )
    normalize_profile(p)
    assert p.contact.location_city == "Bengaluru"
    assert p.contact.location_tier == "metro"
    assert p.notice_period_days == 30


def test_normalize_returns_the_same_object():
    p = CandidateProfile()
    assert normalize_profile(p) is p
