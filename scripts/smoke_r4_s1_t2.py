"""T2: migrated production HTTP/restart with Chroma unavailable, fake providers.

Reuses T1A's evaluation, two-actor ownership, portal, search, consent, erasure and
graceful shutdown journey. First process uses defaults, restart uses retired
Chroma settings; neither may attempt an import, start a vector thread or create
the configured legacy directory. No existing vector data is read or removed.
"""

from contextlib import asynccontextmanager
import importlib.abc
import json
import os
from pathlib import Path
import sys
import threading
import time

from smoke_r4_s1_t1a import create_smoke_app as sql_app, main as sql_main


def create_smoke_app():
    path = Path(os.environ["VERITAS_SQL_SMOKE_EVENTS"])
    prior = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    legacy = any(row["event"] == "started" for row in prior)
    legacy_dir = path.parent / "unused-chroma"
    retired = {
        "DEE_VECTORSTORE_BACKEND": "chroma",
        "DEE_VECTORSTORE_INIT_TIMEOUT_SECONDS": "15",
        "DEE_CHROMA_PERSIST_DIR": str(legacy_dir),
        "DEE_CHROMA_COLLECTION": "legacy-evidence",
    }
    for key, value in retired.items():
        if legacy:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)

    attempts = []

    class WithoutChroma(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "chromadb" or fullname.startswith("chromadb."):
                attempts.append(fullname)
                raise ModuleNotFoundError("Chroma deliberately unavailable in T2 smoke")

    assert not any(name == "chromadb" or name.startswith("chromadb.") for name in sys.modules)
    sys.meta_path.insert(0, WithoutChroma())
    start = time.perf_counter()
    app = sql_app()
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            def verify():
                assert attempts == [], "unused Chroma import attempted"
                assert not legacy_dir.exists(), "legacy storage unexpectedly opened"
                assert not any(t.name == "chroma-init" for t in threading.enumerate())
                assert not hasattr(app.state.services, "vectorstore")
            verify()
            with path.open("a", encoding="utf-8") as log:
                log.write(json.dumps({
                    "event": "provenance_runtime", "mode": "legacy" if legacy else "default",
                    "startup_seconds": round(time.perf_counter() - start, 4),
                    "chroma_import_attempts": len(attempts), "vector_threads": 0,
                }) + "\n")
            try:
                yield
            finally:
                verify()
        assert attempts == [] and not legacy_dir.exists()

    app.router.lifespan_context = lifespan
    return app


if __name__ == "__main__":
    os.environ["VERITAS_SQL_SMOKE_FACTORY"] = "smoke_r4_s1_t2:create_smoke_app"
    print("R4-S1-T2: default/legacy settings, blocked Chroma imports, migrated HTTP/restart", flush=True)
    raise SystemExit(sql_main())
