"""Present authorization at export/join boundaries, independent of stored cuts."""

import csv
import builtins
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event

import pytest

from app.features import default_view, get_feature_registry
from app.features.export import (export_view_csv, export_view_parquet,
                                 export_training_csv, export_training_parquet, ParquetUnavailable)
from app.features.materialize import MaterializedVector
from app.features.schema import FeatureVector
from app.features.store import FeatureStore
from app.features.training import build_training_set
from app.candidates.store import CandidateStore
from app.ledger.models import ConsentGrantRow
from app.ledger.store import LedgerStore
from sqlalchemy import update
from tests.test_report_erasure_concurrency import database  # noqa: F401

CUT = datetime(2026, 1, 2, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)


def seed(factory):
    ledger, features = LedgerStore(factory), FeatureStore(factory)
    orgs = [ledger.create_organization(name) for name in ('A', 'B')]
    grants = []
    for cid, org in zip(('a', 'b'), orgs):
        ledger.grant_consent(candidate_id=cid, purpose='ledger_write', org_id=org.id,
                             now=CUT - timedelta(days=1), expires_at=NOW + timedelta(days=7))
        grants.append(ledger.grant_consent(candidate_id=cid, purpose='ledger_read',
                      org_id=org.id, now=CUT - timedelta(days=1), expires_at=NOW + timedelta(days=7)))
        ledger.submit_interview_record(org_id=org.id, candidate_id=cid, stage='hm',
                                        outcome='hired', interviewed_at=CUT + timedelta(days=1), now=NOW)
        ledger.submit_coding_round(org_id=org.id, candidate_id=cid, platform='internal',
                                   score=90, max_score=100, percentile=90,
                                   taken_at=CUT + timedelta(days=2), now=NOW)
        features.upsert_vector(MaterializedVector(FeatureVector(candidate_id=cid,
            as_of=CUT, view_name='core_v1', view_version=1,
            values={'reputation.score': 0.9, 'candidate.num_skills': 3}),
            {'allowed': True}, CUT))
    return ledger, features, orgs, grants


def test_revoked_feature_csv_does_not_trust_cached_consent(database, tmp_path, monkeypatch):
    monkeypatch.setattr("app.features.serving._utcnow", lambda: NOW)
    _, factory = database
    ledger, features, _, grants = seed(factory)
    rows = features.vectors_for_view('core_v1', 1, as_of=CUT)
    ledger.revoke_consent(grants[0].id, now=NOW)
    path = tmp_path / 'features.csv'
    export_view_csv(rows, view=default_view(), registry=get_feature_registry(), ledger_store=ledger, path=str(path))
    with path.open(newline='', encoding='utf-8') as handle:
        exported = {r['candidate_id']: r for r in csv.DictReader(handle)}
    assert exported['a']['reputation.score'] == ''
    assert exported['b']['reputation.score'] == '0.9'
    assert exported['a']['candidate.num_skills'] == '3'
    assert rows[0].consent_state['allowed'] is True


def test_revoked_training_set_does_not_read_outcomes(database, monkeypatch):
    monkeypatch.setattr("app.features.serving._utcnow", lambda: NOW)
    _, factory = database
    ledger, features, _, grants = seed(factory)
    rows = features.vectors_for_view('core_v1', 1, as_of=CUT)
    ledger.revoke_consent(grants[0].id, now=NOW)
    original = ledger.records_for_candidate
    reads = []

    def read(cid):
        reads.append(cid)
        return original(cid)

    monkeypatch.setattr(ledger, 'records_for_candidate', read)
    examples = build_training_set(rows, ledger_store=ledger, registry=get_feature_registry())
    assert reads == ['b']
    by_id = {ex.vector.candidate_id: ex for ex in examples}
    assert by_id['a'].vector.values['reputation.score'] is None
    assert by_id['a'].label.withheld is True
    assert by_id['a'].label.hired is None
    assert by_id['b'].label.hired is True


def write_rows(kind, inputs, ledger, path, *, org_id=None, null_token=''):
    reg = get_feature_registry()
    writer = {'feature_csv': export_view_csv, 'feature_parquet': export_view_parquet,
              'training_csv': export_training_csv, 'training_parquet': export_training_parquet}[kind]
    kwargs = dict(view=default_view(reg), registry=reg, ledger_store=ledger,
                  path=str(path), org_id=org_id)
    if kind.endswith('csv'):
        writer(inputs, null_token=null_token, **kwargs)
        with path.open(newline='', encoding='utf-8') as handle:
            return {r['candidate_id']: r for r in csv.DictReader(handle)}
    pytest.importorskip('pyarrow')
    writer(inputs, **kwargs)
    import pyarrow.parquet as pq
    return {r['candidate_id']: r for r in pq.read_table(path).to_pylist()}


KINDS = ['feature_csv', 'feature_parquet', 'training_csv', 'training_parquet']


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('denial', ['revoked', 'expired', 'missing', 'wrong_purpose', 'future', 'wrong_org'])
def test_all_writers_recheck_cached_inputs(database, monkeypatch, tmp_path, kind, denial):
    monkeypatch.setattr('app.features.serving._utcnow', lambda: NOW)
    engine, factory = database
    ledger, features, orgs, grants = seed(factory)
    raw = features.vectors_for_view('core_v1', 1, as_of=CUT)
    inputs = build_training_set(raw, ledger_store=ledger, registry=get_feature_registry()) if kind.startswith('training') else raw
    assert raw[0].vector.values['reputation.score'] == 0.9
    if kind.startswith('training'):
        assert inputs[0].label.coding_best_percentile == 90
    if denial in {'revoked', 'wrong_org'}:
        ledger.revoke_consent(grants[0].id, now=NOW)
        if denial == 'wrong_org':
            ledger.grant_consent(candidate_id='a', purpose='ledger_read', org_id=orgs[1].id,
                                 now=CUT, expires_at=NOW + timedelta(days=1))
    else:
        changes = {'expired': {'expires_at': NOW}, 'missing': {'revoked_at': NOW},
                   'wrong_purpose': {'purpose': 'verification_read'},
                   'future': {'granted_at': NOW + timedelta(days=1)}}[denial]
        with engine.begin() as conn:
            conn.execute(update(ConsentGrantRow).where(ConsentGrantRow.id == grants[0].id).values(**changes))
    exported = write_rows(kind, iter(inputs), ledger, tmp_path / kind,
                          org_id=orgs[0].id if denial == 'wrong_org' else None, null_token='NULL')
    null = 'NULL' if kind.endswith('csv') else None
    a = exported['a']
    assert a['reputation.score'] == null
    assert a['candidate.num_skills'] == ('3' if kind.endswith('csv') else 3)
    assert a['as_of'] == CUT.isoformat()
    if denial != 'wrong_org':
        assert exported['b']['reputation.score'] == ('0.9' if kind.endswith('csv') else 0.9)
    if kind.startswith('training'):
        for name in ('hired', 'outcome', 'coding_best_percentile', 'event_at', 'lag_days'):
            assert a['label_' + name] == null
        assert a['label_observed'] == ('False' if kind.endswith('csv') else False)
        assert a['label_withheld'] == ('True' if kind.endswith('csv') else True)
        assert inputs[0].label.hired is True  # immutable cached label
    saved = features.vectors_for_view('core_v1', 1, as_of=CUT)
    assert saved == raw and all(mv.consent_state['allowed'] for mv in raw)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('scope', ['platform', 'org', 'wildcard'])
def test_allowed_scopes_and_candidate_isolation(database, monkeypatch, tmp_path, kind, scope):
    monkeypatch.setattr('app.features.serving._utcnow', lambda: NOW)
    _, factory = database
    ledger, features, orgs, grants = seed(factory)
    org_id = None if scope == 'platform' else orgs[0].id
    if scope == 'wildcard':
        ledger.revoke_consent(grants[0].id, now=NOW)
        ledger.grant_consent(candidate_id='a', purpose='ledger_read', org_id=None,
                             now=CUT, expires_at=NOW + timedelta(days=1))
    raw = features.vectors_for_view('core_v1', 1, as_of=CUT)
    inputs = build_training_set(raw, ledger_store=ledger, registry=get_feature_registry(), org_id=org_id) if kind.startswith('training') else raw
    exported = write_rows(kind, inputs, ledger, tmp_path / kind, org_id=org_id)
    assert exported['a']['reputation.score'] in ('0.9', 0.9)
    assert exported['b']['reputation.score'] == (('0.9' if kind.endswith('csv') else 0.9) if scope == 'platform' else ('' if kind.endswith('csv') else None))
    if kind.startswith('training'):
        assert exported['a']['label_hired'] in ('True', True)
        assert exported['b']['label_withheld'] == (str(scope != 'platform') if kind.endswith('csv') else scope != 'platform')


@pytest.mark.parametrize('audit', [False, True])
@pytest.mark.parametrize('boundary', ['before_read', 'after_outcomes', 'later_input'])
def test_training_rechecks_during_join(database, monkeypatch, audit, boundary):
    monkeypatch.setattr('app.features.serving._utcnow', lambda: NOW)
    _, factory = database
    ledger, features, _, grants = seed(factory)
    raw = features.vectors_for_view('core_v1', 1, as_of=CUT)
    reads = []
    original = ledger.coding_rounds_for_candidate

    def revoke():
        ledger.revoke_consent(grants[0].id, now=NOW)

    def outcomes(cid):
        reads.append(cid)
        rows = original(cid)
        if cid == 'a' and boundary == 'after_outcomes':
            revoke()
        return rows

    monkeypatch.setattr(ledger, 'coding_rounds_for_candidate', outcomes)
    if boundary == 'before_read':
        revoke()

    def stream():
        yield raw[0]
        if boundary == 'later_input':
            revoke()
        yield raw[1]

    result = build_training_set(stream(), ledger_store=ledger, registry=get_feature_registry(), audit=audit)
    assert reads == (['b'] if boundary == 'before_read' else ['a', 'b'])
    a, b = result
    assert a.vector.values['reputation.score'] is None and a.label.withheld
    assert a.label.model_dump() == dict(hired=None, outcome=None, coding_best_percentile=None,
                                      event_at=None, lag_days=None, observed=False, withheld=True)
    assert b.label.hired is True
    joins = [x for x in ledger.audit_for_candidate('a') if x.action == 'training.label']
    assert bool(joins) is audit
    if audit:
        assert joins[-1].details['allowed'] is (boundary == 'later_input')


@pytest.mark.parametrize('kind', KINDS)
def test_revoke_on_another_connection_before_iterator_yield(database, monkeypatch, tmp_path, kind):
    monkeypatch.setattr('app.features.serving._utcnow', lambda: NOW)
    _, factory = database
    ledger, features, _, grants = seed(factory)
    raw = features.vectors_for_view('core_v1', 1, as_of=CUT)
    inputs = build_training_set(raw, ledger_store=ledger, registry=get_feature_registry()) if kind.startswith('training') else raw
    if kind.endswith('parquet'):
        pytest.importorskip('pyarrow')
    ready, release = Event(), Event()

    def stream():
        ready.set()
        assert release.wait(20)
        yield from inputs

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(write_rows, kind, stream(), ledger, tmp_path / kind)
        try:
            assert ready.wait(20)
            assert LedgerStore(factory).revoke_consent(grants[0].id, now=NOW)
        finally:
            release.set()
        exported = pending.result(timeout=20)
    assert exported['a']['reputation.score'] == ('' if kind.endswith('csv') else None)
    assert exported['b']['reputation.score'] in ('0.9', 0.9)


@pytest.mark.parametrize('kind', KINDS)
def test_erasure_and_consent_failure_are_not_cached_fallbacks(database, monkeypatch, tmp_path, kind):
    monkeypatch.setattr('app.features.serving._utcnow', lambda: NOW)
    _, factory = database
    ledger, features, _, _ = seed(factory)
    raw = features.vectors_for_view('core_v1', 1, as_of=CUT)
    inputs = build_training_set(raw, ledger_store=ledger, registry=get_feature_registry()) if kind.startswith('training') else raw
    assert CandidateStore(factory).delete_candidate('a')
    exported = write_rows(kind, inputs, ledger, tmp_path / 'erased')
    assert set(exported) == {'b'}

    def broken(*_):
        raise RuntimeError('synthetic consent read failure')

    monkeypatch.setattr(ledger, 'consents_for_candidate', broken)
    with pytest.raises(RuntimeError, match='synthetic consent read failure'):
        write_rows(kind, inputs, ledger, tmp_path / 'failure')


def test_missing_optional_format_does_not_consume_or_write(database, monkeypatch, tmp_path):
    _, factory = database
    ledger, _, _, _ = seed(factory)
    original = builtins.__import__

    def missing(name, *args, **kwargs):
        if name.startswith('pyarrow'):
            raise ImportError('simulated absent optional dependency')
        return original(name, *args, **kwargs)

    def forbidden():
        pytest.fail('unavailable export must not consume sensitive rows')
        yield

    monkeypatch.setattr(builtins, '__import__', missing)
    for writer in (export_view_parquet, export_training_parquet):
        path = tmp_path / writer.__name__
        with pytest.raises(ParquetUnavailable):
            writer(forbidden(), view=default_view(), registry=get_feature_registry(),
                   ledger_store=ledger, path=str(path))
        assert not path.exists()


def test_new_grant_does_not_fill_historically_withheld_values_or_labels(database, monkeypatch, tmp_path):
    monkeypatch.setattr('app.features.serving._utcnow', lambda: NOW)
    _, factory = database
    ledger, features, _, grants = seed(factory)
    raw = features.vectors_for_view('core_v1', 1, as_of=CUT)
    withheld = MaterializedVector(raw[0].vector.model_copy(update={
        'values': {'reputation.score': None, 'candidate.num_skills': 3}}), {'allowed': False}, CUT)

    def forbidden(*_):
        pytest.fail('historically withheld outcomes must not be read')

    monkeypatch.setattr(ledger, 'records_for_candidate', forbidden)
    examples = build_training_set([withheld], registry=get_feature_registry(), ledger_store=ledger, audit=False)
    assert examples[0].label.withheld and examples[0].vector.values['reputation.score'] is None
    exported = write_rows('training_csv', examples, ledger, tmp_path / 'withheld')
    assert exported['a']['label_hired'] == '' and exported['a']['label_withheld'] == 'True'


@pytest.mark.parametrize('kind', ['feature_parquet', 'training_parquet'])
def test_parquet_authorizes_after_collecting_iterator(database, monkeypatch, tmp_path, kind):
    monkeypatch.setattr('app.features.serving._utcnow', lambda: NOW)
    _, factory = database
    ledger, features, _, grants = seed(factory)
    raw = features.vectors_for_view('core_v1', 1, as_of=CUT)
    inputs = build_training_set(raw, ledger_store=ledger, registry=get_feature_registry()) if kind.startswith('training') else raw

    def stream():
        yield inputs[0]
        ledger.revoke_consent(grants[0].id, now=NOW)
        yield inputs[1]

    exported = write_rows(kind, stream(), ledger, tmp_path / kind)
    assert exported['a']['reputation.score'] is None
    assert exported['b']['reputation.score'] == 0.9
    if kind.startswith('training'):
        assert exported['a']['label_withheld'] is True


@pytest.mark.parametrize('denial', ['expired', 'future', 'wrong_purpose', 'missing', 'wrong_org'])
def test_training_denials_do_not_fetch_either_outcome_source(database, monkeypatch, denial):
    monkeypatch.setattr('app.features.serving._utcnow', lambda: NOW)
    engine, factory = database
    ledger, features, orgs, grants = seed(factory)
    raw = features.vectors_for_view('core_v1', 1, as_of=CUT)[:1]
    changes = {'expired': {'expires_at': NOW}, 'future': {'granted_at': NOW + timedelta(days=1)},
               'wrong_purpose': {'purpose': 'ledger_write'}, 'missing': {'revoked_at': NOW},
               'wrong_org': {'org_id': orgs[1].id}}[denial]
    with engine.begin() as conn:
        conn.execute(update(ConsentGrantRow).where(ConsentGrantRow.id == grants[0].id).values(**changes))

    def forbidden(*_):
        pytest.fail('denied outcome source must not be read')

    monkeypatch.setattr(ledger, 'records_for_candidate', forbidden)
    monkeypatch.setattr(ledger, 'coding_rounds_for_candidate', forbidden)
    result = build_training_set(raw, ledger_store=ledger, registry=get_feature_registry(),
                                org_id=orgs[0].id, audit=False)
    assert result[0].label.withheld and result[0].vector.values['reputation.score'] is None


def test_training_store_failure_propagates(database, monkeypatch):
    _, factory = database
    ledger, features, _, _ = seed(factory)

    def broken(*_):
        raise RuntimeError('synthetic consent read failure')

    monkeypatch.setattr(ledger, 'consents_for_candidate', broken)
    with pytest.raises(RuntimeError, match='synthetic consent read failure'):
        build_training_set(features.vectors_for_view('core_v1', 1, as_of=CUT),
                           ledger_store=ledger, registry=get_feature_registry(), audit=False)


@pytest.mark.parametrize('kind', KINDS + ['training_set'])
def test_erasure_during_final_consent_read_is_omitted(database, monkeypatch, tmp_path, kind):
    monkeypatch.setattr('app.features.serving._utcnow', lambda: NOW)
    _, factory = database
    ledger, features, _, _ = seed(factory)
    raw = features.vectors_for_view('core_v1', 1, as_of=CUT)
    inputs = build_training_set(raw, ledger_store=ledger, registry=get_feature_registry()) if kind.startswith('training') else raw
    original = ledger.consents_for_candidate
    reads = 0

    def read_then_erase(cid):
        nonlocal reads
        grants = original(cid)
        if cid == 'a':
            reads += 1
            if reads == (3 if kind == 'training_set' else 1):
                assert CandidateStore(factory).delete_candidate(cid)
        return grants

    monkeypatch.setattr(ledger, 'consents_for_candidate', read_then_erase)
    if kind == 'training_set':
        examples = build_training_set(raw, ledger_store=ledger, registry=get_feature_registry())
        assert [ex.vector.candidate_id for ex in examples] == ['b']
    else:
        exported = write_rows(kind, inputs, ledger, tmp_path / kind)
        assert set(exported) == {'b'}
