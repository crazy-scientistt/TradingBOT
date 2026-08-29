from __future__ import annotations

from decimal import Decimal

import pytest
from goldguard.broker.binance_spot import BinanceSpotBroker
from goldguard.domain.enums import ExecutionMode, OrderSide, OrderStatus, ProductKind
from goldguard.exchange.binance_transport import BinanceTransport, BinanceTransportError
from goldguard.execution.models import OrderIntent
from pydantic import SecretStr
from tests.exchange.fake_binance import FakeBinance


def _transport(fake: FakeBinance) -> BinanceTransport:
    return BinanceTransport(
        api_key=SecretStr("key"),
        api_secret=SecretStr("secret"),
        client=fake,
    )


def _intent(quantity: str = "0.05", price: str = "2500.00") -> OrderIntent:
    return OrderIntent(
        intent_id="i-1",
        client_order_id="gg-spot-1",
        mode=ExecutionMode.LIVE,
        product=ProductKind.SPOT,
        symbol="PAXGUSDT",
        side=OrderSide.BUY,
        quantity=Decimal(quantity),
        price=Decimal(price),
    )


@pytest.mark.asyncio
async def test_spot_order_submit() -> None:
    fake = FakeBinance()
    broker = BinanceSpotBroker(_transport(fake))
    result = await broker.submit(_intent())
    assert result.success is True
    assert result.order is not None
    assert result.order.symbol == "PAXGUSDT"
    assert result.order.status == OrderStatus.FILLED
    assert result.order.order_id == "1001"


@pytest.mark.asyncio
async def test_spot_order_respects_step_and_min_notional() -> None:
    fake = FakeBinance()
    broker = BinanceSpotBroker(_transport(fake))
    result = await broker.submit(_intent(quantity="0.001234", price="25000"))
    assert result.success is True
    assert result.order is not None
    assert result.order.quantity == Decimal("0.0012")


@pytest.mark.asyncio
async def test_timeout_queries_before_retry() -> None:
    fake = FakeBinance()
    fake.timeout_after_accept = True
    broker = BinanceSpotBroker(_transport(fake))
    result = await broker.submit(_intent())
    assert result.success is True
    assert result.order is not None
    assert result.order.order_id == fake.accepted_order_id
    assert fake.post_count == 1
    assert fake.get_count == 1


@pytest.mark.asyncio
async def test_missing_status_does_not_invent_filled() -> None:
    fake = FakeBinance()
    fake.malformed_status = True
    broker = BinanceSpotBroker(_transport(fake))
    result = await broker.submit(_intent())
    assert result.success is False
    assert result.order is None
    assert result.error_code == "MALFORMED_EXCHANGE_RESPONSE"


@pytest.mark.asyncio
async def test_transport_without_client_does_not_fabricate() -> None:
    transport = BinanceTransport(api_key=SecretStr("key"), api_secret=SecretStr("secret"))
    with pytest.raises(BinanceTransportError):
        await transport.request(ProductKind.SPOT, "GET", "/api/v3/time", {}, signed=False)
