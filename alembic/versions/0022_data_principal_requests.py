"""data principal requests: correction + grievance, reviewed (S8.3 Phase B)

Revision ID: 0022_data_principal_requests
Revises: 0021_rate_limit_counters
Create Date: 2026-08-11

ONE table, TWO kinds. A correction and a grievance share a lifecycle -- filed
by the subject, reviewed by an operator, decided with a written reason,
disclosed back -- and splitting them would mean two queues an operator has to
remember to check, where the one they forget is the one holding a complaint.

`candidate_id` CASCADES. The contrast with S8.5's `outcomes.org_id` (SET NULL)
is the reasoning: an outcome is a label the PLATFORM learns from and outlives
the org that recorded it, while a correction request is wholly the subject's
own. Erasure is the stronger right, and a request about a person who no longer
exists is personal data with no subject.

`status` and `applied` are TWO COLUMNS, deliberately. `status` is what the
operator decided (resolved | rejected); `applied` is whether that decision
actually wrote anything -- false for every grievance, false for an email
correction handled out of band, true only when a value moved. One four-member
enum would leave "is an applied correction also resolved?" answerable two ways.

`resolved_by` + `resolved_by_admin_user_id` are the S8.5 `recorded_by` pattern
one table over: the shared admin key has no human behind it, so a null FK on
its own would conflate "an operator used the machine credential" with "the
admin who decided this has since been deleted". NO server default on either --
a writer that forgets to say must fail loudly, which is exactly what caught the
third writer to `outcomes` in S8.5.
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_data_principal_requests"
down_revision = "0021_rate_limit_counters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_principal_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("field", sa.String(length=32), nullable=True),
        sa.Column("current_value", sa.Text(), nullable=False),
        sa.Column("requested_value", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("resolved_by", sa.String(length=16), nullable=True),
        sa.Column(
            "resolved_by_admin_user_id",
            sa.String(length=36),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_data_principal_requests_candidate_id",
        "data_principal_requests",
        ["candidate_id"],
    )
    op.create_index(
        "ix_data_principal_requests_kind", "data_principal_requests", ["kind"]
    )
    # The operator's queue reads WHERE status = 'open' ORDER BY created_at.
    op.create_index(
        "ix_data_principal_requests_status", "data_principal_requests", ["status"]
    )
    op.create_index(
        "ix_data_principal_requests_created_at",
        "data_principal_requests",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_data_principal_requests_created_at", table_name="data_principal_requests"
    )
    op.drop_index(
        "ix_data_principal_requests_status", table_name="data_principal_requests"
    )
    op.drop_index(
        "ix_data_principal_requests_kind", table_name="data_principal_requests"
    )
    op.drop_index(
        "ix_data_principal_requests_candidate_id",
        table_name="data_principal_requests",
    )
    op.drop_table("data_principal_requests")
