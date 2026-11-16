"""Seeded migration compatibility on disposable SQLite/PostgreSQL."""

import hashlib
import os
from datetime import timedelta
from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import MetaData, Table, select, text, update, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.auth.store import AuthStore
from app.core.db import make_engine, make_session_factory
from tests.test_auth_service import NOW

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = '0028_owned_curation'


@pytest.fixture(params=["sqlite", "postgresql"])
def migrated(request, tmp_path):
    bootstrap = None
    if request.param == "postgresql":
        raw = os.environ.get("DEE_TEST_DB_URL", "")
        if not raw:
            pytest.skip("Disposable PostgreSQL DEE_TEST_DB_URL not configured")
        bootstrap = make_engine(raw)
        schema = "login_binding_" + uuid.uuid4().hex
        with bootstrap.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = make_url(raw).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    else:
        url = "sqlite:///" + (tmp_path / "login-binding.db").as_posix()
    engine = make_engine(url)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    try:
        command.upgrade(cfg, "head")
        yield engine, cfg
    finally:
        engine.dispose()
        if bootstrap is not None:
            with bootstrap.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            bootstrap.dispose()


def test_upgrade_preserves_rows_marks_legacy_proof_for_review_and_roundtrips(migrated):
    engine, cfg = migrated
    command.downgrade(cfg, PREVIOUS)
    metadata = MetaData()
    candidates = Table('candidates', metadata, autoload_with=engine)
    sessions = Table('auth_sessions', metadata, autoload_with=engine)
    credentials = Table('candidate_credentials', metadata, autoload_with=engine)
    audits = Table('audit_log', metadata, autoload_with=engine)
    with engine.begin() as connection:
        for cid in ('a', 'expired', 'revoked', 'purged', 'unclaimed'):
            connection.execute(candidates.insert().values(id=cid, email_hash='same-hint',
                phone_hash='shared-phone', full_name='Synthetic legacy', created_at=NOW, updated_at=NOW))
        for cid in ('a', 'expired', 'revoked'):
            connection.execute(sessions.insert().values(id='session-' + cid, candidate_id=cid,
                token_hash=hashlib.sha256(('legacy-' + cid).encode()).hexdigest(),
                issued_at=NOW, expires_at=NOW + timedelta(days=1) if cid != 'expired' else NOW,
                last_seen_at=NOW, csrf_token='synthetic-csrf', revoked_at=NOW if cid == 'revoked' else None))
        connection.execute(credentials.insert().values(id='credential-a', candidate_id='a', access_key_hash='synthetic-key', created_at=NOW))
        connection.execute(audits.insert().values(id='historical-login', actor_type='candidate',
            actor_id='purged', action='auth.session.create', entity_type='auth_session',
            entity_id='purged-session', candidate_id='purged', details={}, created_at=NOW))
    with engine.connect() as connection:
        before = list(connection.execute(select(candidates).order_by(candidates.c.id)).mappings())
        sessions_before = list(connection.execute(select(sessions).order_by(sessions.c.id)).mappings())
        credentials_before = list(connection.execute(select(credentials).order_by(credentials.c.id)).mappings())
        audits_before = list(connection.execute(select(audits).order_by(audits.c.id)).mappings())
    command.upgrade(cfg, 'head')
    current = Table('candidates', MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        after = {r['id']: r for r in connection.execute(select(current)).mappings()}
        for row in before:
            assert all(after[row['id']][key] == value for key, value in row.items())
            assert after[row['id']]['login_email_hash'] is None
            assert after[row['id']]['login_email_verified_at'] is None
            assert bool(after[row['id']]['login_binding_review_required']) == (row['id'] != 'unclaimed')
        assert list(connection.execute(select(sessions).order_by(sessions.c.id)).mappings()) == sessions_before
        assert list(connection.execute(select(credentials).order_by(credentials.c.id)).mappings()) == credentials_before
        assert list(connection.execute(select(audits).order_by(audits.c.id)).mappings()) == audits_before
    factory = make_session_factory(engine)
    assert AuthStore(factory).session_by_token('legacy-a', at=NOW).candidate_id == 'a'
    with engine.begin() as connection:
        connection.execute(sessions.delete())
    with engine.connect() as connection:
        assert connection.scalar(select(current.c.login_binding_review_required).where(current.c.id == 'a'))
    command.downgrade(cfg, PREVIOUS)
    assert 'login_email_hash' not in {c['name'] for c in inspect(engine).get_columns('candidates')}
    with engine.connect() as connection:
        assert list(connection.execute(select(candidates).order_by(candidates.c.id)).mappings()) == before
        assert list(connection.execute(select(credentials).order_by(credentials.c.id)).mappings()) == credentials_before
        assert list(connection.execute(select(audits).order_by(audits.c.id)).mappings()) == audits_before
    command.upgrade(cfg, 'head')
    with engine.connect() as connection:
        final = Table('candidates', MetaData(), autoload_with=engine)
        assert connection.scalar(select(final.c.login_binding_review_required).where(final.c.id == 'purged'))


def test_verified_mailbox_is_unique_while_unproved_hints_may_duplicate(migrated):
    engine, _ = migrated
    candidates = Table('candidates', MetaData(), autoload_with=engine)
    with engine.begin() as connection:
        for cid in ('a', 'b'):
            connection.execute(candidates.insert().values(id=cid, email_hash='same-hint', created_at=NOW, updated_at=NOW))
        connection.execute(update(candidates).where(candidates.c.id == 'a').values(
            login_email_hash='proved-hash', login_email_verified_at=NOW))
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(update(candidates).where(candidates.c.id == 'b').values(
                login_email_hash='proved-hash', login_email_verified_at=NOW))
    with engine.connect() as connection:
        assert connection.scalar(select(candidates.c.login_email_hash).where(candidates.c.id == 'b')) is None
