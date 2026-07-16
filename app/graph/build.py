"""Assemble the LangGraph pipeline.

The graph is DOMAIN-AGNOSTIC: it wires the seven nodes in order and never
references GenAI. Domain selection happens at runtime via ``state.domain`` and
the registry. Importing ``app.domains`` registers the built-in domains.

    ingest → ai_signals → claim_extraction → provenance → plausibility
           → probe_generation → scoring → report
"""

from __future__ import annotations

from typing import Optional

from langgraph.graph import END, START, StateGraph

import app.domains  # noqa: F401  (registers domains on import)
from app.core.logging import get_logger
from app.graph.nodes import (
    make_ai_signals_node,
    make_claim_extraction_node,
    make_ingest_node,
    make_plausibility_node,
    make_probe_generation_node,
    make_provenance_node,
    make_report_node,
    make_scoring_node,
)
from app.graph.state import EvaluationState
from app.schemas.report import Report
from app.services import Services, build_default_services

log = get_logger("graph.build")

_PIPELINE = [
    ("ingest", make_ingest_node),
    ("ai_signals", make_ai_signals_node),
    ("claim_extraction", make_claim_extraction_node),
    ("provenance", make_provenance_node),
    ("plausibility", make_plausibility_node),
    ("probe_generation", make_probe_generation_node),
    ("scoring", make_scoring_node),
    ("report", make_report_node),
]


def build_graph(services: Services):
    """Compile the LangGraph for the given service bundle."""
    g = StateGraph(EvaluationState)
    names = [name for name, _ in _PIPELINE]
    for name, factory in _PIPELINE:
        g.add_node(name, factory(services))

    g.add_edge(START, names[0])
    for prev, nxt in zip(names, names[1:]):
        g.add_edge(prev, nxt)
    g.add_edge(names[-1], END)
    return g.compile()


class EvaluationEngine:
    """Compiled graph + services; the API and tests run evaluations through this."""

    def __init__(self, services: Optional[Services] = None) -> None:
        self.services = services or build_default_services()
        self.graph = build_graph(self.services)

    async def evaluate(
        self,
        *,
        resume_text: Optional[str] = None,
        resume_pdf_b64: Optional[str] = None,
        github_url: Optional[str] = None,
        portfolio_url: Optional[str] = None,
        domain: str = "genai",
    ) -> Report:
        initial = EvaluationState(
            domain=domain,
            raw_resume_text=resume_text,
            resume_pdf_b64=resume_pdf_b64,
            github_url=github_url,
            portfolio_url=portfolio_url,
        )
        result = await self.graph.ainvoke(initial)
        # LangGraph returns the final state (dict-like or model depending on version).
        final = result if isinstance(result, EvaluationState) else EvaluationState(**result)
        if final.report is None:  # defensive: never return nothing
            raise RuntimeError(f"pipeline produced no report; errors={final.errors}")
        return final.report

    def close(self) -> None:
        github = getattr(self.services, "github", None)
        aclose = getattr(github, "aclose", None)
        if aclose:  # best-effort async client cleanup is handled by caller/lifespan
            return
