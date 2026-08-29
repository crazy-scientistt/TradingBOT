from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from goldguard.domain.enums import ExecutionMode, ProductKind
from goldguard.domain.models import Quote
from goldguard.execution.models import MarketScope
from goldguard.market.catalog import SymbolCatalog, SymbolNotEligible
from goldguard.services.market_supervisor import MarketSupervisor


class MockClock:
    def __init__(self, initial: datetime) -> None:
        self._current = initial

    def now(self) -> datetime:
        return self._current

    def advance(self, delta: timedelta) -> None:
        self._current += delta


def spot_scope(symbol: str) -> MarketScope:
    return MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol=symbol)


def futures_scope(symbol: str) -> MarketScope:
    return MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.FUTURES, symbol=symbol)


@pytest.mark.asyncio
async def test_supervisor_marks_silent_stream_stale() -> None:
    start_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    clock = MockClock(start_time)

    catalog = validated_catalog()
    paxg_scope = spot_scope("PAXGUSDT")
    btc_scope = futures_scope("BTCUSDT")

    supervisor = MarketSupervisor(catalog=catalog, clock=clock)
    await supervisor.start((paxg_scope, btc_scope))

    # Record fresh quotes
    quote_btc = Quote(
        symbol="BTCUSDT",
        bid=Decimal("60000.00"),
        ask=Decimal("60001.00"),
        last=Decimal("60000.50"),
        observed_at=clock.now(),
    )
    supervisor.record_quote(btc_scope, quote_btc)

    assert supervisor.fresh(btc_scope, timedelta(seconds=30)) is True

    # Advance clock beyond 30s
    clock.advance(timedelta(seconds=31))
    assert supervisor.fresh(btc_scope, timedelta(seconds=30)) is False

    await supervisor.stop()


def validated_catalog() -> SymbolCatalog:
    spot = AsyncMock()
    spot.exchange_info = AsyncMock(
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
    futures = AsyncMock()
    futures.exchange_info = AsyncMock(
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
                }
            ]
        }
    )
    return SymbolCatalog(spot_client=spot, futures_client=futures)


@pytest.mark.asyncio
async def test_supervisor_rejects_scope_not_proven_by_exchange_catalog() -> None:
    supervisor = MarketSupervisor(catalog=SymbolCatalog())

    with pytest.raises(SymbolNotEligible, match="not found"):
        await supervisor.start((spot_scope("PAXGUSDT"),))


@pytest.mark.asyncio
async def test_supervisor_polls_product_sources_and_owns_shutdown() -> None:
    start_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
    clock = MockClock(start_time)
    spot_source = AsyncMock()
    spot_source.quote = AsyncMock(
        return_value=Quote(
            bid=Decimal("2500"),
            ask=Decimal("2501"),
            observed_at=start_time,
        )
    )
    futures_source = AsyncMock()
    futures_source.quote = AsyncMock(
        return_value=Quote(
            bid=Decimal("60000"),
            ask=Decimal("60001"),
            observed_at=start_time,
        )
    )
    supervisor = MarketSupervisor(
        catalog=validated_catalog(),
        clock=clock,
        quote_sources={
            ProductKind.SPOT: spot_source,
            ProductKind.FUTURES: futures_source,
        },
        poll_seconds=0.01,
    )

    await supervisor.start((spot_scope("PAXGUSDT"), futures_scope("BTCUSDT")))

    assert supervisor.snapshot(spot_scope("PAXGUSDT")).latest_quote is not None
    assert supervisor.snapshot(futures_scope("BTCUSDT")).latest_quote is not None
    assert supervisor.running is True
    await supervisor.stop()
    assert supervisor.running is False
