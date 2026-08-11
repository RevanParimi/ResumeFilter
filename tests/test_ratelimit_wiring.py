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


#: Every service the sprint gave a limiter to. Named rather than discovered,
#: because a service that silently STOPPED having a limiter must fail here too.
LIMITED = ("auth", "screening", "interview")


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
