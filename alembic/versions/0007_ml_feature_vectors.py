"""ml feature vectors: materialized feature-store table (S4.2)

Revision ID: 0007_ml_feature_vectors
Revises: 0006_org_reliability_weight
Create Date: 2026-07-27

"""
from alembic import op
import sqlalchemy as sa

revision = "0007_ml_feature_vectors"
down_revision = "0006_org_reliability_weight"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ml_feature_vectors",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id", sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("view_name", sa.String(length=64), nullable=False),
        sa.Column("view_version", sa.Integer(), nullable=False),
        sa.Column("feature_values", sa.JSON(), nullable=False),
        sa.Column("missing", sa.JSON(), nullable=False),
        sa.Column("consent_state", sa.JSON(), nullable=False),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "candidate_id", "as_of", "view_name", "view_version",
            name="uq_ml_feature_vectors_cut",
        ),
    )
    op.create_index(
        "ix_ml_feature_vectors_candidate_id", "ml_feature_vectors", ["candidate_id"]
    )
    op.create_index(
        "ix_ml_feature_vectors_view", "ml_feature_vectors", ["view_name", "view_version"]
    )


def downgrade() -> None:
    op.drop_index("ix_ml_feature_vectors_view", table_name="ml_feature_vectors")
    op.drop_index("ix_ml_feature_vectors_candidate_id", table_name="ml_feature_vectors")
    op.drop_table("ml_feature_vectors")
