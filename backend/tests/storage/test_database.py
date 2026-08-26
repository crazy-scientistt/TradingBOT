import sqlite3

import pytest
from goldguard.storage.database import Database


def test_migration_enables_wal_foreign_keys_and_integrity(tmp_path) -> None:
    database = Database(tmp_path / "goldguard.db")
    database.migrate()

    with database.connect() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }

    assert {
        "settings_versions",
        "paper_accounts",
        "market_candles",
        "context_snapshots",
        "decision_chains",
        "orders",
        "trades",
        "reflections",
        "backtest_runs",
        "strategy_proposals",
        "shadow_runs",
        "hermes_events",
        "audit_events",
        "providers",
        "model_routes",
        "active_routes",
        "genomes",
        "evaluations",
        "promotions",
        "research_quota",
        "research_events",
    }.issubset(tables)
    assert database.integrity_check() == "ok"


def test_transaction_rolls_back_all_writes_on_failure(tmp_path) -> None:
    database = Database(tmp_path / "goldguard.db")
    database.migrate()

    with pytest.raises(RuntimeError, match="abort"), database.transaction() as connection:
        connection.execute(
            "INSERT INTO audit_events(occurred_at, actor, action, details_json) "
            "VALUES (?, ?, ?, ?)",
            ("2026-08-26T00:00:00+00:00", "test", "FIRST", "{}"),
        )
        raise RuntimeError("abort")

    with database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 0


def test_immutable_records_reject_update_and_delete(tmp_path) -> None:
    database = Database(tmp_path / "goldguard.db")
    database.migrate()

    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO audit_events(occurred_at, actor, action, details_json) "
            "VALUES (?, ?, ?, ?)",
            ("2026-08-26T00:00:00+00:00", "test", "CREATED", "{}"),
        )

    with (
        pytest.raises(sqlite3.IntegrityError, match="audit events are immutable"),
        database.transaction() as connection,
    ):
        connection.execute("UPDATE audit_events SET action = 'CHANGED'")

    with (
        pytest.raises(sqlite3.IntegrityError, match="audit events are immutable"),
        database.transaction() as connection,
    ):
        connection.execute("DELETE FROM audit_events")
