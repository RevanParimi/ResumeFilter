"""job requisitions: org-owned demand-side matching table (S5.1)

Revision ID: 0008_job_requisitions
Revises: 0007_ml_feature_vectors
Create Date: 2026-07-27

"""
from alembic import op
import sqlalchemy as sa

revision = "0008_job_requisitions"
down_revision = "0007_ml_feature_vectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_requisitions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id", sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("must_have_skills", sa.JSON(), nullable=False),
        sa.Column("nice_to_have_skills", sa.JSON(), nullable=False),
        sa.Column("min_years_experience", sa.Float(), nullable=True),
        sa.Column("min_degree_level", sa.String(length=16), nullable=True),
        sa.Column("max_notice_days", sa.Integer(), nullable=True),
        sa.Column("location_tiers", sa.JSON(), nullable=True),
        sa.Column("remote", sa.Boolean(), nullable=False),
        sa.Column("min_skill_coverage", sa.Float(), nullable=True),
        sa.Column("comp_band", sa.JSON(), nullable=True),
        sa.Column("weights", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_requisitions_org_id", "job_requisitions", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_job_requisitions_org_id", table_name="job_requisitions")
    op.drop_table("job_requisitions")
