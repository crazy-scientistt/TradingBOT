import sqlite3
from pathlib import Path

import pytest
from goldguard.storage.database import Database, _execute_migration_script


def test_migration_003_is_idempotent(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")

    database.migrate()
    database.migrate()

    with database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 3"
        ).fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert count == 1
    assert {
        "profile_versions",
        "active_profile",
        "live_arming_state",
        "admin_users",
        "admin_sessions",
        "security_events",
    }.issubset(tables)


def test_control_plane_history_rejects_mutation(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    database.migrate()

    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO profile_versions "
            "(hash, payload, created_by, correlation_id) VALUES (?, ?, ?, ?)",
            ("profile-hash", "{}", "admin", "corr-1"),
        )
        connection.execute(
            "INSERT INTO security_events "
            "(event_type, actor, correlation_id, metadata) VALUES (?, ?, ?, ?)",
            ("profile_activated", "admin", "corr-1", "{}"),
        )

    with (
        pytest.raises(sqlite3.IntegrityError, match="profile versions are immutable"),
        database.transaction() as connection,
    ):
        connection.execute(
            "UPDATE profile_versions SET payload = ? WHERE hash = ?",
            ('{"changed":true}', "profile-hash"),
        )

    with (
        pytest.raises(sqlite3.IntegrityError, match="security events are immutable"),
        database.transaction() as connection,
    ):
        connection.execute("DELETE FROM security_events")

    with (
        pytest.raises(sqlite3.IntegrityError, match="profile versions are immutable"),
        database.transaction() as connection,
    ):
        connection.execute(
            "INSERT OR REPLACE INTO profile_versions "
            "(hash, payload, created_by, correlation_id) VALUES (?, ?, ?, ?)",
            ("profile-hash", '{"replaced":true}', "admin", "corr-2"),
        )


def test_live_arming_starts_disarmed_and_rejects_unknown_status(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    database.migrate()

    with database.connect() as connection:
        row = connection.execute(
            "SELECT status, profile_hash, expected_equity_usdt, armed_at, armed_by "
            "FROM live_arming_state WHERE id = 1"
        ).fetchone()

    assert row is not None
    assert tuple(row) == ("disarmed", None, None, None, None)

    with (
        pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"),
        database.transaction() as connection,
    ):
        connection.execute("UPDATE live_arming_state SET status = 'invented_state' WHERE id = 1")


def test_disarmed_state_rejects_stale_arming_details(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    database.migrate()

    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO profile_versions "
            "(hash, payload, created_by, correlation_id) VALUES (?, ?, ?, ?)",
            ("stale-profile", "{}", "admin", "corr-1"),
        )

    with (
        pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"),
        database.transaction() as connection,
    ):
        connection.execute(
            "UPDATE live_arming_state "
            "SET profile_hash = 'stale-profile', expected_equity_usdt = '1000.00', "
            "armed_at = '2026-08-29T00:00:00+00:00', armed_by = 'admin' "
            "WHERE id = 1"
        )


def test_live_arming_singleton_cannot_be_deleted(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    database.migrate()

    with (
        pytest.raises(sqlite3.IntegrityError, match="live arming state is required"),
        database.transaction() as connection,
    ):
        connection.execute("DELETE FROM live_arming_state WHERE id = 1")


def test_migration_executor_accepts_multiple_statements_on_one_line(
    tmp_path: Path,
) -> None:
    connection = sqlite3.connect(tmp_path / "script.db")
    try:
        _execute_migration_script(
            connection,
            "CREATE TABLE first_table(id INTEGER); CREATE TABLE second_table(id INTEGER);",
            Path("004_two_statements.sql"),
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        connection.close()

    assert {"first_table", "second_table"}.issubset(tables)
