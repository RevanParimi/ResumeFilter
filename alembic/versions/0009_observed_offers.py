"""observed offers: consent-gated comp capture for comp intelligence (S5.2)

Revision ID: 0009_observed_offers
Revises: 0008_job_requisitions
Create Date: 2026-07-28

"""
from alembic import op
import sqlalchemy as sa

revision = "0009_observed_offers"
down_revision = "0008_job_requisitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observed_offers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id", sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "candidate_id", sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "consent_id", sa.String(length=36),
            sa.ForeignKey("consent_grants.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("role_family", sa.String(length=32), nullable=False),
        sa.Column("seniority", sa.String(length=16), nullable=False),
        sa.Column("city_tier", sa.String(length=16), nullable=False),
        sa.Column("ctc_fixed", sa.Float(), nullable=False),
        sa.Column("ctc_variable", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_observed_offers_candidate_id", "observed_offers", ["candidate_id"])
    op.create_index(
        "ix_observed_offers_role_signal", "observed_offers",
        ["role_family", "seniority", "city_tier"],
    )


def downgrade() -> None:
    op.drop_index("ix_observed_offers_role_signal", table_name="observed_offers")
    op.drop_index("ix_observed_offers_candidate_id", table_name="observed_offers")
    op.drop_table("observed_offers")
