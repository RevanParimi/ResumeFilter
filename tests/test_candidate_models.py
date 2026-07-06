"""ORM table shapes: UUID PKs, FK cascades, version uniqueness, JSON round-trip."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.candidates.models import CandidateRow, ExtractionRow, ResumeRow
from app.core.db import Base, make_engine, make_session_factory


@pytest.fixture
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_tables_registered_on_shared_base():
    assert {"candidates", "resumes", "extractions"} <= set(Base.metadata.tables)


def test_candidate_gets_uuid_id_and_timestamps(session_factory):
    with session_factory() as s:
        cand = CandidateRow(full_name="Asha Rao")
        s.add(cand)
        s.commit()
        assert len(cand.id) == 36
        assert cand.created_at is not None
        assert cand.updated_at is not None


def test_resume_version_unique_per_candidate(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.flush()
        s.add(ResumeRow(candidate_id=cand.id, version=1, raw_text="a", text_sha256="x" * 64))
        s.add(ResumeRow(candidate_id=cand.id, version=1, raw_text="b", text_sha256="y" * 64))
        with pytest.raises(IntegrityError):
            s.commit()


def test_extraction_profile_json_round_trips(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.flush()
        resume = ResumeRow(candidate_id=cand.id, version=1, raw_text="r", text_sha256="z" * 64)
        s.add(resume)
        s.flush()
        s.add(
            ExtractionRow(
                resume_id=resume.id,
                candidate_id=cand.id,
                method="heuristic",
                profile={"id": "cand_x", "skills": [{"name": "python", "confidence": 0.7}]},
            )
        )
        s.commit()
    with session_factory() as s:
        row = s.query(ExtractionRow).one()
        assert row.profile["skills"][0]["name"] == "python"
        assert row.warnings == []


def test_deleting_candidate_cascades_to_resumes_and_extractions(session_factory):
    with session_factory() as s:
        cand = CandidateRow()
        s.add(cand)
        s.flush()
        resume = ResumeRow(candidate_id=cand.id, version=1, raw_text="r", text_sha256="z" * 64)
        s.add(resume)
        s.flush()
        s.add(ExtractionRow(resume_id=resume.id, candidate_id=cand.id, method="llm", profile={}))
        s.commit()
        s.delete(cand)
        s.commit()
        assert s.query(ResumeRow).count() == 0
        assert s.query(ExtractionRow).count() == 0
