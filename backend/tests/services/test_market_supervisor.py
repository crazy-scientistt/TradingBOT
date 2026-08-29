from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from goldguard.domain.enums import ExecutionMode, ProductKind
from goldguard.domain.models import Quote
from goldguard.execution.models import MarketScope
from goldguard.market.catalog import SymbolCatalog
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

    catalog = SymbolCatalog()
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

