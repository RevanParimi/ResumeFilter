from app.matching.schema import JobRequisitionInput


def _org(services, name="Acme"):
    return services.ledger.create_organization(name).id


def test_board_cross_org_is_none(services):
    a = _org(services, "A")
    b = _org(services, "B")
    req = services.jobs.create_requisition(a, JobRequisitionInput(
        title="A-req", must_have_skills=("python",)))
    assert services.dashboard.board(b, req.id) is None


def test_board_composes_req_comp_and_empty_match(services):
    org_id = _org(services)
    req = services.jobs.create_requisition(org_id, JobRequisitionInput(
        title="Senior Backend Engineer", must_have_skills=("python",),
        min_years_experience=7, location_tiers=("metro",),
        comp_band={"ctc_min": 800000, "ctc_max": 900000},
    ))
    board = services.dashboard.board(org_id, req.id)
    assert board is not None
    assert board.requisition.id == req.id
    assert board.comp.advisory is True                 # comp benchmark composed
    assert board.match.pool_size == 0                  # nothing materialized -> empty
    assert board.match.ranked == ()
    assert board.advisory is True
