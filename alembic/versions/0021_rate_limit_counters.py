"""rate limit counters: a bound that survives a redeploy (S8.3 Phase A)

Revision ID: 0021_rate_limit_counters
Revises: 0020_outcome_authorship
Create Date: 2026-08-10

The counters live in the database rather than in process memory, and that is
this sprint's load-bearing choice. An in-process limiter resets on every
container start and is per-worker -- both are silent failures of the exact
surface a limiter exists for (OTP brute force), and both pass every unit test.

NO foreign keys, deliberately: the login path writes a counter BEFORE any
principal exists, so there is no subject to reference. The unique constraint is
the important object here -- it is what makes a lost INSERT race a catchable
IntegrityError rather than a second row nobody counts.

`window_start` is BigInteger epoch seconds, not a timestamp: it is compared
only for exact equality, and an integer carries no timezone semantics for two
dialects to disagree about. `expires_at` IS a timestamp, because Phase B's
retention sweep reads it the way it reads every other retention column.
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_rate_limit_counters"
down_revision = "0020_outcome_authorship"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("bucket_key", sa.String(length=128), nullable=False),
        sa.Column("window_start", sa.BigInteger(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "bucket_key", "window_start", name="uq_rate_limit_counters_key_window"
        ),
    )
    op.create_index(
        "ix_rate_limit_counters_bucket_key", "rate_limit_counters", ["bucket_key"]
    )
    op.create_index(
        "ix_rate_limit_counters_expires_at", "rate_limit_counters", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_counters_expires_at", table_name="rate_limit_counters")
    op.drop_index("ix_rate_limit_counters_bucket_key", table_name="rate_limit_counters")
    op.drop_table("rate_limit_counters")
