"""Add owned curation storage without promoting or deleting legacy raw content.

Runtime switches separately. Downgrade drops the two new tables and therefore
loses their contents; export/restore planning is required before operational rollback.
"""

from alembic import op
import sqlalchemy as sa

revision = "0028_owned_curation"
down_revision = "0027_login_issuances"
branch_labels = None
depends_on = None


def upgrade():
    # This default classifies both existing rows and older application writes.
    # Never infer ownership, remove raw text or copy old keys into approved data.
    op.add_column("unmapped_terms", sa.Column("provenance", sa.String(32),
        nullable=False, server_default="legacy_unattributed"))
    op.create_table("curation_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("profile_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("norm_key", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(norm_key) BETWEEN 1 AND 128", name="ck_curation_observation_key_length"),
        sa.CheckConstraint("length(display_name) BETWEEN 1 AND 128", name="ck_curation_observation_name_length"))
    for column in ("source_id", "norm_key", "created_at"):
        op.create_index(f"ix_curation_observations_{column}", "curation_observations", [column])
    op.create_table("curation_aliases",
        sa.Column("norm_key", sa.String(128), primary_key=True),
        sa.Column("alias", sa.String(128), nullable=False),
        sa.Column("canonical", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("admin_user_id", sa.String(36), sa.ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("length(norm_key) BETWEEN 1 AND 128", name="ck_curation_alias_key_length"),
        sa.CheckConstraint("length(alias) BETWEEN 1 AND 128", name="ck_curation_alias_name_length"),
        sa.CheckConstraint("length(canonical) BETWEEN 1 AND 64", name="ck_curation_alias_canonical_length"),
        sa.CheckConstraint("length(category) BETWEEN 1 AND 32", name="ck_curation_alias_category_length"),
        sa.CheckConstraint("action IN ('map', 'create')", name="ck_curation_alias_action"))


def downgrade():
    op.drop_table("curation_aliases")
    op.drop_table("curation_observations")
    with op.batch_alter_table("unmapped_terms") as batch:
        batch.drop_column("provenance")
