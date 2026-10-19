"""Inventory is read-only, aggregate and honest about legacy proof coverage."""

import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/inventory_candidate_contacts.py'
spec = importlib.util.spec_from_file_location('contact_inventory', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def database(path, current=False):
    with sqlite3.connect(path) as conn:
        columns = ', login_email_hash TEXT, login_email_verified_at TEXT, login_binding_review_required INTEGER' if current else ''
        conn.execute('CREATE TABLE candidates (id TEXT PRIMARY KEY, email_hash TEXT, phone_hash TEXT' + columns + ')')
        conn.execute('CREATE TABLE auth_sessions (candidate_id TEXT)')
        conn.execute('CREATE TABLE audit_log (candidate_id TEXT, action TEXT)')
        for cid, email, phone in [('private-a', 'a' * 64, 'p' * 64),
                                 ('private-b', 'a' * 64, 'p' * 64),
                                 ('private-c', None, None)]:
            conn.execute('INSERT INTO candidates (id, email_hash, phone_hash) VALUES (?, ?, ?)', (cid, email, phone))
        conn.execute("INSERT INTO auth_sessions VALUES ('private-a')")
        conn.execute("INSERT INTO audit_log VALUES ('private-b', 'auth.session.create')")
        if current:
            conn.execute('UPDATE candidates SET login_binding_review_required = 0')
            conn.execute('UPDATE candidates SET login_email_hash = ?, login_email_verified_at = ? WHERE id = ?',
                         ('a' * 64, '2026-10-08', 'private-a'))
            conn.execute("UPDATE candidates SET login_email_hash = ?, login_binding_review_required = 1 WHERE id = 'private-b'", ('b' * 64,))
            conn.execute("UPDATE candidates SET login_email_verified_at = '2026-10-08' WHERE id = 'private-c'")


@pytest.mark.parametrize('current', [False, True])
def test_aggregate_inventory_keeps_source_and_reports_coverage(tmp_path, current):
    path = tmp_path / 'explicit.db'
    database(path, current)
    before = path.read_bytes()
    result = module.inventory(path)
    assert path.read_bytes() == before
    assert result['candidate_rows'] == 3
    assert result['email_duplicate_groups'] == result['phone_duplicate_groups'] == 1
    assert result['email_duplicate_rows'] == result['phone_duplicate_rows'] == 2
    assert result['no_contact_rows'] == 1
    assert result['historical_login_subject_rows'] == 2
    assert result['proof_schema_available'] is current
    if current:
        assert result['proof'] == dict(bound_rows=2, review_required_rows=1,
            proof_without_timestamp_rows=1, timestamp_without_proof_rows=1,
            asserted_email_differs_from_proof_rows=1,
            asserted_email_at_other_proved_owner_rows=1, duplicate_proof_groups=0)
    else:
        assert result['proof'] is None
    serialized = json.dumps(result)
    assert 'private-' not in serialized and 'a' * 64 not in serialized
    output = subprocess.run([sys.executable, str(SCRIPT), '--database', str(path)],
        capture_output=True, text=True)
    assert output.returncode == 0
    assert json.loads(output.stdout) == result
    assert path.read_bytes() == before


def test_missing_file_does_not_create_database(tmp_path):
    missing = tmp_path / 'missing.db'
    with pytest.raises(FileNotFoundError):
        module.inventory(missing)
    output = subprocess.run([sys.executable, str(SCRIPT), '--database', str(missing)],
        capture_output=True, text=True)
    assert output.returncode == 2 and not missing.exists()
    assert 'missing.db' not in output.stderr


def test_no_schema_is_refused_without_writing(tmp_path):
    path = tmp_path / 'empty.db'
    path.touch()
    with pytest.raises(ValueError, match='unsupported_schema'):
        module.inventory(path)
    assert path.read_bytes() == b''
