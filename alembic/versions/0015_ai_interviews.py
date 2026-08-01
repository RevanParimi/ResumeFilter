"""ai interview sessions + turns (S7.3)

Revision ID: 0015_ai_interviews
Revises: 0014_verification_subject
Create Date: 2026-08-01

Two tables, both CASCADE: sessions from candidates, turns from sessions. The
existing DPDP hard-delete therefore sweeps an interview whole -- no new erasure
path exists or is needed.

Nothing here can hold audio. `transcript` is deliberately Text (the candidate's
own words, spec section 0.1); the only audio field is a sha256 digest, and
`question_text` is bounded so the transcript is the single unbounded column.
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_ai_interviews"
down_revision = "0014_verification_subject"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("assurance_level_at_start", sa.Integer(), nullable=False),
        sa.Column("planned_questions", sa.JSON(), nullable=False),
        sa.Column("assessment", sa.JSON(), nullable=True),
        sa.Column("scorer_version", sa.String(length=16), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_interview_sessions_candidate_id", "interview_sessions", ["candidate_id"]
    )
    op.create_index("ix_interview_sessions_status", "interview_sessions", ["status"])

    op.create_table(
        "interview_turns",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("question_text", sa.String(length=512), nullable=False),
        sa.Column("question_source", sa.String(length=24), nullable=False),
        sa.Column("expected_signals", sa.JSON(), nullable=False),
        sa.Column("channel", sa.String(length=8), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("audio_digest", sa.String(length=64), nullable=True),
        sa.Column("audio_duration_seconds", sa.Float(), nullable=True),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["interview_sessions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_interview_turns_session_id", "interview_turns", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_interview_turns_session_id", table_name="interview_turns")
    op.drop_table("interview_turns")
    op.drop_index("ix_interview_sessions_status", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_candidate_id", table_name="interview_sessions")
    op.drop_table("interview_sessions")
