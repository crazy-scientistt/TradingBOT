from __future__ import annotations

from decimal import Decimal

import pytest
from goldguard.broker.binance_futures import BinanceFuturesBroker
from goldguard.domain.enums import ExecutionMode, MarginMode, OrderSide, PositionSide, ProductKind
from goldguard.exchange.binance_transport import BinanceTransport
from goldguard.execution.models import OrderIntent
from pydantic import SecretStr
from tests.exchange.fake_binance import FakeBinance


@pytest.mark.asyncio
async def test_futures_configures_isolated_and_approved_leverage() -> None:
    fake = FakeBinance()
    transport = BinanceTransport(
        api_key=SecretStr("key"), api_secret=SecretStr("secret"), client=fake
    )
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
    assert result.order.order_id == "1001"


@pytest.mark.asyncio
async def test_futures_timeout_does_not_duplicate_submit() -> None:
    fake = FakeBinance()
    fake.timeout_after_accept = True
    transport = BinanceTransport(
        api_key=SecretStr("key"), api_secret=SecretStr("secret"), client=fake
    )
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
    assert fake.post_count == 1
    assert fake.get_count == 1
