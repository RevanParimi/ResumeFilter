"""S5.2 CompService — estimate (static-only + blended) and requisition benchmark."""

from datetime import datetime, timedelta, timezone

import pytest

import app.candidates.models  # noqa: F401 — populate Base.metadata
import app.ledger.models  # noqa: F401 — populate Base.metadata
from app.candidates.models import CandidateRow
from app.comp.schema import RoleSignal, SeniorityBand
from app.comp.service import CompService
from app.core.config import Settings
from app.core.db import Base, make_engine, make_session_factory
from app.ledger.schema import ConsentPurpose
from app.ledger.store import LedgerStore
from app.matching.schema import CompBand, JobRequisition, RequisitionStatus

NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)
SENIOR_BACKEND = RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.SENIOR, city_tier="metro")


@pytest.fixture()
def ctx():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    sf = make_session_factory(engine)
    ledger = LedgerStore(sf, default_consent_ttl_days=365)
    return sf, ledger, CompService(ledger, settings=Settings())


def _candidate(sf) -> str:
    with sf() as s:
        c = CandidateRow()
        s.add(c)
        s.commit()
        return c.id


def test_estimate_static_only_then_shifts_with_offers(ctx):
    sf, ledger, svc = ctx
    org = ledger.create_organization("Acme")
    static = svc.estimate(SENIOR_BACKEND, org_id=org.id, as_of=NOW)
    assert static.sources == ("static",)
    for _ in range(6):
        cid = _candidate(sf)
        ledger.grant_consent(candidate_id=cid, purpose=ConsentPurpose.LEDGER_WRITE,
                             org_id=org.id, expires_at=NOW + timedelta(days=90), now=NOW)
        ledger.submit_observed_offer(
            org_id=org.id, candidate_id=cid, role_family="backend_engineer",
            seniority="senior", city_tier="metro", ctc_fixed=4_000_000.0, offered_at=NOW, now=NOW,
        )
    blended = svc.estimate(SENIOR_BACKEND, org_id=org.id, as_of=NOW)
    assert blended.sources == ("static", "observed")
    assert blended.n_observed == 6
    assert blended.p50 > static.p50


def test_benchmark_from_requisition(ctx):
    sf, ledger, svc = ctx
    org = ledger.create_organization("Acme")
    est = svc.estimate(SENIOR_BACKEND, org_id=org.id, as_of=NOW)
    low = est.p50 * 0.5
    req = JobRequisition(
        id="r1", org_id=org.id, title="Senior Backend Engineer",
        status=RequisitionStatus.OPEN, must_have_skills=("python",), nice_to_have_skills=(),
        min_years_experience=7.0, location_tiers=("metro",), remote=False,
        comp_band=CompBand(ctc_min=low * 0.9, ctc_max=low * 1.1),
        created_at=NOW, updated_at=NOW,
    )
    bench = svc.benchmark(req, org_id=org.id, as_of=NOW)
    assert bench.position == "below"
    assert bench.estimate.role_family == "backend_engineer"
