"""org reliability weight: organizations.reliability_weight (S3.4)

Revision ID: 0006_org_reliability_weight
Revises: 0005_coding_round_results
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa

revision = "0006_org_reliability_weight"
down_revision = "0005_coding_round_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("reliability_weight", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("reliability_weight")
