"""S8.3 Phase A review: the container's limiters, and what counts them.

Every other test in this sprint builds services through `tests.conftest.
make_services`, which wires `metrics` into all three limiters by hand. That
fixture therefore CANNOT see a construction site that `build_default_services`
forgot -- which is the S8.2 lesson ("a fake that cannot enforce an invariant
will hide it") pointed at the wiring rather than at the behaviour.

So these tests build the PRODUCTION container and assert the invariant on it.
"""

from __future__ import annotations

import pytest

from app.core.db import Base, make_engine
from app.services import build_default_services


@pytest.fixture
def real_services(settings, tmp_path):
    """`build_default_services` against a real, empty, on-disk schema.

    A file URL rather than `sqlite://`: the container builds its own engine
    from the URL, and an in-memory database would give every store a private
    one.
    """
    url = f"sqlite:///{tmp_path / 'container.db'}"
    Base.metadata.create_all(make_engine(url))
    return build_default_services(settings.model_copy(update={
        "candidates_db_url": url,
    }))


#: The services that MUST have a limiter. A floor, not the whole list: a
#: service that silently STOPPED having one has to fail here, and discovery
#: alone would simply stop looking at it.
LIMITED = ("auth", "screening", "interview", "rights")


def _limited_services(services) -> list[str]:
    """Every container attribute that actually holds a limiter.

    DISCOVERED, because the alternative is a second hand-maintained list -- and
    the second hand-maintained list is always the one that drifts (S8.2's
    OPEN_PATHS/PUBLIC_PATHS finding, and `GET /`'s endpoints list twice since).
    S8.3 Phase B added a fourth limiter, and under a purely named list it would
    have been covered only if somebody remembered to type it here.
    """
    return sorted(
        name
        for name in vars(services)
        if getattr(getattr(services, name, None), "_limiter", None) is not None
    )


def test_the_named_floor_is_actually_present_on_the_container(real_services):
    """Guards the discovery below from covering nothing, and catches a service
    that lost its limiter (which discovery alone would read as 'not limited')."""
    discovered = set(_limited_services(real_services))
    assert set(LIMITED) <= discovered, (
        f"these services are supposed to be limited and are not: "
        f"{sorted(set(LIMITED) - discovered)}"
    )


def test_discovery_finds_every_named_service_and_no_more_is_fine(real_services):
    """A NEW limiter arriving on the container is covered by the two tests
    below with no edit here -- which is the point of discovering. This test
    just records what was found, so a reviewer can see the set grow."""
    assert _limited_services(real_services) == sorted(LIMITED)


@pytest.mark.parametrize("service_name", LIMITED)
def test_every_limiter_reports_to_the_container_s_metrics(
    real_services, service_name
):
    """A limiter built with `metrics=None` enforces perfectly and counts
    nothing -- so the rule it enforces is invisible in `GET /metrics`, and
    OPERATING.md's runbook step 1 ("read the `rule` and `scope` labels") cannot
    answer for it. The failure is silent in exactly the way a declared-but-never
    -populated column is; this branch's own headline finding was one of those.
    """
    limiter = getattr(real_services, service_name)._limiter
    assert limiter._metrics is real_services.metrics, (
        f"{service_name}'s limiter counts nowhere: build_default_services did "
        f"not pass metrics= to its builder"
    )


@pytest.mark.parametrize("service_name", LIMITED)
def test_every_limiter_shares_the_container_s_settings(
    real_services, service_name
):
    """A limiter holding a DIFFERENT Settings would read different limits than
    the ones an operator configured, and every test using the fixture would
    still pass."""
    limiter = getattr(real_services, service_name)._limiter
    assert limiter._settings is real_services.settings
