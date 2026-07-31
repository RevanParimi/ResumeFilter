"""Base64 PDF → plain text. Deterministic and LLM-free.

Shared by the graph's ingest node and the candidate intake route (S1.3), so
resume parsing behaves identically whether a resume enters via POST /evaluate
or POST /candidates. Raises on malformed input — callers decide how to degrade.
"""

from __future__ import annotations

import base64
import io


def pdf_b64_to_text(b64: str) -> str:
    from pypdf import PdfReader  # deferred: pypdf import is not free at startup

    data = base64.b64decode(b64)
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def pdf_b64_to_document(b64: str) -> tuple[str, int, dict]:
    """Text, page count, and normalized metadata. S7.2 forensics need the
    metadata (producer tool, creation-vs-modification skew), which the
    text-only helper deliberately discards."""
    from pypdf import PdfReader

    data = base64.b64decode(b64)
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    raw = reader.metadata or {}
    meta = {
        "producer": raw.get("/Producer"),
        "creator": raw.get("/Creator"),
        "created": raw.get("/CreationDate"),
        "modified": raw.get("/ModDate"),
    }
    return text, len(reader.pages), {k: str(v) for k, v in meta.items() if v}
