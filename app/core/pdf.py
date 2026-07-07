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
