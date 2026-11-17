"""Drop tables belonging to retired features.

Downgrade restores the schema empty; removed records cannot be recovered.
"""
from alembic import op
import sqlalchemy as sa

revision = "0031_cut_unused_tables"
down_revision = "0030_screening_ingest_facts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('evaluation_events')
    op.drop_table('coding_round_results')
    op.drop_table('observed_offers')
    op.drop_table('interview_records')
    op.drop_table('curation_observations')
    op.drop_table('curation_aliases')
    op.drop_table('unmapped_terms')
    op.drop_table('profile_sources')
    op.drop_table('data_principal_requests')


def downgrade() -> None:
    op.create_table('data_principal_requests',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('candidate_id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('applied', sa.Boolean(), nullable=False),
    sa.Column('field', sa.String(length=32), nullable=True),
    sa.Column('current_value', sa.Text(), nullable=False),
    sa.Column('requested_value', sa.Text(), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolution', sa.Text(), nullable=False),
    sa.Column('resolved_by', sa.String(length=16), nullable=True),
    sa.Column('resolved_by_admin_user_id', sa.String(length=36), nullable=True),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['resolved_by_admin_user_id'], ['admin_users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_data_principal_requests_candidate_id'), 'data_principal_requests', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_data_principal_requests_created_at'), 'data_principal_requests', ['created_at'], unique=False)
    op.create_index(op.f('ix_data_principal_requests_kind'), 'data_principal_requests', ['kind'], unique=False)
    op.create_index(op.f('ix_data_principal_requests_status'), 'data_principal_requests', ['status'], unique=False)
    op.create_table('profile_sources',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('candidate_id', sa.String(length=36), nullable=False),
    sa.Column('source_type', sa.String(length=32), nullable=False),
    sa.Column('identifier', sa.Text(), nullable=False),
    sa.Column('signal', sa.JSON(), nullable=False),
    sa.Column('method', sa.String(length=16), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_profile_sources_candidate_id'), 'profile_sources', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_profile_sources_source_type'), 'profile_sources', ['source_type'], unique=False)
    op.create_table('unmapped_terms',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('norm_key', sa.String(length=128), nullable=False),
    sa.Column('display_name', sa.Text(), nullable=False),
    sa.Column('source_types', sa.JSON(), nullable=False),
    sa.Column('occurrences', sa.Integer(), nullable=False),
    sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('action', sa.String(length=16), nullable=True),
    sa.Column('canonical', sa.String(length=64), nullable=True),
    sa.Column('category', sa.String(length=32), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('decided_by', sa.String(length=128), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('provenance', sa.String(length=32), server_default='legacy_unattributed', nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_unmapped_terms_norm_key'), 'unmapped_terms', ['norm_key'], unique=True)
    op.create_index(op.f('ix_unmapped_terms_status'), 'unmapped_terms', ['status'], unique=False)
    op.create_table('curation_aliases',
    sa.Column('norm_key', sa.String(length=128), nullable=False),
    sa.Column('alias', sa.String(length=128), nullable=False),
    sa.Column('canonical', sa.String(length=64), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('action', sa.String(length=16), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('admin_user_id', sa.String(length=36), nullable=True),
    sa.CheckConstraint("action IN ('map', 'create')", name='ck_curation_alias_action'),
    sa.CheckConstraint('length(alias) BETWEEN 1 AND 128', name='ck_curation_alias_name_length'),
    sa.CheckConstraint('length(canonical) BETWEEN 1 AND 64', name='ck_curation_alias_canonical_length'),
    sa.CheckConstraint('length(category) BETWEEN 1 AND 32', name='ck_curation_alias_category_length'),
    sa.CheckConstraint('length(norm_key) BETWEEN 1 AND 128', name='ck_curation_alias_key_length'),
    sa.ForeignKeyConstraint(['admin_user_id'], ['admin_users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('norm_key')
    )
    op.create_table('curation_observations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('source_id', sa.String(length=36), nullable=False),
    sa.Column('norm_key', sa.String(length=128), nullable=False),
    sa.Column('display_name', sa.String(length=128), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('length(display_name) BETWEEN 1 AND 128', name='ck_curation_observation_name_length'),
    sa.CheckConstraint('length(norm_key) BETWEEN 1 AND 128', name='ck_curation_observation_key_length'),
    sa.ForeignKeyConstraint(['source_id'], ['profile_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_curation_observations_created_at'), 'curation_observations', ['created_at'], unique=False)
    op.create_index(op.f('ix_curation_observations_norm_key'), 'curation_observations', ['norm_key'], unique=False)
    op.create_index(op.f('ix_curation_observations_source_id'), 'curation_observations', ['source_id'], unique=False)
    op.create_table('interview_records',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('candidate_id', sa.String(length=36), nullable=False),
    sa.Column('consent_id', sa.String(length=36), nullable=False),
    sa.Column('stage', sa.String(length=16), nullable=False),
    sa.Column('outcome', sa.String(length=16), nullable=False),
    sa.Column('interviewed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['consent_id'], ['consent_grants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_interview_records_candidate_id'), 'interview_records', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_interview_records_consent_id'), 'interview_records', ['consent_id'], unique=False)
    op.create_index(op.f('ix_interview_records_org_id'), 'interview_records', ['org_id'], unique=False)
    op.create_table('observed_offers',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('candidate_id', sa.String(length=36), nullable=False),
    sa.Column('consent_id', sa.String(length=36), nullable=False),
    sa.Column('role_family', sa.String(length=32), nullable=False),
    sa.Column('seniority', sa.String(length=16), nullable=False),
    sa.Column('city_tier', sa.String(length=16), nullable=False),
    sa.Column('ctc_fixed', sa.Float(), nullable=False),
    sa.Column('ctc_variable', sa.Float(), nullable=True),
    sa.Column('currency', sa.String(length=8), nullable=False),
    sa.Column('offered_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['consent_id'], ['consent_grants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_observed_offers_candidate_id'), 'observed_offers', ['candidate_id'], unique=False)
    op.create_index('ix_observed_offers_role_signal', 'observed_offers', ['role_family', 'seniority', 'city_tier'], unique=False)
    op.create_table('coding_round_results',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=36), nullable=False),
    sa.Column('candidate_id', sa.String(length=36), nullable=False),
    sa.Column('consent_id', sa.String(length=36), nullable=False),
    sa.Column('platform', sa.String(length=32), nullable=False),
    sa.Column('platform_name', sa.Text(), nullable=True),
    sa.Column('assessment_name', sa.Text(), nullable=True),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('max_score', sa.Float(), nullable=True),
    sa.Column('percentile', sa.Float(), nullable=True),
    sa.Column('problem_tags', sa.JSON(), nullable=False),
    sa.Column('taken_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('raw', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['consent_id'], ['consent_grants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_coding_round_results_candidate_id'), 'coding_round_results', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_coding_round_results_consent_id'), 'coding_round_results', ['consent_id'], unique=False)
    op.create_index(op.f('ix_coding_round_results_org_id'), 'coding_round_results', ['org_id'], unique=False)
    op.create_table('evaluation_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('record_id', sa.String(length=36), nullable=False),
    sa.Column('candidate_id', sa.String(length=36), nullable=False),
    sa.Column('event_type', sa.String(length=32), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['record_id'], ['interview_records.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_evaluation_events_candidate_id'), 'evaluation_events', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_evaluation_events_record_id'), 'evaluation_events', ['record_id'], unique=False)
