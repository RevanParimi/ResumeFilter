"""Graph node factories.

Each ``make_*_node(services)`` returns an async ``node(state) -> dict`` that
closes over its injected :class:`~app.services.Services`. ``graph/build.py``
wires them in order; tests call them directly with fake services.
"""

from app.graph.nodes.claim_extraction import make_claim_extraction_node
from app.graph.nodes.ingest import make_ingest_node
from app.graph.nodes.plausibility import make_plausibility_node
from app.graph.nodes.probe_generation import make_probe_generation_node
from app.graph.nodes.provenance import make_provenance_node
from app.graph.nodes.report import make_report_node
from app.graph.nodes.scoring import make_scoring_node

__all__ = [
    "make_ingest_node",
    "make_claim_extraction_node",
    "make_provenance_node",
    "make_plausibility_node",
    "make_probe_generation_node",
    "make_scoring_node",
    "make_report_node",
]
