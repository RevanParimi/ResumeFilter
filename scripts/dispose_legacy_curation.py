"""Counts-only inventory and explicitly selected legacy curation disposition.

No .env/config loading, migrations, automatic database creation or raw output.
Read-only by default. Apply only after operator authorization and writer shutdown.
"""

import argparse
import json
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, select, text, URL
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.curation.legacy import LegacyDispositionError, dispose, inventory
from app.curation.models import CurationAliasRow, CurationObservationRow

MAX_MANIFEST_BYTES = 256 * 1024


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's normal errors can echo arbitrary supplied arguments.
        raise LegacyDispositionError("invalid command arguments; use --help")


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LegacyDispositionError("duplicate manifest field")
        result[key] = value
    return result


def main(argv=None):
    engine = None
    try:
        parser = Parser(description=__doc__)
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--database", type=Path, help="existing SQLite file")
        target.add_argument("--database-url-env", help="environment variable holding an explicit PostgreSQL URL")
        parser.add_argument("--selection", type=Path, help="strict JSON disposition manifest")
        parser.add_argument("--apply", action="store_true", help="commit selected disposition; requires authorization")
        args = parser.parse_args(argv)
        if args.apply and args.selection is None:
            raise LegacyDispositionError("apply requires an explicit selection")
        entries = None
        if args.selection is not None:
            with args.selection.open("rb") as manifest:
                payload = manifest.read(MAX_MANIFEST_BYTES + 1)
            if len(payload) > MAX_MANIFEST_BYTES:
                raise LegacyDispositionError("manifest exceeds size limit")
            entries = json.loads(payload, object_pairs_hook=unique_fields)
        if args.database is not None:
            path = args.database.resolve(strict=True)
            if not path.is_file():
                raise LegacyDispositionError("database must be an existing file")
            url = URL.create("sqlite", database=path.as_uri(),
                             query={"mode": "rw" if args.apply else "ro", "uri": "true"})
            engine = create_engine(url, hide_parameters=True)
        else:
            raw = os.environ.get(args.database_url_env, "")
            if not raw:
                raise LegacyDispositionError("database URL environment variable is empty")
            url = make_url(raw)
            if url.get_backend_name() != "postgresql":
                raise LegacyDispositionError("URL environment variable must select PostgreSQL")
            engine = create_engine(url, hide_parameters=True)
        with engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(text("SET LOCAL lock_timeout = '10s'"))
                conn.execute(text("SET LOCAL statement_timeout = '30s'"))
                if not args.apply:
                    conn.execute(text("SET TRANSACTION READ ONLY"))
            elif not args.apply:
                conn.execute(text("PRAGMA query_only=ON"))
            # Refuse partial/old schemas before any selected deletion.
            conn.execute(select(CurationAliasRow.norm_key).limit(0))
            conn.execute(select(CurationObservationRow.source_id).limit(0))
            result = {}
            if args.selection is not None:
                result["disposition"] = dispose(conn, entries, apply=args.apply)
            result["inventory"] = inventory(conn)
        print(json.dumps(result, sort_keys=True))
        return 0
    except LegacyDispositionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, ValueError, RecursionError, SQLAlchemyError):
        print("Legacy curation operation failed; check target, migration and selection privately.", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
