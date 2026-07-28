"""profile sources: GitHub-as-signal ingestion (S6.1)

Revision ID: 0010_profile_sources
Revises: 0009_observed_offers
Create Date: 2026-07-28

"""
from alembic import op
import sqlalchemy as sa

revision = "0010_profile_sources"
down_revision = "0009_observed_offers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id", sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("signal", sa.JSON(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_profile_sources_candidate_id", "profile_sources", ["candidate_id"])
    op.create_index("ix_profile_sources_source_type", "profile_sources", ["source_type"])


def downgrade() -> None:
    op.drop_index("ix_profile_sources_source_type", table_name="profile_sources")
    op.drop_index("ix_profile_sources_candidate_id", table_name="profile_sources")
    op.drop_table("profile_sources")
