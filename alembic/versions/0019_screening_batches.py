"""screening batches + items (S8.4 Phase B)

Revision ID: 0019_screening_batches
Revises: 0018_upload_ownership
Create Date: 2026-08-07

An organisation can now upload ONE resume and read its report (Phase A). This
adds the surface the product is actually sold on: drop in the resumes you have,
watch them process, read a ranked list of who needs a human.

Both tables are new, so there is no batch_alter_table here -- SQLite creates
them with their foreign keys in place.

The ondelete choices are not uniform and the asymmetry is deliberate:
screening_batches.org_id CASCADEs (a batch is the ORG's work product), while
the three subject pointers on batch_items SET NULL (a candidate's erasure must
not rewrite the org's record of what it screened).
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_screening_batches"
down_revision = "0018_upload_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "screening_batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("created_by_org_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"],
            name="fk_screening_batches_org_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_org_user_id"], ["org_users.id"],
            name="fk_screening_batches_created_by", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_screening_batches_org_id", "screening_batches", ["org_id"])
    op.create_index(
        "ix_screening_batches_org_created", "screening_batches", ["org_id", "created_at"]
    )

    op.create_table(
        "batch_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column("resume_id", sa.String(length=36), nullable=True),
        sa.Column("report_id", sa.String(length=64), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["screening_batches.id"],
            name="fk_batch_items_batch_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"],
            name="fk_batch_items_candidate_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resume_id"], ["resumes.id"],
            name="fk_batch_items_resume_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"], ["reports.id"],
            name="fk_batch_items_report_id", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_batch_items_batch_id", "batch_items", ["batch_id"])
    op.create_index("ix_batch_items_text_sha256", "batch_items", ["text_sha256"])
    op.create_index("ix_batch_items_batch_status", "batch_items", ["batch_id", "status"])
    op.create_index("ix_batch_items_batch_risk", "batch_items", ["batch_id", "risk_score"])


def downgrade() -> None:
    op.drop_index("ix_batch_items_batch_risk", table_name="batch_items")
    op.drop_index("ix_batch_items_batch_status", table_name="batch_items")
    op.drop_index("ix_batch_items_text_sha256", table_name="batch_items")
    op.drop_index("ix_batch_items_batch_id", table_name="batch_items")
    op.drop_table("batch_items")

    op.drop_index("ix_screening_batches_org_created", table_name="screening_batches")
    op.drop_index("ix_screening_batches_org_id", table_name="screening_batches")
    op.drop_table("screening_batches")
