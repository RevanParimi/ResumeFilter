"""Reserve in-flight login sends so candidate erasure can cancel activation."""

from alembic import op
import sqlalchemy as sa

revision = "0027_login_issuances"
down_revision = "0026_screening_erasure_guard"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("login_issuances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email_hash", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("plane", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_login_issuances_email_hash", "login_issuances", ["email_hash"])


def downgrade():
    # Reservations contain no challenge/code. Existing active challenges survive.
    op.drop_table("login_issuances")
