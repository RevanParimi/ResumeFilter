import csv
import io
import zipfile

from app.core.config import Settings
from app.profile_sources.linkedin import parse_linkedin_export


def _settings(**kw):
    return Settings(_env_file=None, openrouter_api_key="", **kw)


def _zip(files: dict[str, str]) -> bytes:
    """Build an in-memory zip from {archive_name: csv_text}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


SKILLS = "Name\nPython\nDjango\nLeadership\n"
POSITIONS = (
    "Company Name,Title,Description,Started On,Finished On\n"
    "Infosys,Python Developer,Built Django APIs,Jan 2020,Dec 2021\n"
    "TCS,Engineer,Kubernetes work,Jan 2022,\n"
)
EDUCATION = "School Name,Degree Name,Start Date,End Date\nIIT Madras,B.Tech,2016,2020\n"
PROFILE = "First Name,Last Name,Headline,Industry\nAsha,K,Senior Python Engineer,Information Technology\n"


def test_parses_all_sections():
    raw = parse_linkedin_export(
        _zip({"Skills.csv": SKILLS, "Positions.csv": POSITIONS,
              "Education.csv": EDUCATION, "Profile.csv": PROFILE}),
        _settings(),
    )
    assert raw.available is True
    assert raw.skills == ["Python", "Django", "Leadership"]
    assert [p.company for p in raw.positions] == ["Infosys", "TCS"]
    assert raw.positions[1].finished_on == ""   # current role
    assert raw.education[0].school == "IIT Madras"
    assert raw.headline == "Senior Python Engineer"
    assert raw.industry == "Information Technology"


def test_tolerates_column_name_variants():
    positions = "Company,Title\nWipro,SDE\n"
    education = "School,Degree\nBITS Pilani,M.Tech\n"
    raw = parse_linkedin_export(_zip({"Positions.csv": positions, "Education.csv": education}), _settings())
    assert raw.positions[0].company == "Wipro"
    assert raw.education[0].school == "BITS Pilani"


def test_nested_directory_members_resolved():
    raw = parse_linkedin_export(_zip({"Basic_LinkedInDataExport/Skills.csv": SKILLS}), _settings())
    assert raw.available is True
    assert raw.skills == ["Python", "Django", "Leadership"]


def test_missing_optional_files_are_fine():
    raw = parse_linkedin_export(_zip({"Skills.csv": SKILLS}), _settings())
    assert raw.available is True
    assert raw.positions == [] and raw.education == []


def test_non_zip_is_unavailable():
    raw = parse_linkedin_export(b"this is not a zip", _settings())
    assert raw.available is False
    assert raw.warnings


def test_zip_without_linkedin_csvs_is_unavailable():
    raw = parse_linkedin_export(_zip({"Ad_Targeting.csv": "Member Age\n25\n"}), _settings())
    assert raw.available is False
    assert any("no linkedin" in w.lower() for w in raw.warnings)


def test_row_cap_enforced():
    many = "Name\n" + "".join(f"skill{i}\n" for i in range(50))
    raw = parse_linkedin_export(_zip({"Skills.csv": many}), _settings(ps_linkedin_max_rows=10))
    assert len(raw.skills) == 10
