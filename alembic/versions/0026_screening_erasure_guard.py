"""Pause unresolved/historical screening input after erasure, without deleting it."""

from alembic import op
import sqlalchemy as sa

from app.screening.erasure_schema import install, uninstall

revision = "0026_screening_erasure_guard"
down_revision = "0025_screening_input_report"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("screening_erasure_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_screening_erasure_singleton"))
    op.add_column("batch_items", sa.Column("input_generation", sa.BigInteger(), nullable=True))
    # No guess about which report preceded a historical interruption. Keep
    # both raw data and references, but end old leases and automatic recovery.
    op.execute(sa.text("""
        UPDATE batch_items SET status = 'failed', error = 'fresh_upload_required', claimed_at = NULL
        WHERE status != 'done' AND (raw_text != '' OR EXISTS (
            SELECT 1 FROM screening_item_inputs i
            WHERE i.id = batch_items.id AND i.report_id IS NULL))
    """))
    install(op.get_bind())


def downgrade():
    conn = op.get_bind()
    # Old code can retry any retained raw text. Refuse the downgrade if it
    # would restore quarantined input; never silently discard that input.
    unsafe = conn.scalar(sa.text("""
        SELECT count(*) FROM batch_items b WHERE b.status != 'done' AND (
            (b.error = 'fresh_upload_required' AND (b.raw_text != '' OR EXISTS (
                SELECT 1 FROM screening_item_inputs i WHERE i.id = b.id))) OR
            (b.raw_text != '' AND (b.input_generation IS NULL OR b.input_generation != (
                SELECT generation FROM screening_erasure_state WHERE id = 1))))
    """))
    if unsafe:
        raise RuntimeError("screening_input_requires_review_before_downgrade")
    uninstall(conn)
    # Native DROP COLUMN avoids rebuilding the parent table (which would
    # cascade-delete private references with SQLite foreign keys enabled).
    op.drop_column("batch_items", "input_generation")
    op.drop_table("screening_erasure_state")
