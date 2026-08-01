"""reports + outcomes folded into the main database (S8.1)

Revision ID: 0016_reports_outcomes
Revises: 0015_ai_interviews
Create Date: 2026-08-01

These two tables lived in a second, raw-sqlite3 database with no foreign key to
`candidates`. DPDP erasure across the two was a CONVENTION -- two route handlers
that each remembered to delete reports before the candidate -- and a third entry
point forgetting one line would orphan an erased person's full evaluation, with
no FK to catch it and no error to notice it.

reports.candidate_id -> candidates.id ON DELETE CASCADE makes that
unrepresentable. Nullable, because POST /evaluate produces candidate-less
reports and those were never personal data.

Schema only: existing rows are imported by scripts/migrate_reports_into_main_db.py,
because a migration must not read a filesystem path out of Settings.
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_reports_outcomes"
down_revision = "0015_ai_interviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("depth_band", sa.String(length=32), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_reports_candidate_created", "reports", ["candidate_id", "created_at"]
    )

    op.create_table(
        "outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("report_id", sa.String(length=64), nullable=False),
        sa.Column("claim_id", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_outcomes_report_id", "outcomes", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_outcomes_report_id", table_name="outcomes")
    op.drop_table("outcomes")
    op.drop_index("ix_reports_candidate_created", table_name="reports")
    op.drop_table("reports")
