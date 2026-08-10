"""S8.5: the customer closes the loop on a report they paid for.

`POST /report/{id}/outcome` is the OPERATOR's route. Until this sprint there
was no org-plane equivalent, so a staffing agency that screened 400 resumes and
formed a judgment had nowhere to put it -- and that judgment is PI-9's
calibration input, the one thing that turns a reasoned default into a measured
one.

Everything here is tested from the OUTSIDE, over HTTP, on two organisations.
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN_HEADERS


@contextmanager
def _client(services):
    with TestClient(create_app(services), raise_server_exceptions=False,
                    headers=ADMIN_HEADERS) as c:
        yield c


def _key(services, name):
    org = services.ledger.create_organization(name)
    return org.id, services.ledger.issue_api_key(org.id)


def _upload(c, key, resume):
    up = c.post("/screening/candidates", headers={"X-Org-Key": key},
                json={"resume_text": resume, "domain": "genai"})
    assert up.status_code == 200, up.text
    return up.json()["report"]


# ── the loop closes ──────────────────────────────────────────────────────────


def test_an_org_records_an_outcome_and_reads_it_back(services, genuine_resume):
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        report = _upload(c, key, genuine_resume)

        assert c.get(
            f"/screening/reports/{report['id']}/outcomes",
            headers={"X-Org-Key": key},
        ).json()["outcomes"] == [], "a report nobody has judged lists nothing"

        rec = c.post(
            f"/screening/reports/{report['id']}/outcome",
            headers={"X-Org-Key": key},
            json={"outcome": "verified_fabricated",
                  "notes": "the employer had never heard of them"},
        )
        assert rec.status_code == 200, rec.text
        assert rec.json()["outcome"] == "verified_fabricated"
        assert rec.json()["report_id"] == report["id"]

        listed = c.get(
            f"/screening/reports/{report['id']}/outcomes",
            headers={"X-Org-Key": key},
        )
        assert listed.status_code == 200
        rows = listed.json()["outcomes"]
        assert len(rows) == 1
        assert rows[0]["outcome"] == "verified_fabricated"
        assert rows[0]["recorded_by"] == "organization"
        assert rows[0]["notes"] == "the employer had never heard of them"


def test_a_claim_level_outcome_names_a_claim_the_report_actually_has(
    services, genuine_resume
):
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        report = _upload(c, key, genuine_resume)
        claim_id = report["verdicts"][0]["claim_id"]

        ok = c.post(
            f"/screening/reports/{report['id']}/outcome",
            headers={"X-Org-Key": key},
            json={"outcome": "candidate_clarified", "claim_id": claim_id},
        )
        assert ok.status_code == 200
        assert ok.json()["claim_id"] == claim_id

        bad = c.post(
            f"/screening/reports/{report['id']}/outcome",
            headers={"X-Org-Key": key},
            json={"outcome": "verified_genuine", "claim_id": "clm_not_there"},
        )
        assert bad.status_code == 422
        assert "clm_not_there" in bad.text


def test_outcomes_are_append_only_and_ordered(services, genuine_resume):
    """A reviewer changing their mind is a fact, not a correction. Upsert would
    destroy the sequence of judgments -- which is precisely what a calibration
    harness wants to look at (did they flip after the interview?)."""
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        report = _upload(c, key, genuine_resume)
        for label in ("inconclusive", "candidate_clarified", "verified_genuine"):
            c.post(f"/screening/reports/{report['id']}/outcome",
                   headers={"X-Org-Key": key}, json={"outcome": label})

        rows = c.get(f"/screening/reports/{report['id']}/outcomes",
                     headers={"X-Org-Key": key}).json()["outcomes"]
        assert [r["outcome"] for r in rows] == [
            "inconclusive", "candidate_clarified", "verified_genuine",
        ]


# ── tenancy ──────────────────────────────────────────────────────────────────


def test_another_orgs_report_is_404_on_both_routes(services, genuine_resume):
    """Byte-identical to an unknown id, on BOTH verbs. A 403 anywhere here
    would confirm the report exists (TENANCY.md §6), and a write route is the
    easiest place to forget that -- the natural instinct is 403 on a refused
    write."""
    _, key_a = _key(services, "Agency A")
    _, key_b = _key(services, "Agency B")
    with _client(services) as c:
        report = _upload(c, key_a, genuine_resume)

        theirs_post = c.post(f"/screening/reports/{report['id']}/outcome",
                             headers={"X-Org-Key": key_b},
                             json={"outcome": "verified_genuine"})
        absent_post = c.post("/screening/reports/nope/outcome",
                             headers={"X-Org-Key": key_b},
                             json={"outcome": "verified_genuine"})
        theirs_get = c.get(f"/screening/reports/{report['id']}/outcomes",
                           headers={"X-Org-Key": key_b})
        absent_get = c.get("/screening/reports/nope/outcomes",
                           headers={"X-Org-Key": key_b})

        assert theirs_post.status_code == absent_post.status_code == 404
        assert theirs_post.json() == absent_post.json()
        assert theirs_get.status_code == absent_get.status_code == 404
        assert theirs_get.json() == absent_get.json()

        # And the refused write wrote nothing.
        assert c.get(f"/screening/reports/{report['id']}/outcomes",
                     headers={"X-Org-Key": key_a}).json()["outcomes"] == []


def test_an_operators_note_is_invisible_to_the_customer(services, genuine_resume):
    """The leak this route could plausibly introduce is DOWNWARD, not sideways.
    A report has exactly one owning org, so no other customer can reach it --
    but the operator's own internal note lives on the same report."""
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        report = _upload(c, key, genuine_resume)

        admin = c.post(f"/report/{report['id']}/outcome",
                       json={"outcome": "inconclusive",
                             "notes": "internal: this agency keeps uploading fakes"})
        assert admin.status_code == 200

        mine = c.get(f"/screening/reports/{report['id']}/outcomes",
                     headers={"X-Org-Key": key}).json()["outcomes"]
        assert mine == []
        assert "internal" not in str(mine)

        # The operator's cross-tenant view still sees everything, which is what
        # it is for.
        everything = c.get(f"/report/{report['id']}/outcomes").json()["outcomes"]
        assert len(everything) == 1


def test_an_unowned_report_is_404_even_for_an_org_that_uploaded_the_person(
    services, genuine_resume
):
    """A report the ADMIN plane created belongs to nobody, not to everybody
    (TENANCY.md §4) -- and no special case in the route says so; `NULL = 'org'`
    is false in SQL."""
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        admin_report = c.post("/candidates",
                              json={"resume_text": genuine_resume,
                                    "domain": "genai"}).json()["report"]

        refused = c.post(f"/screening/reports/{admin_report['id']}/outcome",
                         headers={"X-Org-Key": key},
                         json={"outcome": "verified_genuine"})
        assert refused.status_code == 404


# ── the bound, at the second door ────────────────────────────────────────────


def test_the_org_door_enforces_the_same_notes_cap(services, genuine_resume):
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        report = _upload(c, key, genuine_resume)
        over = "x" * (services.settings.max_outcome_notes_chars + 1)

        resp = c.post(f"/screening/reports/{report['id']}/outcome",
                      headers={"X-Org-Key": key},
                      json={"outcome": "inconclusive", "notes": over})
        assert resp.status_code == 422
        assert "max_outcome_notes_chars" in resp.text
        assert c.get(f"/screening/reports/{report['id']}/outcomes",
                     headers={"X-Org-Key": key}).json()["outcomes"] == []


def test_both_doors_refuse_the_same_inputs(services, genuine_resume):
    """"Both doors call the helper" is a claim about today's source. "Both
    doors refuse the same input" is a claim about behaviour, and it is the one
    that survives somebody rewriting a handler."""
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        report = _upload(c, key, genuine_resume)
        over = "x" * (services.settings.max_outcome_notes_chars + 1)

        for payload in (
            {"outcome": "inconclusive", "notes": over},
            {"outcome": "inconclusive", "claim_id": "clm_not_there"},
        ):
            admin = c.post(f"/report/{report['id']}/outcome", json=payload)
            org = c.post(f"/screening/reports/{report['id']}/outcome",
                         headers={"X-Org-Key": key}, json=payload)
            assert admin.status_code == org.status_code == 422, payload
            assert admin.json()["detail"] == org.json()["detail"], payload


# ── DPDP ─────────────────────────────────────────────────────────────────────


def test_erasing_the_candidate_destroys_the_judgment(services, genuine_resume):
    """Through the real foreign keys, with nobody remembering to: outcomes ->
    reports -> candidates, both CASCADE. The notes are the only free text this
    sprint adds, and this is what reaches them."""
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        up = c.post("/screening/candidates", headers={"X-Org-Key": key},
                    json={"resume_text": genuine_resume, "domain": "genai"})
        body = up.json()
        report_id, candidate_id = body["report"]["id"], body["candidate_id"]

        c.post(f"/screening/reports/{report_id}/outcome",
               headers={"X-Org-Key": key},
               json={"outcome": "verified_fabricated", "notes": "they admitted it"})
        assert len(services.report_store.outcomes(report_id)) == 1

        assert services.candidates.delete_candidate(candidate_id) is True
        assert services.report_store.outcomes(report_id) == []


def test_the_flywheel_gets_the_label_and_provenance_but_not_the_note(
    services, genuine_resume
):
    org_id, key = _key(services, "Agency A")
    with _client(services) as c:
        report = _upload(c, key, genuine_resume)
        c.post(f"/screening/reports/{report['id']}/outcome",
               headers={"X-Org-Key": key},
               json={"outcome": "verified_fabricated",
                     "notes": "they admitted it on the call"})

    rows = [r for r in services.flywheel.records if r.get("record_type") == "outcome"]
    assert len(rows) == 1
    assert rows[0]["outcome"] == "verified_fabricated"
    assert rows[0]["recorded_by"] == "organization"
    assert rows[0]["org_id"] == org_id
    assert "notes" not in rows[0]
    assert "admitted" not in str(rows[0])


def test_a_machine_caller_records_no_human(services, genuine_resume):
    """X-Org-Key is an ORGANISATION credential with no human behind it.
    Inventing one would be a false audit trail -- the same decision, and the
    same words, as screening_batches.created_by_org_user_id."""
    _, key = _key(services, "Agency A")
    with _client(services) as c:
        report = _upload(c, key, genuine_resume)
        c.post(f"/screening/reports/{report['id']}/outcome",
               headers={"X-Org-Key": key}, json={"outcome": "inconclusive"})

    stored = services.report_store.outcomes(report["id"])[0]
    assert stored.recorded_by_org_user_id is None
    assert stored.recorded_by.value == "organization"
