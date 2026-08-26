import sqlite3
from decimal import Decimal

import pytest
from goldguard.storage.database import Database
from goldguard.storage.repositories import LedgerRepository


@pytest.fixture
def repository(tmp_path) -> LedgerRepository:
    database = Database(tmp_path / "goldguard.db")
    database.migrate()
    return LedgerRepository(database)


def test_new_paper_balance_creates_a_session_without_deleting_history(
    repository: LedgerRepository,
) -> None:
    first = repository.create_paper_session(Decimal("100"))
    second = repository.create_paper_session(Decimal("250.50"))

    assert first != second
    assert repository.current_paper_session_id() == second
    sessions = repository.list_paper_sessions()
    assert [row.initial_balance for row in sessions] == [Decimal("100"), Decimal("250.50")]


def test_settings_versions_are_immutable(repository: LedgerRepository) -> None:
    identifier = repository.save_settings_version(
        version="safe-default-v1",
        payload={"risk_per_trade": "0.005"},
    )

    with (
        pytest.raises(sqlite3.IntegrityError, match="settings versions are immutable"),
        repository.database.transaction() as connection,
    ):
        connection.execute(
            "UPDATE settings_versions SET payload_json = '{}' WHERE id = ?",
            (identifier,),
        )


def test_decision_chain_is_idempotent_per_closed_candle(repository: LedgerRepository) -> None:
    session_id = repository.create_paper_session(Decimal("100"))
    key = repository.record_decision_chain(
        mode="paper",
        account_scope=session_id,
        symbol="PAXGUSDT",
        timeframe="15m",
        candle_close_time="2026-08-26T00:15:00+00:00",
    )

    assert (
        repository.record_decision_chain(
            mode="paper",
            account_scope=session_id,
            symbol="PAXGUSDT",
            timeframe="15m",
            candle_close_time="2026-08-26T00:15:00+00:00",
        )
        == key
    )
    assert repository.count_decision_chains() == 1


def test_order_schema_rejects_cross_mode_paper_link(repository: LedgerRepository) -> None:
    session_id = repository.create_paper_session(Decimal("100"))

    with pytest.raises(sqlite3.IntegrityError), repository.database.transaction() as connection:
        connection.execute(
            "INSERT INTO orders(id, mode, paper_account_id, client_order_id, side, "
            "quantity_text, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "order-1",
                "live",
                session_id,
                "client-1",
                "BUY",
                "0.01",
                "PENDING",
                "2026-08-26T00:00:00+00:00",
            ),
        )
