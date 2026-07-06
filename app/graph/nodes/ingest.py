"""ingest — parse the resume to normalized text; capture shared links.

Deterministic and LLM-free. Accepts raw text or a base64 PDF. The optional
github_url / portfolio_url are first-party links the candidate chose to share.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.pdf import pdf_b64_to_text
from app.graph.state import EvaluationState
from app.services import Services


def make_ingest_node(services: Services):
    log = get_logger("node.ingest")

    async def ingest(state: EvaluationState) -> dict:
        text = state.raw_resume_text
        if not text and state.resume_pdf_b64:
            try:
                text = pdf_b64_to_text(state.resume_pdf_b64)
            except Exception as exc:  # malformed PDF: record, don't crash pipeline
                log.warning("pdf_parse_failed", error=str(exc))
                return {"errors": [f"pdf_parse_failed: {exc}"], "resume_text": ""}

        text = (text or "").strip()
        if not text:
            return {"errors": ["empty_resume"], "resume_text": ""}

        log.info("ingested", chars=len(text), has_github=bool(state.github_url))
        return {"resume_text": text}

    return ingest
