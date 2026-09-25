"""Frozen DDL for migration 0026 and ORM-created test databases.

Keep this version stable: a future schema change needs a new migration/helper.
Builders do not execute DDL. No subject identifiers or text are kept here.
"""

from sqlalchemy import text


def install(connection):
    connection.execute(text("INSERT INTO screening_erasure_state (id, generation) VALUES (1, 0)"))
    if connection.dialect.name == "postgresql":
        connection.execute(text("""
            CREATE FUNCTION screening_erasure_lock() RETURNS trigger AS $$
            BEGIN
                PERFORM id FROM screening_erasure_state WHERE id = 1 FOR UPDATE;
                RETURN NULL;
            END; $$ LANGUAGE plpgsql
        """))
        connection.execute(text("""
            CREATE FUNCTION screening_erasure_advance() RETURNS trigger AS $$
            BEGIN
                UPDATE screening_erasure_state SET generation = generation + 1 WHERE id = 1;
                RETURN OLD;
            END; $$ LANGUAGE plpgsql
        """))
        for table in ("candidates", "resumes", "reports"):
            connection.execute(text(f"CREATE TRIGGER screening_erasure_lock BEFORE DELETE ON {table} "
                                    "FOR EACH STATEMENT EXECUTE FUNCTION screening_erasure_lock()"))
            connection.execute(text(f"CREATE TRIGGER screening_erasure_advance AFTER DELETE ON {table} "
                                    "FOR EACH ROW EXECUTE FUNCTION screening_erasure_advance()"))
    elif connection.dialect.name == "sqlite":
        # SQLite serializes writers; the row trigger and deletion share that
        # write transaction, including rollback and cascaded/bulk deletions.
        for table in ("candidates", "resumes", "reports"):
            connection.execute(text(f"""
                CREATE TRIGGER screening_erasure_{table} BEFORE DELETE ON {table}
                BEGIN
                    UPDATE screening_erasure_state SET generation = generation + 1 WHERE id = 1;
                END
            """))
    else:
        raise NotImplementedError("screening erasure supports SQLite and PostgreSQL")


def uninstall(connection):
    if connection.dialect.name == "postgresql":
        for table in ("candidates", "resumes", "reports"):
            for suffix in ("lock", "advance"):
                connection.execute(text(f"DROP TRIGGER screening_erasure_{suffix} ON {table}"))
        for suffix in ("lock", "advance"):
            connection.execute(text(f"DROP FUNCTION screening_erasure_{suffix}()"))
    else:
        for table in ("candidates", "resumes", "reports"):
            connection.execute(text(f"DROP TRIGGER screening_erasure_{table}"))
