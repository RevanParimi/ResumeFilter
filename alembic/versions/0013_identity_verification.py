"""identity verification spine: outcomes + short-lived OTP challenges (S7.1)

Revision ID: 0013_identity_verification
Revises: 0012_candidate_credentials
Create Date: 2026-07-31

Both tables CASCADE to the candidate so DPDP erasure sweeps them. No column on
either table can hold a document or biometric -- outcomes only, by design.
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_identity_verification"
down_revision = "0012_candidate_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id", sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("assurance_level", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("consent_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_digest", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_verifications_candidate_id", "verifications", ["candidate_id"])
    op.create_index("ix_verifications_method", "verifications", ["method"])
    op.create_index("ix_verifications_status", "verifications", ["status"])

    op.create_table(
        "verification_challenges",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "verification_id", sa.String(length=36),
            sa.ForeignKey("verifications.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("destination_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_verification_challenges_verification_id",
        "verification_challenges", ["verification_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_verification_challenges_verification_id", table_name="verification_challenges"
    )
    op.drop_table("verification_challenges")
    op.drop_index("ix_verifications_status", table_name="verifications")
    op.drop_index("ix_verifications_method", table_name="verifications")
    op.drop_index("ix_verifications_candidate_id", table_name="verifications")
    op.drop_table("verifications")
