"""resume fingerprints for farm detection (S2.3)

Revision ID: 0002_resume_fingerprints
Revises: 0001_candidate_store
Create Date: 2026-07-17

"""
from alembic import op
import sqlalchemy as sa

revision = "0002_resume_fingerprints"
down_revision = "0001_candidate_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_fingerprints",
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
        sa.Column("algo", sa.String(32), nullable=False),
        sa.Column("signature", sa.JSON(), nullable=False),
        sa.Column("shingle_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("resume_id", "algo", name="uq_fingerprints_resume_algo"),
    )
    op.create_index("ix_resume_fingerprints_resume_id", "resume_fingerprints", ["resume_id"])
    op.create_index(
        "ix_resume_fingerprints_candidate_id", "resume_fingerprints", ["candidate_id"]
    )
    op.create_index("ix_resume_fingerprints_algo", "resume_fingerprints", ["algo"])


def downgrade() -> None:
    op.drop_table("resume_fingerprints")
