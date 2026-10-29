"""Owned transports, startup failure, cancellation and borrowed resources."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import event

from app.services import build_default_services
from app.services.github import GitHubClient
from app.services.llm import OpenRouterLLM
from app.services.speech import OpenRouterSpeech
from tests.test_services_features import production  # noqa: F401


@pytest.mark.parametrize('pool_name', ['auth_codes', 'contact_codes', 'auth_resolution', 'auth_redemption', 'auth_sessions', 'candidate_records'])
async def test_code_shutdown_joins_accepted_work_before_disposing_sql(services, monkeypatch, pool_name):
    from threading import Event
    from app.core.blocking import ExecutionUnavailable
    entered, release, finished = Event(), Event(), Event()
    def work():
        entered.set()
        assert release.wait(8)
        finished.set()
        return 'completed'
    pending = asyncio.create_task(getattr(services, pool_name).run(work))
    assert await asyncio.to_thread(entered.wait, 5)
    disposed = []
    def dispose():
        assert finished.is_set()
        disposed.append(True)
    monkeypatch.setattr(services, 'dispose_sql', dispose)
    closing = asyncio.create_task(services.aclose())
    try:
        await asyncio.sleep(.02)
        closing.cancel()
        await asyncio.sleep(.02)
        closing.cancel()
        await asyncio.sleep(.02)
        assert not closing.done() and not disposed
        with pytest.raises(ExecutionUnavailable, match=pool_name.removesuffix('s') + '_executor_closed'):
            getattr(services, pool_name)
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert await pending == 'completed'
    await services.aclose()
    assert disposed == [True]


async def test_services_stop_pdf_before_sql_disposal_and_refuse_late_admission(services, monkeypatch):
    from threading import Event
    from app.core.pdf_execution import PdfUnavailable, check_pdf_cancelled
    entered, stopped = Event(), Event()
    def work():
        entered.set()
        try:
            while True:
                check_pdf_cancelled()
                stopped.wait(.01)
        finally:
            stopped.set()
    parsing = asyncio.create_task(services.pdf.run(work))
    assert await asyncio.to_thread(entered.wait, 5)
    disposed = []
    def dispose():
        assert stopped.is_set(), 'SQL disposal preceded PDF child supervision cleanup'
        disposed.append(True)
    monkeypatch.setattr(services, 'dispose_sql', dispose)
    await services.aclose()
    with pytest.raises(PdfUnavailable, match='pdf_executor_closed'):
        await parsing
    with pytest.raises(PdfUnavailable, match='pdf_executor_closed'):
        _ = services.pdf
    await services.aclose()
    assert disposed == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["llm", "speech"])
async def test_sdk_transports_are_lazy_cached_and_closed_once(settings, monkeypatch, kind):
    import openai
    made = []
    def client(**kwargs):
        transport = SimpleNamespace(close=AsyncMock(), chat=SimpleNamespace(completions=SimpleNamespace(
            create=AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Saved answer"))])))))
        made.append((transport, kwargs)); return transport
    monkeypatch.setattr(openai, "AsyncOpenAI", client)
    provider = (OpenRouterLLM if kind == "llm" else OpenRouterSpeech)(settings)
    assert made == []
    for _ in range(2):
        if kind == "llm":
            assert await provider.acomplete_text(tier="parsing", system="fixed", prompt="fixed") == "Saved answer"
        else:
            assert (await provider.atranscribe(audio_b64="AAAA", mime="audio/wav")).text == "Saved answer"
    assert len(made) == 1
    await provider.aclose(); await provider.aclose()
    made[0][0].close.assert_awaited_once()
    with pytest.raises(RuntimeError, match="closed"):
        provider._get_client()
    assert len(made) == 1
    assert made[0][1]["timeout"] == (settings.llm_timeout_seconds if kind == "llm" else settings.speech_timeout_seconds)


@pytest.mark.asyncio
async def test_unused_sdk_providers_close_without_creating_a_transport(settings, monkeypatch):
    import openai
    def forbidden(**kwargs): raise AssertionError("unused provider created transport")
    monkeypatch.setattr(openai, "AsyncOpenAI", forbidden)
    for provider in (OpenRouterLLM(settings), OpenRouterSpeech(settings)):
        await provider.aclose(); await provider.aclose()


@pytest.mark.asyncio
async def test_github_owned_transport_is_lazy_and_borrowed_transport_survives(settings, monkeypatch):
    original, created = httpx.AsyncClient, []
    def make(**kwargs):
        transport = original(**kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(404)))
        created.append(transport); return transport
    monkeypatch.setattr(httpx, "AsyncClient", make)
    provider = GitHubClient(settings)
    assert not created
    await provider.gather_repo_evidence("synthetic", "repo")
    assert len(created) == 1 and not created[0].is_closed
    await provider.aclose(); await provider.aclose()
    assert created[0].is_closed
    async with original(transport=httpx.MockTransport(lambda request: httpx.Response(404))) as borrowed:
        wrapper = GitHubClient(settings, client=borrowed)
        await wrapper.aclose()
        assert not borrowed.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_owned_resources_settle_once_and_cleanup_failure_does_not_skip_sql(production, failed, log_output):
    svc = build_default_services(production)
    closed, disposed = [], []
    class Provider:
        async def aclose(self):
            closed.append(self)
            if failed and len(closed) == 1: raise RuntimeError("synthetic-private-provider-payload")
    clients = [Provider(), Provider()]
    svc._owned_clients = (*clients, clients[0])  # Aliases close once.
    event.listen(svc.session_factory.kw["bind"], "engine_disposed", lambda engine: disposed.append(engine))
    outcomes = await asyncio.gather(svc.aclose(), svc.aclose(), return_exceptions=True)
    assert len(closed) == 2 and len(disposed) == 1
    if failed:
        assert all(isinstance(outcome, RuntimeError) and "synthetic-private" not in str(outcome) for outcome in outcomes)
    else: assert outcomes == [None, None]
    assert "synthetic-private" not in log_output.text


@pytest.mark.asyncio
async def test_cancelled_caller_waits_for_all_owned_cleanup(production):
    svc = build_default_services(production)
    entered, release = asyncio.Event(), asyncio.Event()
    async def close():
        entered.set(); await release.wait()
    closer = SimpleNamespace(aclose=AsyncMock(side_effect=close))
    svc._owned_clients = (closer,)
    task = asyncio.create_task(svc.aclose())
    await entered.wait(); task.cancel(); await asyncio.sleep(0)
    task.cancel(); await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError): await task
    await svc.aclose()
    closer.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_injected_bundle_and_clients_are_borrowed(production):
    from app.main import create_app
    clients = [SimpleNamespace(aclose=AsyncMock()) for _ in range(3)]
    svc = build_default_services(production, github=clients[0], llm=clients[1], speech=clients[2])
    app = create_app(svc)
    async with app.router.lifespan_context(app): pass
    await svc.aclose()
    assert all(client.aclose.await_count == 0 for client in clients)


@pytest.mark.parametrize("boundary", ["curation", "portal"])
def test_failed_sync_composition_opens_no_http_transport(production, monkeypatch, boundary):
    import app.services as module
    from app.curation.service import CurationService
    monkeypatch.setattr(module, "GitHubClient", GitHubClient)
    calls = []
    def transport(**kwargs):
        calls.append(kwargs); return SimpleNamespace()
    def fail(self): raise RuntimeError("synthetic startup refusal")
    monkeypatch.setattr(httpx, "AsyncClient", transport)
    if boundary == "curation":
        monkeypatch.setattr(CurationService, "refresh_overlay", fail)
    else:
        import app.portal.service as portal
        monkeypatch.setattr(portal, "build_portal_service", lambda *args, **kwargs: fail(None))
    with pytest.raises(RuntimeError, match="synthetic startup refusal"):
        build_default_services(production)
    assert calls == []


def test_late_composition_failure_disposes_sql_and_preserves_primary(production, monkeypatch):
    import app.services as module
    disposed = []
    original = module.make_engine
    def engine(url):
        value = original(url)
        event.listen(value, "engine_disposed", lambda engine: disposed.append(True))
        return value
    def fail(settings): raise ValueError("synthetic flywheel setup refusal")
    monkeypatch.setattr(module, "make_engine", engine)
    monkeypatch.setattr(module, "build_flywheel", fail)
    with pytest.raises(ValueError, match="synthetic flywheel setup refusal"):
        build_default_services(production)
    assert disposed == [True]


@pytest.mark.asyncio
async def test_sql_and_provider_cleanup_failures_still_settle_other_clients(production, monkeypatch, log_output):
    from app.services import ServiceCleanupError
    svc = build_default_services(production)
    disposed, closed = [], []
    engine = svc._owned_engine
    original = engine.dispose
    def fail_sql():
        original(); disposed.append(True)
        raise RuntimeError("synthetic-private-driver-payload")
    async def fail_provider(): raise asyncio.CancelledError("synthetic-private-provider-payload")
    async def close(): closed.append(True)
    monkeypatch.setattr(engine, "dispose", fail_sql)
    svc._owned_clients = (SimpleNamespace(aclose=fail_provider), SimpleNamespace(aclose=close))
    for _ in range(2):
        with pytest.raises(ServiceCleanupError, match="^owned service cleanup failed$"):
            await svc.aclose()
    assert disposed == closed == [True]
    assert "synthetic-private" not in log_output.text


@pytest.mark.asyncio
@pytest.mark.parametrize("primary", [False, True])
async def test_lifespan_cleanup_failure_preserves_primary_error(production, monkeypatch, primary, log_output):
    import app.main as main
    from app.services import ServiceCleanupError
    async def fail(): raise RuntimeError("synthetic-private-provider-payload")
    def build(settings):
        svc = build_default_services(settings)
        svc._owned_clients = (SimpleNamespace(aclose=fail),)
        return svc
    monkeypatch.setattr(main, "get_settings", lambda: production)
    monkeypatch.setattr(main, "build_default_services", build)
    app = main.create_app()
    with pytest.raises(RuntimeError if primary else ServiceCleanupError,
                       match="primary serving failure" if primary else "^owned service cleanup failed$"):
        async with app.router.lifespan_context(app):
            if primary: raise RuntimeError("primary serving failure")
    assert app.state.services is app.state.engine is None
    assert "synthetic-private" not in log_output.text


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["startup", "serving", "normal"])
async def test_app_closes_owned_clients_on_all_exit_paths(production, monkeypatch, phase):
    import app.main as main
    closed = []
    async def close(): closed.append(True)
    def build(settings):
        svc = build_default_services(settings)
        svc._owned_clients = (SimpleNamespace(aclose=close),)
        return svc
    monkeypatch.setattr(main, "get_settings", lambda: production)
    monkeypatch.setattr(main, "build_default_services", build)
    if phase == "startup":
        def fail(svc): raise RuntimeError("synthetic graph setup refusal")
        monkeypatch.setattr(main, "EvaluationEngine", fail)
    app = main.create_app()
    async def run():
        async with app.router.lifespan_context(app):
            if phase == "serving": raise RuntimeError("synthetic serving refusal")
    if phase == "normal": await run()
    else:
        with pytest.raises(RuntimeError, match="synthetic"): await run()
    assert closed == [True]


def test_graph_requires_explicit_services_without_constructing_resources(monkeypatch):
    import app.graph.build as module
    def forbidden(): raise AssertionError("implicit service construction")
    monkeypatch.setattr(module, "build_default_services", forbidden, raising=False)
    with pytest.raises(TypeError): module.EvaluationEngine()
    with pytest.raises(ValueError, match="explicit Services"): module.EvaluationEngine(None)
