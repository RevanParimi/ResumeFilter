"""S3.2 ledger HTTP surface — offline TestClient over injected in-memory stores."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.candidates.extractor import extract_profile
from app.candidates.store import CandidateStore
from app.ledger.store import LedgerStore
from app.main import create_app
from tests.conftest import make_services

RESUME = """Asha Rao
Email: asha.rao@example.com | Phone: +91 98765 43210

EXPERIENCE
- Senior ML Engineer, Acme AI (2021 - Present)

SKILLS
Python, PyTorch
"""


def test_services_bundle_has_ledger_sharing_candidate_db(services):
    assert isinstance(services.ledger, LedgerStore)
    assert isinstance(services.candidates, CandidateStore)
