from __future__ import annotations

from pathlib import Path

from goldguard.storage.database import Database


def test_execution_migration_applies_cleanly(tmp_path: Path) -> None:
    db = Database(tmp_path / "migration_test.db")
    db.migrate()

    with db.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "execution_intents" in tables
        assert "execution_orders" in tables
        assert "execution_fills" in tables
        assert "execution_positions" in tables
        assert "execution_protections" in tables
        assert "account_snapshots" in tables

