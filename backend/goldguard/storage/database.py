import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def _execute_migration_script(
    connection: sqlite3.Connection, script: str, source: Path
) -> None:
    pending = ""
    fragments = script.split(";")
    for index, fragment in enumerate(fragments):
        pending += fragment
        if index < len(fragments) - 1:
            pending += ";"
        statement = pending.strip()
        if not statement or not sqlite3.complete_statement(statement):
            continue
        connection.execute(statement)
        pending = ""

    if pending.strip():
        raise ValueError(f"Incomplete SQL statement in migration {source.name}")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA recursive_triggers = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def migrate(self) -> None:
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        with self.connect() as connection:
            connection.executescript(schema)
            migrations_dir = Path(__file__).with_name("migrations")
            for migration_file in sorted(migrations_dir.glob("*.sql")):
                version = int(migration_file.stem.partition("_")[0])
                connection.execute("BEGIN IMMEDIATE")
                try:
                    applied = connection.execute(
                        "SELECT 1 FROM schema_migrations WHERE version = ?",
                        (version,),
                    ).fetchone()
                    if applied is None:
                        migration = migration_file.read_text(encoding="utf-8")
                        _execute_migration_script(connection, migration, migration_file)
                        connection.execute(
                            "INSERT INTO schema_migrations(version, applied_at) "
                            "VALUES (?, strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'))",
                            (version,),
                        )
                except BaseException:
                    connection.rollback()
                    raise
                else:
                    connection.commit()

    def integrity_check(self) -> str:
        with self.connect() as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
        if result is None:
            raise RuntimeError("SQLite returned no integrity result")
        return str(result[0])
