from app.features.store import FeatureStore
from tests.conftest import make_services

import pytest
from sqlalchemy import event, text

from app.core.db import Base, make_engine, make_session_factory
from app.services import build_default_services
from tests.conftest import FakeGitHub


def test_services_bundle_has_feature_store_sharing_candidate_db(settings):
    services = make_services(settings)
    assert isinstance(services.features, FeatureStore)
    # Shares the candidate DB session factory so FK-linked vectors persist.
    assert services.features._session_factory is services.candidates._session_factory


@pytest.fixture
def production(settings, tmp_path, monkeypatch):
    import app.services as module
    monkeypatch.setattr(module, "GitHubClient", lambda settings: FakeGitHub())
    cfg = settings.model_copy(update={"candidates_db_url": "sqlite:///" + (tmp_path/"app.db").as_posix(),
        "db_migrate_on_boot": False})
    bootstrap = make_engine(cfg.candidates_db_url)
    try: Base.metadata.create_all(bootstrap)
    finally: bootstrap.dispose()
    return cfg


def sql_topology(svc):
    stores = [svc.candidates, svc.ledger, svc.report_store, svc.features, svc.jobs,
        svc.curation._store, svc.profile_sources._store, svc.auth._store,
        svc.verification._store, svc.interview._store, svc.screening._store, svc.rights._store]
    stores.extend(getattr(svc, name)._limiter._store for name in ("auth", "interview", "screening", "rights"))
    return [store._session_factory for store in stores]


@pytest.mark.parametrize("production_container", [False, True])
def test_real_and_fake_composition_share_sql_and_service_instances(production, production_container):
    svc = build_default_services(production) if production_container else make_services(production)
    try:
        assert all(factory is svc.session_factory for factory in sql_topology(svc))
        assert svc.jobs._candidates is svc.candidates
        assert svc.jobs._features is svc.features
        assert svc.comp._ledger is svc.ledger
        assert svc.dashboard._jobs is svc.jobs
        assert svc.dashboard._comp is svc.comp
        assert svc.dashboard._ledger is svc.ledger
        assert svc.profile_sources._candidates is svc.candidates
        assert svc.portal._candidates is svc.candidates
        assert svc.portal._ledger is svc.ledger
    finally:
        if hasattr(svc, "dispose_sql"): svc.dispose_sql()


def test_default_composition_constructs_one_runtime_pool(production, monkeypatch):
    import app.core.db as db
    original, engines = db.create_engine, []
    def observed(*args, **kwargs):
        engine = original(*args, **kwargs); engines.append(engine); return engine
    monkeypatch.setattr(db, "create_engine", observed)
    svc = build_default_services(production)
    try:
        assert len(engines) == 1
        assert svc.session_factory.kw["bind"] is engines[0]
    finally:
        for engine in engines: engine.dispose()


def test_explicit_factory_is_borrowed_and_ignores_other_database_settings(production, tmp_path):
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    disposed = []
    event.listen(engine, "engine_disposed", lambda engine: disposed.append(engine))
    try:
        svc = build_default_services(production, session_factory=factory)
        assert all(f is factory for f in sql_topology(svc))
        svc.dispose_sql(); svc.dispose_sql()
        assert not disposed
        with factory() as session:
            assert session.scalar(text("SELECT count(*) FROM candidates")) == 0
    finally: engine.dispose()


def test_different_apps_keep_their_databases_and_instances_separate(production, tmp_path):
    second = production.model_copy(update={"candidates_db_url":"sqlite:///" + (tmp_path/"second.db").as_posix()})
    engine = make_engine(second.candidates_db_url)
    try: Base.metadata.create_all(engine)
    finally: engine.dispose()
    first, other = build_default_services(production), build_default_services(second)
    try:
        first.ledger.create_organization("Only first app")
        assert len(first.ledger.list_organizations()) == 1 and other.ledger.list_organizations() == []
        assert first.session_factory is not other.session_factory
        assert first.jobs is not other.jobs and first.ledger is not other.ledger
    finally:
        for svc in (first, other):
            if hasattr(svc, "dispose_sql"): svc.dispose_sql()


def test_failed_composition_disposes_its_runtime_pool(production, monkeypatch):
    import app.core.db as db
    from app.curation.service import CurationService
    original, created, disposed = db.create_engine, [], []
    def observed(*args, **kwargs):
        engine = original(*args, **kwargs); created.append(engine)
        event.listen(engine, "engine_disposed", lambda engine: disposed.append(engine))
        return engine
    def fail(self): raise RuntimeError("synthetic overlay startup refusal")
    monkeypatch.setattr(db, "create_engine", observed)
    monkeypatch.setattr(CurationService, "refresh_overlay", fail)
    with pytest.raises(RuntimeError, match="synthetic overlay"):
        build_default_services(production)
    assert len(created) == len(disposed) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "startup", "serving"])
async def test_app_disposes_owned_sql_on_every_lifespan_exit(production, monkeypatch, failure):
    import app.main as main
    built, disposed, closed = [], [], []
    def build(settings=None):
        svc = build_default_services(settings or production); built.append(svc)
        event.listen(svc.session_factory.kw["bind"], "engine_disposed", lambda engine: disposed.append(engine))
        event.listen(svc.session_factory.kw["bind"], "close", lambda conn, record: closed.append(conn))
        return svc
    monkeypatch.setattr(main, "get_settings", lambda: production)
    monkeypatch.setattr(main, "build_default_services", build)
    if failure == "startup":
        def fail(svc): raise RuntimeError("synthetic engine setup refusal")
        monkeypatch.setattr(main, "EvaluationEngine", fail)
    app = main.create_app()
    async def cycle():
        async with app.router.lifespan_context(app):
            with app.state.services.session_factory() as session:
                assert session.scalar(text("SELECT 1")) == 1
            if failure == "serving": raise RuntimeError("synthetic serving refusal")
    if failure:
        with pytest.raises(RuntimeError, match="synthetic"): await cycle()
    else:
        await cycle(); await cycle()
    assert len(disposed) == len(built) == (1 if failure else 2)
    assert len(closed) >= len(built)  # Actual warmed DBAPI connections closed.
    for svc in built: svc.dispose_sql()
    assert len(disposed) == len(built)
    assert app.state.services is None and app.state.engine is None


@pytest.mark.asyncio
async def test_injected_bundle_remains_owned_by_its_caller(production):
    from app.main import create_app
    svc = build_default_services(production)
    engine = svc.session_factory.kw["bind"]
    disposed = []
    event.listen(engine, "engine_disposed", lambda engine: disposed.append(engine))
    app = create_app(svc)
    try:
        for _ in range(2):
            async with app.router.lifespan_context(app):
                assert app.state.services is svc
        assert disposed == []
        svc.dispose_sql(); svc.dispose_sql()
        assert disposed == [engine]
    finally: engine.dispose()


@pytest.mark.parametrize("kind", ["jobs", "dashboard"])
def test_standalone_builders_create_only_one_factory(production, monkeypatch, kind):
    import app.core.db as db
    from app.dashboard.service import build_dashboard_service
    from app.matching.store import build_job_store
    original, engines = db.create_engine, []
    def observed(*args, **kwargs):
        engine = original(*args, **kwargs); engines.append(engine); return engine
    monkeypatch.setattr(db, "create_engine", observed)
    try:
        service = build_job_store(production) if kind == "jobs" else build_dashboard_service(production)
        jobs = service if kind == "jobs" else service._jobs
        assert len(engines) == 1
        assert jobs._session_factory is jobs._candidates._session_factory is jobs._features._session_factory
        if kind == "dashboard":
            assert service._ledger._session_factory is jobs._session_factory
            assert service._comp._ledger is service._ledger
    finally:
        for engine in engines: engine.dispose()
