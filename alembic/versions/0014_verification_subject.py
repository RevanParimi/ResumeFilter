"""verification subject discriminator + claim_ref (S7.2)

Revision ID: 0014_verification_subject
Revises: 0013_identity_verification
Create Date: 2026-07-31

Existing rows backfill to 'identity': they predate the existence of any other
subject, so that is not a guess. The server_default is added for the backfill
and then dropped, so the application stays the source of truth for new rows --
the 0004 precedent.

`claim_ref` is a LABEL (employer + interval), not document content. Nothing
here can hold an artifact; the S7.1 structural posture is unchanged.
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_verification_subject"
down_revision = "0013_identity_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("verifications") as batch:
        batch.add_column(sa.Column("subject", sa.String(length=24), nullable=False,
                                   server_default="identity"))
        batch.add_column(sa.Column("claim_ref", sa.String(length=128), nullable=True))
    op.create_index("ix_verifications_subject", "verifications", ["subject"])
    with op.batch_alter_table("verifications") as batch:
        batch.alter_column("subject", existing_type=sa.String(length=24),
                           existing_nullable=False, server_default=None)


def downgrade() -> None:
    op.drop_index("ix_verifications_subject", table_name="verifications")
    with op.batch_alter_table("verifications") as batch:
        batch.drop_column("claim_ref")
        batch.drop_column("subject")
