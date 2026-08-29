from __future__ import annotations

from decimal import Decimal

import pytest
from goldguard.broker.paper_spot import (
    InsufficientBalance,
    PaperSpotBroker,
    SpotOrderRejected,
)
from goldguard.domain.enums import (
    ExecutionMode,
    OrderSide,
    OrderType,
    PositionSide,
    PositionStatus,
    ProductKind,
)
from goldguard.execution.models import OrderIntent


@pytest.fixture
def spot_broker() -> PaperSpotBroker:
    return PaperSpotBroker(
        starting_cash=Decimal("100.00"),
        fee_rate=Decimal("0.001"),
        slippage_rate=Decimal("0"),
    )


@pytest.mark.asyncio
async def test_spot_cannot_spend_more_than_available_cash(
    spot_broker: PaperSpotBroker,
) -> None:
    intent = OrderIntent(
        intent_id="i-1",
        client_order_id="c-1",
        mode=ExecutionMode.PAPER,
        product=ProductKind.SPOT,
        symbol="PAXGUSDT",
        side=OrderSide.BUY,
        position_side=PositionSide.LONG,
        order_type=OrderType.MARKET,
        quantity=Decimal("1.0"),
        price=Decimal("101.00"),
    )
    with pytest.raises(InsufficientBalance):
        await spot_broker.submit(intent)


@pytest.mark.asyncio
async def test_spot_rejects_order_without_observed_or_explicit_price() -> None:
    broker = PaperSpotBroker(starting_cash=Decimal("1000.00"))
    intent = OrderIntent(
        intent_id="missing-price",
        client_order_id="missing-price",
        mode=ExecutionMode.PAPER,
        product=ProductKind.SPOT,
        symbol="PAXGUSDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.1"),
    )

    with pytest.raises(SpotOrderRejected, match="market price"):
        await broker.submit(intent)


@pytest.mark.asyncio
async def test_spot_buy_and_sell_cycle(spot_broker: PaperSpotBroker) -> None:
    buy_intent = OrderIntent(
        intent_id="i-1",
        client_order_id="c-1",
        mode=ExecutionMode.PAPER,
        product=ProductKind.SPOT,
        symbol="PAXGUSDT",
        side=OrderSide.BUY,
        position_side=PositionSide.LONG,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.05"),
        price=Decimal("1000.00"),
    )
    res = await spot_broker.submit(buy_intent)
    assert res.success is True
    assert res.position is not None
    assert res.position.quantity == Decimal("0.05")
    assert spot_broker.cash == Decimal("100.00") - Decimal("50.00") - Decimal("0.05")

    # Update price and check snapshot
    spot_broker.on_price("PAXGUSDT", Decimal("1100.00"))
    snapshot = await spot_broker.snapshot()
    assert snapshot.unrealized_pnl_usdt == Decimal("5.00")

    # Sell
    sell_intent = OrderIntent(
        intent_id="i-2",
        client_order_id="c-2",
        mode=ExecutionMode.PAPER,
        product=ProductKind.SPOT,
        symbol="PAXGUSDT",
        side=OrderSide.SELL,
        position_side=PositionSide.LONG,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.05"),
        price=Decimal("1100.00"),
        reduce_only=True,
    )
    sell_res = await spot_broker.submit(sell_intent)
    assert sell_res.success is True
    assert sell_res.position is not None
    assert sell_res.position.status == PositionStatus.CLOSED
