"""Retain original ingest facts on the private screening retry reference.

Historical facts stay unknown. A later retry cannot reconstruct the first
ingest's matching outcome. Downgrade drops only this new checkpoint metadata.
"""

from alembic import op
import sqlalchemy as sa

revision = "0030_screening_ingest_facts"
down_revision = "0029_candidate_login_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("screening_item_inputs", sa.Column("ingest_facts", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("screening_item_inputs", "ingest_facts")
