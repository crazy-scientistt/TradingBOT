from __future__ import annotations

from decimal import Decimal

import pytest
from goldguard.risk.circuit_breaker import CircuitBreaker


@pytest.mark.asyncio
async def test_loss_limit_cancels_entries_and_trips_breaker() -> None:
    breaker = CircuitBreaker()
    # Realized loss: -20, unrealized loss: -5, fees: 2, funding: 1, slippage: 1 => Total 29
    breaker.seed_loss(realized="-20", unrealized="-5", fees="2", funding="1", slippage="1")
    res = await breaker.evaluate(limit_usdt=Decimal("25"))
    assert res.tripped is True
    assert res.total_loss_usdt == Decimal("29")

