"""coding-round results: coding_round_results table (S3.3)

Revision ID: 0005_coding_round_results
Revises: 0004_org_api_keys
Create Date: 2026-07-25

"""
from alembic import op
import sqlalchemy as sa

revision = "0005_coding_round_results"
down_revision = "0004_org_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coding_round_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id", sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "candidate_id", sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "consent_id", sa.String(36),
            sa.ForeignKey("consent_grants.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("platform_name", sa.Text(), nullable=True),
        sa.Column("assessment_name", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("max_score", sa.Float(), nullable=True),
        sa.Column("percentile", sa.Float(), nullable=True),
        sa.Column("problem_tags", sa.JSON(), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_coding_round_results_org_id", "coding_round_results", ["org_id"]
    )
    op.create_index(
        "ix_coding_round_results_candidate_id", "coding_round_results", ["candidate_id"]
    )
    op.create_index(
        "ix_coding_round_results_consent_id", "coding_round_results", ["consent_id"]
    )


def downgrade() -> None:
    op.drop_table("coding_round_results")
