"""skill curation: unmapped-term review queue (S6.3)

Revision ID: 0011_skill_curation
Revises: 0010_profile_sources
Create Date: 2026-07-30

Candidate-agnostic taxonomy-gap queue: NO candidate FK (survives candidate
erasure by design). Surrogate id PK + unique index on norm_key (the upsert key).
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_skill_curation"
down_revision = "0010_profile_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unmapped_terms",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("norm_key", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("source_types", sa.JSON(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=True),
        sa.Column("canonical", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_unmapped_terms_norm_key", "unmapped_terms", ["norm_key"], unique=True)
    op.create_index("ix_unmapped_terms_status", "unmapped_terms", ["status"])


def downgrade() -> None:
    op.drop_index("ix_unmapped_terms_status", table_name="unmapped_terms")
    op.drop_index("ix_unmapped_terms_norm_key", table_name="unmapped_terms")
    op.drop_table("unmapped_terms")
