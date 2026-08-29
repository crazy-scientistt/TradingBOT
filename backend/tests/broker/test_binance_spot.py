from __future__ import annotations

from decimal import Decimal

import pytest
from goldguard.broker.binance_spot import BinanceSpotBroker
from goldguard.domain.enums import ExecutionMode, OrderSide, ProductKind
from goldguard.exchange.binance_transport import BinanceTransport
from goldguard.execution.models import OrderIntent
from pydantic import SecretStr


@pytest.mark.asyncio
async def test_spot_order_submit() -> None:
    transport = BinanceTransport(api_key=SecretStr("key"), api_secret=SecretStr("secret"))
    broker = BinanceSpotBroker(transport)

    intent = OrderIntent(
        intent_id="i-1",
        client_order_id="gg-spot-1",
        mode=ExecutionMode.LIVE,
        product=ProductKind.SPOT,
        symbol="PAXGUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.05"),
        price=Decimal("2500.00"),
    )
    result = await broker.submit(intent)
    assert result.success is True
    assert result.order is not None
    assert result.order.symbol == "PAXGUSDT"

