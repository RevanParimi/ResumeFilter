"""Owned real provider wrappers with local SDK/HTTP fakes; graceful SQL restart.

No real provider traffic or media/answer payloads in lifecycle metadata. Reuses
T1A's migrated storage, actor, consent, erasure and graceful-stop journey with
T2's default/legacy-settings Chroma guard. --integration adds the R4-S1-Q HTTP
API/UI composition checks; --postgres selects disposable PostgreSQL storage.
"""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import httpx

from smoke_r4_s1_t1a import main as sql_main
from smoke_r4_s1_t2 import create_smoke_app as sql_app


def create_smoke_app():
    import app.services as services
    import openai
    from app.services.github import GitHubClient
    from app.services.llm import OpenRouterLLM
    from app.services.speech import OpenRouterSpeech
    from smoke_r2_s2_t1 import ClaimFake
    from smoke_r3_s3_t3 import ANSWER

    app = sql_app()
    path = Path(os.environ["VERITAS_SQL_SMOKE_EVENTS"])
    def record(event, provider, **metadata):
        with path.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"event":event, "provider":provider, **metadata}) + "\n")

    class ObservedGitHub(GitHubClient):
        def _get_client(self):
            if self._client is None and not self._closed:
                self._client = httpx.AsyncClient(base_url="http://synthetic-github.invalid",
                    transport=httpx.MockTransport(lambda request: httpx.Response(404)))
                record("provider_opened", "github")
            return super()._get_client()

        async def aclose(self):
            was_open = self._client is not None and not self._closed
            await super().aclose()
            if was_open: record("provider_closed", "github", closed=self._client.is_closed)

    def provider(settings, kind):
        class SDK:
            def __init__(self, **kwargs):
                self.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.complete))
                record("provider_opened", kind)

            async def complete(self, *, model, messages, max_tokens=512):
                # Exercise an actual async httpx transport; no user payload sent.
                await self.http.post("http://synthetic-sdk.invalid/completion", json={"synthetic":True})
                content = ANSWER if kind == "speech" else await ClaimFake(settings)._araw(
                    model=model, system=messages[0]["content"], prompt=messages[1]["content"], max_tokens=max_tokens)
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

            async def close(self):
                await self.http.aclose()
                record("provider_closed", kind, closed=self.http.is_closed)
        # The wrappers import the SDK lazily; each closure binds its own factory.
        base = OpenRouterLLM if kind == "llm" else OpenRouterSpeech
        class Observed(base):
            def _get_client(self):
                original = openai.AsyncOpenAI
                try:
                    openai.AsyncOpenAI = SDK
                    return super()._get_client()
                finally:
                    openai.AsyncOpenAI = original
        return Observed(settings)

    services.GitHubClient = ObservedGitHub
    services.build_llm = lambda settings: provider(settings, "llm")
    services.build_speech = lambda settings: provider(settings, "speech")
    return app


if __name__ == "__main__":
    raise SystemExit(sql_main(provider_checks=True, composition_checks="--integration" in sys.argv))
