"""Read-only aggregate contact inventory of an explicitly selected SQLite file.

No configuration/environment loading, migrations, candidate identifiers, contact
hash values or repair mode. Missing proof columns mean unknown, not zero.
"""

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3


def inventory(database: Path) -> dict:
    path = database.resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        columns = {row[1] for row in connection.execute('PRAGMA table_info(candidates)')}
        if not {'id', 'email_hash', 'phone_hash'} <= columns:
            raise ValueError('unsupported_schema')
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        def count(sql):
            return connection.execute(sql).fetchone()[0]

        result = {'candidate_rows': count('SELECT COUNT(*) FROM candidates')}
        for column in ('email_hash', 'phone_hash'):
            # Identifiers come only from this fixed tuple, never user input.
            prefix = column.removesuffix('_hash')
            result[prefix + '_missing_rows'] = count(
                f"SELECT COUNT(*) FROM candidates WHERE {column} IS NULL OR {column} = ''")
            grouped = (f'SELECT COUNT(*) AS n FROM candidates WHERE {column} IS NOT NULL '
                       f"AND {column} != '' GROUP BY {column} HAVING COUNT(*) > 1")
            result[prefix + '_duplicate_groups'] = count(f'SELECT COUNT(*) FROM ({grouped})')
            result[prefix + '_duplicate_rows'] = count(f'SELECT COALESCE(SUM(n), 0) FROM ({grouped})')
        result['no_contact_rows'] = count("SELECT COUNT(*) FROM candidates WHERE "
            "(email_hash IS NULL OR email_hash = '') AND (phone_hash IS NULL OR phone_hash = '')")
        result['proof_schema_available'] = {
            'login_email_hash', 'login_email_verified_at', 'login_binding_review_required'} <= columns
        result['proof'] = None
        if result['proof_schema_available']:
            queries = {
                'bound_rows': 'login_email_hash IS NOT NULL',
                'review_required_rows': 'login_binding_review_required = 1',
                'proof_without_timestamp_rows': 'login_email_hash IS NOT NULL AND login_email_verified_at IS NULL',
                'timestamp_without_proof_rows': 'login_email_hash IS NULL AND login_email_verified_at IS NOT NULL',
                'asserted_email_differs_from_proof_rows': 'login_email_hash IS NOT NULL AND (email_hash IS NULL OR email_hash != login_email_hash)',
                'asserted_email_at_other_proved_owner_rows': 'EXISTS (SELECT 1 FROM candidates other WHERE other.id != candidates.id AND other.login_email_hash = candidates.email_hash)',
            }
            proof = {key: count('SELECT COUNT(*) FROM candidates WHERE ' + where)
                     for key, where in queries.items()}
            proof['duplicate_proof_groups'] = count('SELECT COUNT(*) FROM '
                '(SELECT 1 FROM candidates WHERE login_email_hash IS NOT NULL '
                'GROUP BY login_email_hash HAVING COUNT(*) > 1)')
            result['proof'] = proof
        # Historical evidence supplies review counts, never mailbox ownership.
        conditions = []
        if 'auth_sessions' in tables:
            conditions.append('EXISTS (SELECT 1 FROM auth_sessions WHERE auth_sessions.candidate_id = candidates.id)')
        if 'audit_log' in tables:
            conditions.append("EXISTS (SELECT 1 FROM audit_log WHERE audit_log.candidate_id = candidates.id AND audit_log.action = 'auth.session.create')")
        result['historical_login_subject_rows'] = count(
            'SELECT COUNT(*) FROM candidates WHERE ' + ' OR '.join(conditions)) if conditions else None
        result['historical_login_evidence_available'] = {'auth_sessions', 'audit_log'} <= tables
        revision = (connection.execute('SELECT version_num FROM alembic_version').fetchone()
                    if 'alembic_version' in tables else None)
        result['schema_revision'] = revision[0] if revision else None
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = inventory(args.database)
    except (OSError, sqlite3.Error, ValueError):
        parser.exit(2, 'Inventory refused: missing file or unsupported SQLite schema.\n')
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
