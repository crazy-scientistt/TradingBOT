import sqlite3
from pathlib import Path

from goldguard.storage.database import Database


def test_migration_003_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    # Create base schema manually for the test
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY)")
    connection.close()

    database = Database(db_path)

    # Override migrate to not try to read schema.sql from the real path
    def mock_migrate():
        migrations_dir = Path(__file__).parents[2] / "goldguard" / "storage" / "migrations"
        with database.connect() as conn:
            for migration_file in sorted(migrations_dir.glob("*.sql")):
                version = int(migration_file.stem.split("_")[0])
                applied = conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
                ).fetchone()
                if not applied:
                    with database.transaction() as tx:
                        tx.executescript(migration_file.read_text(encoding="utf-8"))

    mock_migrate()
    mock_migrate()

    with database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 3"
        ).fetchone()[0]
    assert count == 1
