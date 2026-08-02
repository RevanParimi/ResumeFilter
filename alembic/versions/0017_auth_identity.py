"""org_users, admin_users, auth_sessions, login_challenges (S8.2)

Revision ID: 0017_auth_identity
Revises: 0016_reports_outcomes
Create Date: 2026-08-02

Sessions are opaque server-side rows, not JWTs: a JWT stays valid after a
candidate revokes consent or erases their account, which is a DPDP correctness
bug rather than a preference (PI-8 decision 0.2). An opaque row dies with a
DELETE.

auth_sessions carries three nullable FKs and a CHECK that exactly one is
non-null. A polymorphic subject_type+subject_id cannot carry a foreign key, so
erasure would stop cascading -- the guarantee this whole architecture rests on.

login_challenges deliberately has NO foreign key: at signup time no principal
exists yet. The erasure path therefore deletes them explicitly by email_hash.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_auth_identity"
down_revision = "0016_reports_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "organization_id", "email_hash", name="uq_org_users_org_email"
        ),
    )
    op.create_index("ix_org_users_organization_id", "org_users", ["organization_id"])
    op.create_index("ix_org_users_email_hash", "org_users", ["email_hash"])

    op.create_table(
        "admin_users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_admin_users_email_hash", "admin_users", ["email_hash"], unique=True
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column("org_user_id", sa.String(length=36), nullable=True),
        sa.Column("admin_user_id", sa.String(length=36), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_user_id"], ["org_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["admin_user_id"], ["admin_users.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "(CASE WHEN candidate_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN org_user_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN admin_user_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_auth_sessions_exactly_one_principal",
        ),
    )
    op.create_index("ix_auth_sessions_candidate_id", "auth_sessions", ["candidate_id"])
    op.create_index("ix_auth_sessions_org_user_id", "auth_sessions", ["org_user_id"])
    op.create_index("ix_auth_sessions_admin_user_id", "auth_sessions", ["admin_user_id"])
    op.create_index(
        "ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True
    )

    op.create_table(
        "login_challenges",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("plane", sa.String(length=16), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "email_hash", "purpose", "plane", name="uq_login_challenges_scope"
        ),
    )
    op.create_index(
        "ix_login_challenges_email_hash", "login_challenges", ["email_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_login_challenges_email_hash", table_name="login_challenges")
    op.drop_table("login_challenges")
    for ix in (
        "ix_auth_sessions_token_hash",
        "ix_auth_sessions_admin_user_id",
        "ix_auth_sessions_org_user_id",
        "ix_auth_sessions_candidate_id",
    ):
        op.drop_index(ix, table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_admin_users_email_hash", table_name="admin_users")
    op.drop_table("admin_users")
    op.drop_index("ix_org_users_email_hash", table_name="org_users")
    op.drop_index("ix_org_users_organization_id", table_name="org_users")
    op.drop_table("org_users")
