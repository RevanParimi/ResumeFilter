"""Bind unfinished screening retry capability to report erasure.

Existing references remain unlinked: historical report ownership is not inferred.
"""

from alembic import op
import sqlalchemy as sa

revision = "0025_screening_input_report"
down_revision = "0024_screening_retry_input"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("screening_item_inputs") as batch:
        batch.add_column(sa.Column("report_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_screening_input_report", "reports",
                                 ["report_id"], ["id"], ondelete="CASCADE")
        batch.create_index("ix_screening_item_inputs_report_id", ["report_id"])


def downgrade() -> None:
    with op.batch_alter_table("screening_item_inputs") as batch:
        batch.drop_index("ix_screening_item_inputs_report_id")
        batch.drop_constraint("fk_screening_input_report", type_="foreignkey")
        batch.drop_column("report_id")
