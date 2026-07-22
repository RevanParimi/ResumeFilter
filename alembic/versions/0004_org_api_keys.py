"""org API keys: organizations.api_key_hash + unique index (S3.2)

Revision ID: 0004_org_api_keys
Revises: 0003_evaluation_ledger
Create Date: 2026-07-22

"""
from alembic import op
import sqlalchemy as sa

revision = "0004_org_api_keys"
down_revision = "0003_evaluation_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("api_key_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "uq_organizations_api_key_hash", "organizations", ["api_key_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_organizations_api_key_hash", table_name="organizations")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("api_key_hash")
