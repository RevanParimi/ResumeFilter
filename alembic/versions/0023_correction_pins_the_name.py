"""a reviewed correction pins full_name against the next upload (S8.3 Phase B)

Revision ID: 0023_correction_pins_the_name
Revises: 0022_data_principal_requests
Create Date: 2026-08-11

FOUND BY THE SMOKE, not by the design, and it is the difference between the
correction mechanism working and merely appearing to work.

`CandidateStore._refresh_identity` is documented "latest non-empty name wins",
so EVERY ingest overwrites `candidates.full_name` from the extractor. A subject
files a correction, an operator verifies it against an identity document and
applies it -- and the customer's very next upload for that person silently puts
the old spelling back, while `/portal/requests` goes on reporting
`applied: true`. That is the declared-but-not-true shape this sprint keeps
finding, on the one value a data principal is most entitled to have right.

One nullable timestamp. Set by `apply_correction`, read by `_refresh_identity`,
and narrow on purpose: with no correction on the row, "latest non-empty name
wins" is still the right rule for an extractor refining what it knows.

NULLABLE with no server default, so every existing row reads "never corrected"
-- which is true of all of them.
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_correction_pins_the_name"
down_revision = "0022_data_principal_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column("full_name_corrected_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidates", "full_name_corrected_at")
