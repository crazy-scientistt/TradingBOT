from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from goldguard.broker.paper_futures import PaperFuturesBroker
from goldguard.broker.paper_portfolio import PaperPortfolioBroker
from goldguard.broker.paper_spot import PaperSpotBroker
from goldguard.domain.enums import ExecutionMode, ProductKind
from goldguard.domain.models import Candle, Quote
from goldguard.execution.models import MarketScope
from goldguard.services.execution_coordinator import ExecutionCoordinator
from goldguard.storage.database import Database
from goldguard.storage.execution_repository import ExecutionRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "coordinator_test.db")
    db.migrate()
    return db


@pytest.fixture
def coordinator(database: Database) -> ExecutionCoordinator:
    spot = PaperSpotBroker(starting_cash=Decimal("10000.00"))
    futures = PaperFuturesBroker(starting_collateral=Decimal("10000.00"))
    broker = PaperPortfolioBroker(spot=spot, futures=futures)
    repo = ExecutionRepository(database)
    return ExecutionCoordinator(broker=broker, repository=repo, database=database)


def spot_scope(symbol: str) -> MarketScope:
    return MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol=symbol)


def closed_candle() -> Candle:
    close = datetime(2026, 8, 29, 12, 15, 0, tzinfo=UTC)
    start = close - timedelta(minutes=15)
    return Candle(
        symbol="PAXGUSDT",
        timeframe="15m",
        open_time=start,
        close_time=close,
        open=Decimal("2500.00"),
        high=Decimal("2510.00"),
        low=Decimal("2495.00"),
        close=Decimal("2505.00"),
        volume=Decimal("100.0"),
        closed=True,
    )


def stop_quote() -> Quote:
    now = datetime(2026, 8, 29, 12, 15, 5, tzinfo=UTC)
    return Quote(
        bid=Decimal("2490.00"),
        ask=Decimal("2491.00"),
        observed_at=now,
    )


@pytest.mark.asyncio
async def test_concurrent_same_candle_creates_one_intent(
    coordinator: ExecutionCoordinator,
) -> None:
    outcomes = await asyncio.gather(
        *[coordinator.evaluate(spot_scope("PAXGUSDT"), closed_candle()) for _ in range(5)]
    )
    assert sum(1 for o in outcomes if o.intent_created) == 1


@pytest.mark.asyncio
async def test_pause_blocks_entry_but_keeps_position_management(
    coordinator: ExecutionCoordinator,
) -> None:
    coordinator.pause_entries()
    hold_res = await coordinator.evaluate(spot_scope("PAXGUSDT"), closed_candle())
    assert hold_res.action == "HOLD"
    stop_res = await coordinator.manage_positions(spot_scope("PAXGUSDT"), stop_quote())
    assert stop_res.action == "STOP"

