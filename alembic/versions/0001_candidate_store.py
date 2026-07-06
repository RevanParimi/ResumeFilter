"""candidate store: candidates, resumes, extractions

Revision ID: 0001_candidate_store
Revises:
Create Date: 2026-07-06

"""
from alembic import op
import sqlalchemy as sa

revision = "0001_candidate_store"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email_hash", sa.String(64), nullable=True),
        sa.Column("phone_hash", sa.String(64), nullable=True),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_candidates_email_hash", "candidates", ["email_hash"])
    op.create_index("ix_candidates_phone_hash", "candidates", ["phone_hash"])

    op.create_table(
        "resumes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("candidate_id", "version", name="uq_resumes_candidate_version"),
    )
    op.create_index("ix_resumes_candidate_id", "resumes", ["candidate_id"])
    op.create_index("ix_resumes_text_sha256", "resumes", ["text_sha256"])

    op.create_table(
        "extractions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "resume_id",
            sa.String(36),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_extractions_resume_id", "extractions", ["resume_id"])
    op.create_index("ix_extractions_candidate_id", "extractions", ["candidate_id"])


def downgrade() -> None:
    op.drop_table("extractions")
    op.drop_table("resumes")
    op.drop_table("candidates")
