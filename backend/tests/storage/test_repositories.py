import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from goldguard.storage.database import Database
from goldguard.storage.repositories import (
    GenomeRepository,
    LedgerRepository,
    ProviderRepository,
    QuotaRepository,
)
from goldguard.strategy.genome import trend_pullback_v1


@pytest.fixture
def database(tmp_path) -> Database:
    db = Database(tmp_path / "goldguard.db")
    db.migrate()
    return db


@pytest.fixture
def repository(database: Database) -> LedgerRepository:
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


def test_genome_repository_transitions_and_active_resolution(database: Database) -> None:
    repo = GenomeRepository(database)
    genome = trend_pullback_v1()

    # Save baseline as candidate
    repo.save_genome(genome, origin="baseline", status="candidate")
    assert repo.get_genome("trend-pullback-v1") is not None

    # Baseline direct promotion to active by human is permitted
    repo.transition_genome_status("trend-pullback-v1", "active", promoted_by="human")
    active = repo.get_active_genome()
    assert active is not None
    assert active.genome_id == "trend-pullback-v1"

    # Hermes genome cannot jump from candidate to active directly
    hermes_genome = genome.model_copy(
        update={"genome_id": "hermes-proposal-1", "parent_id": "trend-pullback-v1"}
    )
    repo.save_genome(hermes_genome, origin="hermes", status="candidate")

    with pytest.raises(ValueError, match="invalid status transition"):
        repo.transition_genome_status("hermes-proposal-1", "active", promoted_by="gate")

    # Valid step: candidate -> shadow -> active
    repo.transition_genome_status("hermes-proposal-1", "shadow")
    repo.transition_genome_status("hermes-proposal-1", "active", promoted_by="gate")
    new_active = repo.get_active_genome()
    assert new_active is not None
    assert new_active.genome_id == "hermes-proposal-1"


def test_research_quota_repository(database: Database) -> None:
    quota_repo = QuotaRepository(database)
    today = "2026-08-26"

    # Consume backtests within limit
    assert quota_repo.consume_backtest(today, max_limit=2) is True
    assert quota_repo.consume_backtest(today, max_limit=2) is True
    # Exceeded limit
    assert quota_repo.consume_backtest(today, max_limit=2) is False

    # Web calls
    assert quota_repo.consume_web_call(today, max_limit=1) is True
    assert quota_repo.consume_web_call(today, max_limit=1) is False


def test_provider_routes_and_active_view(database: Database) -> None:
    prov_repo = ProviderRepository(database)
    prov_repo.upsert_provider(
        name="opencodex",
        kind="opencodex",
        base_url="http://localhost:10100",
        key_fingerprint="sha256-mock",
        status="active",
    )

    v1 = prov_repo.set_route("decision", "opencodex", "gemini-2.0-flash-lite", pinned=True)
    assert v1 == 1

    v2 = prov_repo.set_route(
        "decision", "opencodex", "google-antigravity/gemini-3.7-flash", pinned=True
    )
    assert v2 == 2

    routes = prov_repo.get_active_routes()
    assert routes["decision"].model == "google-antigravity/gemini-3.7-flash"
    assert routes["decision"].version == 2


def _equity_snapshot(
    database: Database,
    *,
    account_id: str,
    equity: str,
    observed_at: datetime,
) -> None:
    """Write one equity snapshot, mirroring the runtime's own insert."""
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO equity_snapshots(id, paper_account_id, equity_text, cash_text, observed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (f"eq-{observed_at.isoformat()}", account_id, equity, equity, observed_at.isoformat()),
        )


def _close_trade(
    database: Database,
    *,
    account_id: str,
    trade_id: str,
    realized_pnl: str,
    closed_at: datetime,
) -> None:
    """Write one CLOSED paper trade, mirroring the runtime's own inserts."""
    order_id = f"order-{trade_id}"
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO orders(
                id, mode, paper_account_id, client_order_id, side,
                quantity_text, status, created_at
            ) VALUES (?, 'paper', ?, ?, 'BUY', '0.01', 'FILLED', ?)
            """,
            (order_id, account_id, f"cid-{trade_id}", closed_at.isoformat()),
        )
        connection.execute(
            """
            INSERT INTO trades(
                id, mode, paper_account_id, entry_order_id, status,
                realized_pnl_text, opened_at, closed_at
            ) VALUES (?, 'paper', ?, ?, 'CLOSED', ?, ?, ?)
            """,
            (
                trade_id,
                account_id,
                order_id,
                realized_pnl,
                (closed_at - timedelta(hours=1)).isoformat(),
                closed_at.isoformat(),
            ),
        )


def test_risk_inputs_are_measured_from_the_ledger(
    database: Database,
    repository: LedgerRepository,
) -> None:
    now = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    account = repository.create_paper_session(Decimal("100"))
    _equity_snapshot(
        database,
        account_id=account,
        equity="100",
        observed_at=now - timedelta(hours=23),
    )
    # Two losses today after a win: the streak must count only the trailing losses.
    _close_trade(
        database,
        account_id=account,
        trade_id="t1",
        realized_pnl="4.00",
        closed_at=now - timedelta(hours=20),
    )
    _close_trade(
        database,
        account_id=account,
        trade_id="t2",
        realized_pnl="-3.00",
        closed_at=now - timedelta(hours=6),
    )
    _close_trade(
        database,
        account_id=account,
        trade_id="t3",
        realized_pnl="-2.00",
        closed_at=now - timedelta(minutes=30),
    )

    measured = repository.measure_risk_inputs(account, equity=Decimal("99"), now=now)

    # 24h realized pnl is -1.00 against a 100.00 window-opening equity.
    assert measured.rolling_24h_loss_rate == Decimal("0.01")
    assert measured.peak_drawdown_rate == Decimal("0.01")
    assert measured.consecutive_losses == 2
    assert measured.minutes_since_exit == 30


def test_risk_inputs_on_a_fresh_account_block_nothing(repository: LedgerRepository) -> None:
    account = repository.create_paper_session(Decimal("100"))

    measured = repository.measure_risk_inputs(account, equity=Decimal("100"))

    assert measured.rolling_24h_loss_rate == Decimal("0")
    assert measured.peak_drawdown_rate == Decimal("0")
    assert measured.consecutive_losses == 0
    # No exit has happened, so there is no cooldown to serve.
    assert measured.minutes_since_exit is None


def test_a_profitable_day_reports_no_loss_rate(
    database: Database,
    repository: LedgerRepository,
) -> None:
    now = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    account = repository.create_paper_session(Decimal("100"))
    _equity_snapshot(
        database,
        account_id=account,
        equity="100",
        observed_at=now - timedelta(hours=5),
    )
    _close_trade(
        database,
        account_id=account,
        trade_id="win",
        realized_pnl="7.50",
        closed_at=now - timedelta(hours=2),
    )

    measured = repository.measure_risk_inputs(account, equity=Decimal("107.50"), now=now)

    assert measured.rolling_24h_loss_rate == Decimal("0")
    assert measured.peak_drawdown_rate == Decimal("0")
    assert measured.consecutive_losses == 0
