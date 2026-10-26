"""ingest — parse the resume to normalized text; capture shared links.

Deterministic and LLM-free. Accepts raw text or a base64 PDF. The optional
github_url / portfolio_url are first-party links the candidate chose to share.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.resume import read_resume_input_async
from app.graph.state import EvaluationState
from app.services import Services


def make_ingest_node(services: Services):
    log = get_logger("node.ingest")

    async def ingest(state: EvaluationState) -> dict:
        text = await read_resume_input_async(executor=services.pdf,
            resume_text=state.raw_resume_text, resume_pdf_b64=state.resume_pdf_b64,
            settings=services.settings,
        )

        log.info("ingested", chars=len(text), has_github=bool(state.github_url))
        return {"resume_text": text}

    return ingest
