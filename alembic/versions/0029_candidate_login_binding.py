"""Separate verified login mailbox ownership from asserted resume contacts.

Existing bindings remain NULL. Historical sessions/session-create audits cannot
tell us which mailbox was proved; their subjects require explicit review, even
after sessions are purged. No IDs, asserted contacts or credentials change.
"""

from alembic import op
import sqlalchemy as sa

revision = '0029_candidate_login_binding'
down_revision = '0028_owned_curation'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('candidates', sa.Column('login_email_hash', sa.String(64), nullable=True))
    op.add_column('candidates', sa.Column('login_email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('candidates', sa.Column('login_binding_review_required', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(sa.text('UPDATE candidates SET login_binding_review_required = TRUE '
                      'WHERE EXISTS (SELECT 1 FROM auth_sessions WHERE auth_sessions.candidate_id = candidates.id) '
                      'OR EXISTS (SELECT 1 FROM audit_log WHERE audit_log.candidate_id = candidates.id '
                      "AND audit_log.action = 'auth.session.create')"))
    op.create_index('uq_candidates_login_email_hash', 'candidates', ['login_email_hash'], unique=True)


def downgrade():
    op.drop_index('uq_candidates_login_email_hash', table_name='candidates')
    op.drop_column('candidates', 'login_binding_review_required')
    op.drop_column('candidates', 'login_email_verified_at')
    op.drop_column('candidates', 'login_email_hash')
