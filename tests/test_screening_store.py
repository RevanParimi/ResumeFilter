"""S8.4 Phase B: the batch store.

Two properties here are worth more than the rest: an item cannot be claimed
twice (each claim is a paid graph run), and a batch that belongs to somebody
else is indistinguishable from one that does not exist.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.screening.schema import ItemSignals, ItemStatus
from app.screening.store import ScreeningStore

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(services) -> ScreeningStore:
    return ScreeningStore(services.candidates._session_factory)


def _org(services, name="Acme Staffing"):
    return services.ledger.create_organization(name).id


def test_register_creates_items_and_nothing_else(store, services):
    org = _org(services)
    bid = store.create_batch(org, name="Q3", domain="genai",
                             created_by_org_user_id=None,
                             texts=["resume one", "resume two"])
    counts = store.counts(org, bid, now=NOW)
    assert counts.pending == 2 and counts.total == 2
    assert store.batch_row(org, bid).name == "Q3"


def test_another_orgs_batch_is_invisible_everywhere(store, services):
    a, b = _org(services, "A"), _org(services, "B")
    bid = store.create_batch(a, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["t"])
    assert store.batch_row(b, bid) is None
    assert store.counts(b, bid, now=NOW) is None
    assert store.queue_page(b, bid, cursor=None, limit=10, now=NOW) is None
    assert store.claim(b, bid, limit=5, now=NOW, timeout_seconds=900) == []
    assert store.delete_batch(b, bid) is False
    assert store.batch_row(a, bid) is not None, "and A still has it"


def test_claim_is_bounded_and_marks_items_processing(store, services):
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None,
                             texts=[f"resume {i}" for i in range(5)])
    claimed = store.claim(org, bid, limit=2, now=NOW, timeout_seconds=900)
    assert len(claimed) == 2
    assert all(c.raw_text for c in claimed)
    counts = store.counts(org, bid, now=NOW)
    assert (counts.processing, counts.pending) == (2, 3)


def test_an_item_cannot_be_claimed_twice(store, services):
    """The whole reason the claim is a conditional UPDATE: each item is a full
    nine-node graph run, and on a live model a double claim is double money."""
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["only one"])
    first = store.claim(org, bid, limit=5, now=NOW, timeout_seconds=900)
    second = store.claim(org, bid, limit=5, now=NOW, timeout_seconds=900)
    assert len(first) == 1 and second == []


def test_a_stale_claim_is_reclaimed_and_reads_as_pending(store, services):
    """Spec §4.4: a batch interrupted by a redeploy heals itself instead of
    wedging with items nobody will ever claim."""
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["one"])
    store.claim(org, bid, limit=1, now=NOW, timeout_seconds=900)

    later = NOW + timedelta(seconds=901)
    assert store.counts(org, bid, now=later).pending == 1, (
        "a read reinterprets a stale claim; it never rewrites the row"
    )
    again = store.claim(org, bid, limit=1, now=later, timeout_seconds=900)
    assert len(again) == 1


def test_complete_clears_the_text_and_stamps_the_signals(store, services):
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["one"])
    item = store.claim(org, bid, limit=1, now=NOW, timeout_seconds=900)[0]
    store.complete(item.id, lease=item.claimed_at, candidate_id=None,
                   resume_id=None, report_id=None,
                   risk_score=0.8, signals=ItemSignals(risk_confidence=0.5), at=NOW)

    rows = store.all_items(org, bid, now=NOW)
    assert rows[0].status is ItemStatus.DONE
    assert rows[0].raw_text == "", (
        "the text now lives in `resumes`, where candidate erasure cascades"
    )
    assert rows[0].risk_score == 0.8
    assert rows[0].signals.risk_confidence == 0.5


def test_fail_keeps_the_text_so_the_org_can_retry(store, services):
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["one"])
    item = store.claim(org, bid, limit=1, now=NOW, timeout_seconds=900)[0]
    store.fail(item.id, lease=item.claimed_at, error="empty_resume", at=NOW)

    rows = store.all_items(org, bid, now=NOW)
    assert rows[0].status is ItemStatus.FAILED
    assert rows[0].raw_text == "one", "failure is not a reason to destroy the input"
    assert rows[0].error == "empty_resume"


def test_unreadable_signals_degrade_to_none_rather_than_raising(store, services):
    """S7.3's finding: one unparseable stored blob must not brick every later
    read of the batch it belongs to."""
    from sqlalchemy import update
    from app.screening.models import BatchItemRow

    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["one"])
    item = store.claim(org, bid, limit=1, now=NOW, timeout_seconds=900)[0]
    store.complete(item.id, lease=item.claimed_at, candidate_id=None,
                   resume_id=None, report_id=None,
                   risk_score=0.4, signals=ItemSignals(), at=NOW)
    with services.candidates._session_factory() as s:
        s.execute(update(BatchItemRow).where(BatchItemRow.id == item.id)
                  .values(signals={"risk_band": "not-a-band"}))
        s.commit()

    rows = store.all_items(org, bid, now=NOW)
    assert rows[0].signals is None
    assert rows[0].risk_score == 0.4, "the sort key is a real column and survives"


def test_the_queue_is_ranked_by_risk_with_unscored_items_last(store, services):
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None,
                             texts=["a", "b", "c"])
    claimed = store.claim(org, bid, limit=2, now=NOW, timeout_seconds=900)
    store.complete(claimed[0].id, lease=claimed[0].claimed_at, candidate_id=None,
                   resume_id=None, report_id=None,
                   risk_score=0.3, signals=ItemSignals(), at=NOW)
    store.complete(claimed[1].id, lease=claimed[1].claimed_at, candidate_id=None,
                   resume_id=None, report_id=None,
                   risk_score=0.9, signals=ItemSignals(), at=NOW)

    rows, _ = store.queue_page(org, bid, cursor=None, limit=10, now=NOW)
    assert [r.risk_score for r in rows] == [0.9, 0.3, None]
    assert rows[-1].status is ItemStatus.PENDING, "unscreened rows are shown, last"


def test_paging_across_an_insert_neither_skips_nor_duplicates(store, services):
    """The reason the cursor is a keyset position rather than an offset."""
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["a", "b", "c"])
    items = store.claim(org, bid, limit=3, now=NOW, timeout_seconds=900)
    for item, score in zip(items, (0.9, 0.6, 0.3)):
        store.complete(item.id, lease=item.claimed_at, candidate_id=None,
                       resume_id=None, report_id=None,
                       risk_score=score, signals=ItemSignals(), at=NOW)

    first, cursor = store.queue_page(org, bid, cursor=None, limit=2, now=NOW)
    assert cursor is not None

    # A new item lands between the two page reads.
    store.add_items(org, bid, texts=["late arrival"])

    second, _ = store.queue_page(org, bid, cursor=cursor, limit=10, now=NOW)
    seen = [r.item_id for r in first] + [r.item_id for r in second]
    assert len(seen) == len(set(seen)), "no row served twice"
    assert {r.id for r in items} <= set(seen), "no scored row skipped"


def test_a_cursor_from_another_batch_cannot_reach_its_rows(store, services):
    """A cursor is a sort POSITION, not a capability -- the org_id/batch_id
    filter is what protects the boundary."""
    org = _org(services)
    mine = store.create_batch(org, name="mine", domain="genai",
                              created_by_org_user_id=None, texts=["a", "b"])
    other = store.create_batch(org, name="other", domain="genai",
                               created_by_org_user_id=None, texts=["c", "d"])
    _, cursor = store.queue_page(org, mine, cursor=None, limit=1, now=NOW)

    rows, _ = store.queue_page(org, other, cursor=cursor, limit=10, now=NOW)
    other_ids = {r.item_id for r in store.all_items(org, other, now=NOW)}
    assert {r.item_id for r in rows} <= other_ids


def test_delete_removes_items_and_their_text(store, services):
    from sqlalchemy import func, select
    from app.screening.models import BatchItemRow

    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["a", "b"])
    assert store.delete_batch(org, bid) is True
    assert store.batch_row(org, bid) is None
    with services.candidates._session_factory() as s:
        assert s.execute(select(func.count()).select_from(BatchItemRow)).scalar() == 0


def test_list_batches_is_newest_first_and_pages(store, services):
    org = _org(services)
    ids = [
        store.create_batch(org, name=f"b{i}", domain="genai",
                           created_by_org_user_id=None, texts=["t"])
        for i in range(3)
    ]
    page, cursor = store.list_batches(org, cursor=None, limit=2)
    assert len(page) == 2 and cursor is not None
    rest, _ = store.list_batches(org, cursor=cursor, limit=10)
    assert {b.id for b in page} | {b.id for b in rest} == set(ids)


def test_a_lost_lease_cannot_overwrite_the_winners_result(store, services):
    """The claim's race-safety, one step later. Claim call A blows past the
    timeout mid-run (five slow graph runs), B legitimately re-claims the item
    and completes it. A then finishes and writes back.

    Without a lease check, A's late `fail` lands on top of B's result: status
    FAILED and an error code beside B's risk_score and signals, with raw_text
    already cleared -- a contradictory row the org can neither trust nor
    retry. The claim was conditional; the write-back must be too.
    """
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["only one"])
    a = store.claim(org, bid, limit=1, now=NOW, timeout_seconds=900)[0]

    later = NOW + timedelta(seconds=901)
    b = store.claim(org, bid, limit=1, now=later, timeout_seconds=900)[0]
    assert b.id == a.id, "the stale claim was re-claimable"

    # A writes back while B still HOLDS the row. The row's status is still
    # `processing`, so ONLY the lease clause can refuse this -- the assertion
    # that kills the mutant deleting `claimed_at == lease` from the WHERE.
    assert store.fail(a.id, lease=a.claimed_at, error="internal_error",
                      at=later) is False

    assert store.complete(
        b.id, lease=b.claimed_at, candidate_id=None, resume_id=None,
        report_id=None, risk_score=0.7, signals=ItemSignals(), at=later,
    ) is True

    assert store.complete(
        a.id, lease=a.claimed_at, candidate_id=None, resume_id=None,
        report_id=None, risk_score=0.2, signals=ItemSignals(), at=later,
    ) is False

    row = store.all_items(org, bid, now=later)[0]
    assert row.status is ItemStatus.DONE
    assert row.risk_score == 0.7, "the live claimant's result stands"
    assert row.error is None


def test_the_conditional_update_refuses_an_item_claimed_since_the_select(store, services):
    """Two tabs both POST .../process; both SELECTs see the same pending row.
    The UPDATE that claims it re-asserts claimability, so only one wins.

    Driven at the store on purpose. The race is UNREACHABLE through two
    sequential `claim` calls -- the second call's own SELECT filters the row
    out before the UPDATE is ever reached -- so mutation testing found that
    deleting the UPDATE's WHERE clause, or relaxing `rowcount == 1`, survived
    every end-to-end test. This is the same shape as S8.2's two-challenge
    lockout test: an invariant the public API cannot reach needs a test that
    builds the state directly.
    """
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["only one"])
    item = store.claim(org, bid, limit=1, now=NOW, timeout_seconds=900)[0]

    # A second worker holding an id it selected BEFORE the claim above landed.
    with services.candidates._session_factory() as s:
        won = store._try_claim(
            s, item.id, claimable=store._claimable(NOW, 900), now=NOW
        )
        s.commit()
    assert won is False, "the loser of the race must not get a paid graph run"


def test_the_conditional_update_wins_when_the_item_really_is_claimable(store, services):
    """The other direction: the guard above must refuse a TAKEN item, not
    every item -- a claim that never succeeds is a batch that never runs."""
    org = _org(services)
    bid = store.create_batch(org, name="x", domain="genai",
                             created_by_org_user_id=None, texts=["only one"])
    with services.candidates._session_factory() as s:
        item_id = s.execute(
            __import__("sqlalchemy").select(
                __import__("app.screening.models", fromlist=["BatchItemRow"]).BatchItemRow.id
            )
        ).scalars().one()
        won = store._try_claim(
            s, item_id, claimable=store._claimable(NOW, 900), now=NOW
        )
        s.commit()
    assert won is True
