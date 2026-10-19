"""A stale contact match is a retryable batch refusal, never internal error."""

import pytest
from sqlalchemy import select

from app.candidates.models import CandidateRow
from app.candidates.store import AssertedContactChangedError
from app.graph.build import EvaluationEngine


@pytest.mark.asyncio
async def test_batch_records_stale_match_and_retries_without_partial_candidate(services, monkeypatch):
    org = services.ledger.create_organization('Agency A').id
    other_org = services.ledger.create_organization('Agency B').id
    batch = services.screening.register(org, name='Contacts', domain='genai',
        texts=['Synthetic candidate\nEmail: owner@example.in\nSKILLS\nPython\n'],
        created_by_org_user_id=None)
    ingest = services.candidates.ingest
    engine = EvaluationEngine(services)

    def refuse(*args, **kwargs):
        raise AssertedContactChangedError()

    with monkeypatch.context() as patch:
        patch.setattr(services.candidates, 'ingest', refuse)
        result = await services.screening.process(org, batch.id, engine=engine)
    assert (result.processed, result.failed) == (0, 1)
    queue = services.screening.queue(org, batch.id, cursor=None, limit=None)
    assert queue.rows[0].error == 'candidate_contact_changed'
    assert queue.rows[0].candidate_id is queue.rows[0].resume_id is None
    with services.session_factory() as session:
        assert session.scalar(select(CandidateRow.id)) is None
    assert services.screening.retry(other_org, batch.id) is None
    assert services.screening.retry(org, batch.id).requeued == 1
    assert services.candidates.ingest == ingest
    success = await services.screening.process(org, batch.id, engine=engine)
    assert (success.processed, success.failed) == (1, 0)
    assert services.screening.get(org, batch.id).counts.done == 1
