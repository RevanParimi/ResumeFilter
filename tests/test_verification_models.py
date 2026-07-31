"""S7.1 ORM: CASCADE from the candidate, and no column can hold an artifact."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.candidates.models import CandidateRow
from app.core.db import Base, make_engine, make_session_factory
from app.verification.models import VerificationChallengeRow, VerificationRow

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _candidate(session, cid="c1"):
    session.add(CandidateRow(id=cid, full_name="A Candidate"))
    session.commit()
    return cid


def test_tables_exist_with_the_expected_names():
    assert VerificationRow.__tablename__ == "verifications"
    assert VerificationChallengeRow.__tablename__ == "verification_challenges"


def test_verification_row_has_no_column_able_to_hold_a_document():
    cols = set(VerificationRow.__table__.columns.keys())
    assert "evidence_digest" in cols
    for banned in ("document", "image", "raw", "artifact", "biometric", "file", "payload"):
        assert banned not in cols


def test_erasing_the_candidate_cascades_verifications_and_challenges():
    factory = _factory()
    with factory() as s:
        _candidate(s)
        v = VerificationRow(
            id="v1", candidate_id="c1", method="otp_email",
            assurance_level=2, status="pending", requested_at=NOW,
        )
        s.add(v)
        s.commit()
        s.add(
            VerificationChallengeRow(
                id="ch1", verification_id="v1", code_hash="d" * 64, channel="email",
                destination_hash="e" * 64, attempts=0, max_attempts=5,
                expires_at=NOW + timedelta(minutes=10), last_sent_at=NOW,
            )
        )
        s.commit()

        s.delete(s.get(CandidateRow, "c1"))
        s.commit()

        assert s.execute(select(VerificationRow)).scalars().all() == []
        assert s.execute(select(VerificationChallengeRow)).scalars().all() == []


def test_deleting_a_verification_cascades_its_challenges():
    factory = _factory()
    with factory() as s:
        _candidate(s)
        s.add(
            VerificationRow(
                id="v1", candidate_id="c1", method="otp_email",
                assurance_level=2, status="pending", requested_at=NOW,
            )
        )
        s.commit()
        s.add(
            VerificationChallengeRow(
                id="ch1", verification_id="v1", code_hash="d" * 64, channel="email",
                destination_hash="e" * 64, attempts=0, max_attempts=5,
                expires_at=NOW + timedelta(minutes=10), last_sent_at=NOW,
            )
        )
        s.commit()

        s.delete(s.get(VerificationRow, "v1"))
        s.commit()
        assert s.execute(select(VerificationChallengeRow)).scalars().all() == []
