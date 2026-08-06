"""upload ownership: resumes.org_id + reports.org_id (S8.4 Phase A)

Revision ID: 0018_upload_ownership
Revises: 0017_auth_identity
Create Date: 2026-08-06

Nothing in the schema has ever recorded WHICH organization uploaded a resume or
commissioned an evaluation, which was fine while the wedge was operator-run and
is not fine the moment two staffing agencies screen the same candidate.

Ownership is a property of the UPLOAD, not of the person: candidates stay global
and deduplicated (S1.1 identity resolution), so cross-corpus near-duplicate
detection still works, while each upload carries its own owner.

NULLABLE because every existing row is legitimately unowned, and so is every
admin-plane upload. No data migration invents an owner that never existed.

ON DELETE SET NULL, deliberately NOT CASCADE: an organization offboarding must
not destroy a candidate's resume. That resume is the PERSON's data; the only
cascade permitted to delete it is the candidate's own erasure.

batch_alter_table because SQLite cannot ADD COLUMN with a foreign key in place.
On Postgres batch mode is a plain ALTER.
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_upload_ownership"
down_revision = "0017_auth_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("resumes") as batch:
        batch.add_column(sa.Column("org_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_resumes_org_id", "organizations", ["org_id"], ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_resumes_org_id", "resumes", ["org_id"])

    with op.batch_alter_table("reports") as batch:
        batch.add_column(sa.Column("org_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_reports_org_id", "organizations", ["org_id"], ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_reports_org_id", "reports", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_reports_org_id", table_name="reports")
    with op.batch_alter_table("reports") as batch:
        batch.drop_constraint("fk_reports_org_id", type_="foreignkey")
        batch.drop_column("org_id")

    op.drop_index("ix_resumes_org_id", table_name="resumes")
    with op.batch_alter_table("resumes") as batch:
        batch.drop_constraint("fk_resumes_org_id", type_="foreignkey")
        batch.drop_column("org_id")
