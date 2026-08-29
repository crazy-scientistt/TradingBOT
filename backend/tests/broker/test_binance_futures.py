from __future__ import annotations

from decimal import Decimal

import pytest
from goldguard.broker.binance_futures import BinanceFuturesBroker
from goldguard.domain.enums import ExecutionMode, MarginMode, OrderSide, PositionSide, ProductKind
from goldguard.exchange.binance_transport import BinanceTransport
from goldguard.execution.models import OrderIntent
from pydantic import SecretStr


@pytest.mark.asyncio
async def test_futures_configures_isolated_and_approved_leverage() -> None:
    transport = BinanceTransport(api_key=SecretStr("key"), api_secret=SecretStr("secret"))
    broker = BinanceFuturesBroker(transport)

    intent = OrderIntent(
        intent_id="i-1",
        client_order_id="gg-fut-1",
        mode=ExecutionMode.LIVE,
        product=ProductKind.FUTURES,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        position_side=PositionSide.LONG,
        quantity=Decimal("0.01"),
        price=Decimal("60000.00"),
        margin_mode=MarginMode.ISOLATED,
        leverage=4,
    )
    result = await broker.submit(intent)
    assert result.success is True
    assert result.order is not None
    assert result.order.leverage == 4

