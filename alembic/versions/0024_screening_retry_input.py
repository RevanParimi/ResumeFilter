"""Private screening retry references, bound to resume erasure.

Existing unlinked input is left intact; ownership cannot be inferred safely.
"""

from alembic import op
import sqlalchemy as sa

revision = "0024_screening_retry_input"
down_revision = "0023_correction_pins_the_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "screening_item_inputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("resume_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["batch_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_screening_item_inputs_resume_id", "screening_item_inputs", ["resume_id"])


def downgrade() -> None:
    # Old code reads retry input from batch_items. Restore only surviving
    # references, never erased/swept input or a completed item's payload.
    op.execute(sa.text("""
        UPDATE batch_items SET
            raw_text = (SELECT r.raw_text FROM screening_item_inputs i
                        JOIN resumes r ON r.id = i.resume_id WHERE i.id = batch_items.id),
            text_sha256 = (SELECT r.text_sha256 FROM screening_item_inputs i
                           JOIN resumes r ON r.id = i.resume_id WHERE i.id = batch_items.id)
        WHERE status != 'done' AND raw_text = '' AND EXISTS
            (SELECT 1 FROM screening_item_inputs i JOIN resumes r ON r.id = i.resume_id
             WHERE i.id = batch_items.id)
    """))
    op.drop_index("ix_screening_item_inputs_resume_id", table_name="screening_item_inputs")
    op.drop_table("screening_item_inputs")
