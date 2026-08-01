"""Structural DPDP: no column here can hold audio. The single audio field is a
sha256 digest, so a future adapter cannot persist a voice sample without a
migration a reviewer would see -- the S7.1/S7.2 posture, unchanged."""

from sqlalchemy import String, Text

from app.interview.models import InterviewSessionRow, InterviewTurnRow


def _cols(model):
    return {c.name: c for c in model.__table__.columns}


def test_table_names():
    assert InterviewSessionRow.__tablename__ == "interview_sessions"
    assert InterviewTurnRow.__tablename__ == "interview_turns"


def test_sessions_cascade_from_candidates():
    fk = next(iter(_cols(InterviewSessionRow)["candidate_id"].foreign_keys))
    assert fk.column.table.name == "candidates"
    assert fk.ondelete == "CASCADE"


def test_turns_cascade_from_sessions():
    fk = next(iter(_cols(InterviewTurnRow)["session_id"].foreign_keys))
    assert fk.column.table.name == "interview_sessions"
    assert fk.ondelete == "CASCADE"


def test_the_audio_field_is_a_digest_not_a_blob():
    audio = _cols(InterviewTurnRow)["audio_digest"]
    assert isinstance(audio.type, String)
    assert audio.type.length == 64          # sha256 hex, and nothing larger fits


def test_no_column_on_either_table_can_hold_audio():
    """The transcript is TEXT by design (spec section 0.1). Nothing else is: a
    reviewer scanning for "where could bytes live" must find one answer."""
    for model in (InterviewSessionRow, InterviewTurnRow):
        for name, col in _cols(model).items():
            if isinstance(col.type, Text):
                assert name == "transcript", (
                    f"{model.__tablename__}.{name} is unbounded TEXT; only the "
                    "transcript may be, and audio never may"
                )
            type_name = type(col.type).__name__.casefold()
            assert "blob" not in type_name
            assert "binary" not in type_name


def test_report_id_is_a_loose_reference_not_a_foreign_key():
    """Still deliberately loose. Until S8.1 an FK was not EXPRESSIBLE (reports
    lived in a second database); now it would be, and the reason is different:
    adding it needs a batch_alter_table on a live table plus a decision about
    what a deleted report should do to a finished interview. Deferred, not
    forgotten -- S8.1 spec follow-ups."""
    assert not _cols(InterviewSessionRow)["report_id"].foreign_keys


def test_status_and_candidate_are_indexed_for_the_reads_we_actually_do():
    cols = _cols(InterviewSessionRow)
    assert cols["candidate_id"].index is True
    assert cols["status"].index is True
    assert _cols(InterviewTurnRow)["session_id"].index is True


def test_assessment_and_scorer_version_are_stored_on_the_session():
    cols = _cols(InterviewSessionRow)
    assert "assessment" in cols and cols["assessment"].nullable is True
    assert cols["scorer_version"].type.length == 16
    assert cols["assurance_level_at_start"].nullable is False
