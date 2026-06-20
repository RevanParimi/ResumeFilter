"""ingest — parse the resume to normalized text; capture shared links.

Deterministic and LLM-free. Accepts raw text or a base64 PDF. The optional
github_url / portfolio_url are first-party links the candidate chose to share.
"""

from __future__ import annotations

import base64
import io

from app.core.logging import get_logger
from app.graph.state import EvaluationState
from app.services import Services


def _parse_pdf(b64: str) -> str:
    from pypdf import PdfReader

    data = base64.b64decode(b64)
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def make_ingest_node(services: Services):
    log = get_logger("node.ingest")

    async def ingest(state: EvaluationState) -> dict:
        text = state.raw_resume_text
        if not text and state.resume_pdf_b64:
            try:
                text = _parse_pdf(state.resume_pdf_b64)
            except Exception as exc:  # malformed PDF: record, don't crash pipeline
                log.warning("pdf_parse_failed", error=str(exc))
                return {"errors": [f"pdf_parse_failed: {exc}"], "resume_text": ""}

        text = (text or "").strip()
        if not text:
            return {"errors": ["empty_resume"], "resume_text": ""}

        log.info("ingested", chars=len(text), has_github=bool(state.github_url))
        return {"resume_text": text}

    return ingest
