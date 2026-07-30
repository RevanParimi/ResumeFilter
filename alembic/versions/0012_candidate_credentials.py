"""candidate credentials: first-party auth for the DPDP portal (S6.4)

Revision ID: 0012_candidate_credentials
Revises: 0011_skill_curation
Create Date: 2026-07-30

One credential per candidate (unique candidate_id); CASCADE on candidate erasure.
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_candidate_credentials"
down_revision = "0011_skill_curation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_credentials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id", sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("access_key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_candidate_credentials_candidate_id",
        "candidate_credentials", ["candidate_id"], unique=True,
    )
    op.create_index(
        "ix_candidate_credentials_access_key_hash",
        "candidate_credentials", ["access_key_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_candidate_credentials_access_key_hash", table_name="candidate_credentials")
    op.drop_index("ix_candidate_credentials_candidate_id", table_name="candidate_credentials")
    op.drop_table("candidate_credentials")
