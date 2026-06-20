"""Vector store for provenance grounding.

Two implementations behind one Protocol:
  * :class:`ChromaVectorStore` — persistent ChromaDB for real runs.
  * :class:`InMemoryVectorStore` — dependency-free, deterministic; used in tests.

To keep M0 fully offline and reproducible, the default embedding is a local
deterministic hashing embedder (no model download, no network). Swap in a real
embedding model for production retrieval quality — see ``HashingEmbedding``.
"""

from __future__ import annotations

import hashlib
import math
from typing import Optional, Protocol, Sequence, runtime_checkable

from app.core.config import Settings, get_settings


@runtime_checkable
class VectorStore(Protocol):
    def add(
        self, *, documents: Sequence[str], ids: Sequence[str],
        metadatas: Optional[Sequence[dict]] = None,
    ) -> None: ...

    def query(self, *, text: str, n_results: int = 3) -> list[str]: ...


class HashingEmbedding:
    """Deterministic local embedding. NOT semantic — a stand-in for M0/tests.

    Token hashing into a fixed-dim L2-normalized vector. Good enough to exercise
    the retrieval path deterministically; replace with sentence-transformers /
    a hosted embedding model for production.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def __call__(self, input: Sequence[str]) -> list[list[float]]:  # chroma signature
        return [self._embed(t) for t in input]

    def embed_one(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in text.lower().split():
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class InMemoryVectorStore:
    """Cosine-similarity store with no external deps (test/default-safe)."""

    def __init__(self, embedder: Optional[HashingEmbedding] = None) -> None:
        self._embedder = embedder or HashingEmbedding()
        self._docs: list[str] = []
        self._vecs: list[list[float]] = []

    def add(self, *, documents, ids=None, metadatas=None) -> None:  # noqa: ARG002
        for doc in documents:
            self._docs.append(doc)
            self._vecs.append(self._embedder.embed_one(doc))

    def query(self, *, text: str, n_results: int = 3) -> list[str]:
        if not self._docs:
            return []
        q = self._embedder.embed_one(text)
        scored = sorted(
            ((sum(a * b for a, b in zip(q, v)), d) for v, d in zip(self._vecs, self._docs)),
            key=lambda t: t[0],
            reverse=True,
        )
        return [d for _, d in scored[:n_results]]


class ChromaVectorStore:
    """Persistent ChromaDB-backed store."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        import chromadb

        settings = settings or get_settings()
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=settings.chroma_collection,
            embedding_function=HashingEmbedding(),  # swap for production embeddings
        )

    def add(self, *, documents, ids, metadatas=None) -> None:
        if not documents:
            return
        self._collection.add(documents=list(documents), ids=list(ids), metadatas=metadatas)

    def query(self, *, text: str, n_results: int = 3) -> list[str]:
        res = self._collection.query(query_texts=[text], n_results=n_results)
        docs = res.get("documents") or [[]]
        return docs[0] if docs else []


def build_vectorstore(settings: Optional[Settings] = None) -> VectorStore:
    """Default = Chroma; falls back to in-memory if chromadb isn't importable."""
    try:
        return ChromaVectorStore(settings)
    except Exception:  # pragma: no cover - environment-dependent
        return InMemoryVectorStore()
