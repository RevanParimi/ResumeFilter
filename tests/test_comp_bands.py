"""S5.2 static comp bands + deterministic role-signal resolvers."""

from datetime import datetime, timezone

from app.core.config import Settings
from app.comp import bands
from app.comp.schema import RoleSignal, SeniorityBand
from app.matching.schema import JobRequisition, RequisitionStatus


def _s() -> Settings:
    return Settings()


def test_lookup_cell_monotonic_in_seniority_and_tier():
    s = _s()
    jr = bands.lookup_cell(RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.JUNIOR, city_tier="metro"), s)
    sr = bands.lookup_cell(RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.SENIOR, city_tier="metro"), s)
    t2 = bands.lookup_cell(RoleSignal(role_family="backend_engineer", seniority=SeniorityBand.SENIOR, city_tier="tier_2"), s)
    assert sr[1] > jr[1]          # senior mid > junior mid
    assert t2[1] < sr[1]          # tier_2 < metro
    assert jr[0] < jr[1] < jr[2]  # low < mid < high
    assert 0.0 <= jr[3] < 1.0     # variable fraction in range


def test_resolve_role_family_title_then_skills_then_default():
    s = _s()
    assert bands.resolve_role_family((), "Senior Frontend Engineer", s) == "frontend_engineer"
    assert bands.resolve_role_family(("react", "css"), None, s) == "frontend_engineer"
    assert bands.resolve_role_family(("kubernetes", "terraform"), None, s) == "devops_sre"
    assert bands.resolve_role_family((), None, s) == "backend_engineer"  # default


def test_resolve_seniority_thresholds():
    s = _s()
    assert bands.resolve_seniority(1.0, s) is SeniorityBand.JUNIOR
    assert bands.resolve_seniority(3.0, s) is SeniorityBand.MID
    assert bands.resolve_seniority(7.0, s) is SeniorityBand.SENIOR
    assert bands.resolve_seniority(12.0, s) is SeniorityBand.LEAD
    assert bands.resolve_seniority(None, s) is SeniorityBand.MID  # unknown -> neutral


def test_resolve_city_tier_remote_and_unknown_default_metro():
    s = _s()
    assert bands.resolve_city_tier(("tier_2",), False, s) == "tier_2"
    assert bands.resolve_city_tier(None, True, s) == "metro"
    assert bands.resolve_city_tier((), False, s) == "metro"


def test_role_signal_from_requisition():
    s = _s()
    req = JobRequisition(
        id="r1", org_id="o1", title="Backend Engineer",
        status=RequisitionStatus.OPEN, must_have_skills=("python",),
        nice_to_have_skills=(), min_years_experience=6.0,
        location_tiers=("metro",), remote=False,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    sig = bands.role_signal_from_requisition(req, s)
    assert sig.role_family == "backend_engineer"
    assert sig.seniority is SeniorityBand.SENIOR
    assert sig.city_tier == "metro"


def test_role_signal_from_input_overrides_win():
    s = _s()
    sig = bands.role_signal_from_input(
        skills=("react",), title="Frontend Engineer", years=1.0,
        location_tiers=None, remote=True,
        role_family="ml_engineer", seniority=SeniorityBand.LEAD, settings=s,
    )
    assert sig.role_family == "ml_engineer"      # override beats title/skills
    assert sig.seniority is SeniorityBand.LEAD    # override beats years
    assert sig.city_tier == "metro"               # remote -> metro
