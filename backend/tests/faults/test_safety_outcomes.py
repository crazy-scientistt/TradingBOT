from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from goldguard.broker.paper_futures import PaperFuturesBroker
from goldguard.broker.paper_portfolio import PaperPortfolioBroker
from goldguard.broker.paper_spot import PaperSpotBroker
from goldguard.domain.enums import ExecutionMode, OrderSide, PositionSide, ProductKind
from goldguard.domain.models import Candle
from goldguard.domain.profile import default_autonomous_profile
from goldguard.execution.models import ExecutionResult, MarketScope, OrderIntent
from goldguard.market.catalog import SymbolCatalog
from goldguard.risk.circuit_breaker import CircuitBreaker
from goldguard.services.emergency import EmergencyService
from goldguard.services.execution_coordinator import EntryPlan, ExecutionCoordinator
from goldguard.services.market_supervisor import MarketSupervisor
from goldguard.services.runtime_supervisor import RuntimeSupervisor
from goldguard.storage.database import Database
from goldguard.storage.execution_repository import ExecutionRepository


class TimeoutAfterAcceptBroker(PaperPortfolioBroker):
    """Accepts the first submit on the inner broker, then times out to the caller."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.submit_calls = 0

    async def submit(self, intent: OrderIntent) -> ExecutionResult:
        self.submit_calls += 1
        result = await super().submit(intent)
        if self.submit_calls == 1:
            raise TimeoutError("timeout after accept")
        return result


def _closed_candle() -> Candle:
    close_time = datetime(2026, 8, 29, 12, 15, tzinfo=UTC)
    open_time = close_time - timedelta(minutes=15)
    return Candle(
        symbol="PAXGUSDT",
        timeframe="15m",
        open_time=open_time,
        close_time=close_time,
        open=Decimal("2500.00"),
        high=Decimal("2510.00"),
        low=Decimal("2490.00"),
        close=Decimal("2505.00"),
        volume=Decimal("12.0"),
        closed=True,
    )


def _spot_scope() -> MarketScope:
    return MarketScope(
        mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol="PAXGUSDT"
    )


def _futures_scope(symbol: str) -> MarketScope:
    return MarketScope(
        mode=ExecutionMode.PAPER, product=ProductKind.FUTURES, symbol=symbol
    )


def _fake_spot_client() -> AsyncMock:
    client = AsyncMock()
    client.exchange_info = AsyncMock(
        return_value={
            "symbols": [
                {
                    "symbol": "PAXGUSDT",
                    "status": "TRADING",
                    "baseAsset": "PAXG",
                    "quoteAsset": "USDT",
                    "filters": [
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                        {
                            "filterType": "LOT_SIZE",
                            "stepSize": "0.0001",
                            "minQty": "0.0001",
                            "maxQty": "1000",
                        },
                        {"filterType": "NOTIONAL", "minNotional": "5"},
                    ],
                }
            ]
        }
    )
    return client


def _fake_futures_client() -> AsyncMock:
    client = AsyncMock()
    client.exchange_info = AsyncMock(
        return_value={
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "filters": [
                        {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                        {
                            "filterType": "LOT_SIZE",
                            "stepSize": "0.001",
                            "minQty": "0.001",
                            "maxQty": "1000",
                        },
                        {"filterType": "MIN_NOTIONAL", "notional": "5"},
                    ],
                },
                {
                    "symbol": "ETHUSDT",
                    "status": "TRADING",
                    "baseAsset": "ETH",
                    "quoteAsset": "USDT",
                    "filters": [
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                        {
                            "filterType": "LOT_SIZE",
                            "stepSize": "0.001",
                            "minQty": "0.001",
                            "maxQty": "1000",
                        },
                        {"filterType": "MIN_NOTIONAL", "notional": "5"},
                    ],
                },
            ]
        }
    )
    return client


@pytest.mark.asyncio
async def test_timeout_after_accept_does_not_duplicate_order(tmp_path: Path) -> None:
    db = Database(tmp_path / "fault_timeout.db")
    db.migrate()
    broker = TimeoutAfterAcceptBroker(
        spot=PaperSpotBroker(starting_cash=Decimal("10000.00")),
        futures=PaperFuturesBroker(starting_collateral=Decimal("10000.00")),
    )
    coordinator = ExecutionCoordinator(
        broker=broker,
        repository=ExecutionRepository(db),
        database=db,
        entry_planner=lambda _scope, _candle: EntryPlan(
            approved=True,
            reason="qualified_test_entry",
            side=OrderSide.BUY,
            position_side=PositionSide.LONG,
            quantity=Decimal("0.01"),
            leverage=1,
            stop_loss_price=Decimal("2495.00"),
            take_profit_price=Decimal("2600.00"),
        ),
    )
    candle = _closed_candle()
    scope = _spot_scope()

    with pytest.raises(TimeoutError):
        await coordinator.evaluate(scope, candle)
    assert broker.submit_calls == 1

    retry = await coordinator.evaluate(scope, candle)
    assert retry.action == "HOLD"
    assert retry.reason == "duplicate_intent"
    assert broker.submit_calls == 1


@pytest.mark.asyncio
async def test_gateway_outage_holds_entries_but_does_not_block_stop(
    tmp_path: Path,
) -> None:
    db = Database(tmp_path / "fault_gateway.db")
    db.migrate()
    profile = default_autonomous_profile()
    catalog = SymbolCatalog(
        spot_client=_fake_spot_client(),
        futures_client=_fake_futures_client(),
    )
    market = MarketSupervisor(catalog=catalog)
    broker = PaperPortfolioBroker(
        spot=PaperSpotBroker(starting_cash=Decimal("10000.00")),
        futures=PaperFuturesBroker(starting_collateral=Decimal("10000.00")),
    )
    coordinator = ExecutionCoordinator(
        broker=broker,
        repository=ExecutionRepository(db),
        database=db,
    )
    system = RuntimeSupervisor(
        profile=profile,
        market=market,
        broker=broker,
        coordinator=coordinator,
        breaker=CircuitBreaker(),
        emergency=EmergencyService(broker=broker, coordinator=coordinator),
    )
    await system.start()
    btc = _futures_scope("BTCUSDT")
    assert system.new_entries_allowed(btc) is True

    # Gateway/OpenCodex outage: HOLD new entries. Pause/stop must still run.
    await system.pause()
    assert system.new_entries_allowed(btc) is False
    hold = await coordinator.evaluate(_spot_scope(), _closed_candle())
    assert hold.action == "HOLD"

    await system.stop()
    assert system.new_entries_allowed(btc) is False
    assert system._running is False
