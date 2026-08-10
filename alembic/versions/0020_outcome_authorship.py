"""outcome authorship: who closed the loop (S8.5)

Revision ID: 0020_outcome_authorship
Revises: 0019_screening_batches
Create Date: 2026-08-10

`outcomes` recorded WHAT was judged and nothing about WHO judged it. That was
tolerable while one operator was the only writer. It stops being tolerable the
moment customers write to the same table, which is what the org-plane outcome
route makes possible -- and that judgment is PI-9's calibration input, so its
source is not metadata, it is the point.

`org_id` is ON DELETE SET NULL, deliberately NOT CASCADE, and the contrast with
`screening_batches.org_id` (which CASCADEs) is the reasoning: a batch is an
organisation's own operational work product with no meaning once they are gone,
while an outcome is a LABEL about a person's record that the platform learns
from. Destroying labels on offboarding would silently degrade the model and
leave the report that survives -- `reports.org_id` SET NULLs for exactly the
same reason -- with a judgment history full of holes.

`recorded_by` exists BECAUSE `org_id` is SET NULL. Without it, a null org
conflates "an operator recorded this" with "the customer who recorded this has
offboarded", and a calibration harness must never train on our own operator's
self-labels believing a customer produced them.

Existing rows backfill to 'operator': there was no other door, so that is a
fact about them and not a guess. The server_default is added for the backfill
and then DROPPED, so the application stays the source of truth for new rows --
the 0004/0014 precedent, and here it also stops a forgotten `recorded_by` from
becoming 'operator' silently.

batch_alter_table because SQLite cannot ADD COLUMN with a foreign key in place.
On Postgres batch mode is a plain ALTER.
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_outcome_authorship"
down_revision = "0019_screening_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("outcomes") as batch:
        batch.add_column(sa.Column(
            "recorded_by", sa.String(length=16), nullable=False,
            server_default="operator",
        ))
        batch.add_column(sa.Column("org_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column(
            "recorded_by_org_user_id", sa.String(length=36), nullable=True,
        ))
        batch.create_foreign_key(
            "fk_outcomes_org_id", "organizations", ["org_id"], ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_outcomes_recorded_by_org_user_id", "org_users",
            ["recorded_by_org_user_id"], ["id"], ondelete="SET NULL",
        )

    # The default was for the backfill only.
    with op.batch_alter_table("outcomes") as batch:
        batch.alter_column(
            "recorded_by", existing_type=sa.String(length=16),
            existing_nullable=False, server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table("outcomes") as batch:
        batch.drop_constraint("fk_outcomes_recorded_by_org_user_id", type_="foreignkey")
        batch.drop_constraint("fk_outcomes_org_id", type_="foreignkey")
        batch.drop_column("recorded_by_org_user_id")
        batch.drop_column("org_id")
        batch.drop_column("recorded_by")
