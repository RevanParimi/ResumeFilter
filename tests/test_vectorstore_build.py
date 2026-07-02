"""Vector store construction must be bounded (NFR-1).

ChromaDB's PersistentClient can hang indefinitely on some machines/networks.
A hang is not an exception — build_vectorstore must enforce a timeout and fall
back to the in-memory store so service startup never blocks.
"""

from __future__ import annotations

import time

import app.services.vectorstore as vs_mod
from app.services.vectorstore import InMemoryVectorStore, build_vectorstore


def test_memory_backend_explicit(settings):
    s = settings.model_copy(update={"vectorstore_backend": "memory"})
    assert isinstance(build_vectorstore(s), InMemoryVectorStore)


def test_chroma_init_hang_falls_back_to_memory(settings, monkeypatch):
    class HangingChroma:
        def __init__(self, *a, **kw):
            time.sleep(30)  # simulates the PersistentClient deadlock

    monkeypatch.setattr(vs_mod, "ChromaVectorStore", HangingChroma)
    s = settings.model_copy(update={"vectorstore_init_timeout_seconds": 0.2})

    start = time.perf_counter()
    store = build_vectorstore(s)
    elapsed = time.perf_counter() - start

    assert isinstance(store, InMemoryVectorStore)
    assert elapsed < 5, "startup must not block on a hanging Chroma init"


def test_chroma_init_error_falls_back_to_memory(settings, monkeypatch):
    class BrokenChroma:
        def __init__(self, *a, **kw):
            raise RuntimeError("no disk")

    monkeypatch.setattr(vs_mod, "ChromaVectorStore", BrokenChroma)
    assert isinstance(build_vectorstore(settings), InMemoryVectorStore)
