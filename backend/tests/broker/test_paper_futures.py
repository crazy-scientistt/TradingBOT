from __future__ import annotations

from decimal import Decimal

import pytest
from goldguard.broker.paper_futures import FuturesOrderRejected, PaperFuturesBroker
from goldguard.domain.enums import (
    ExecutionMode,
    ExitReason,
    MarginMode,
    OrderSide,
    OrderType,
    PositionSide,
    PositionStatus,
    ProductKind,
)
from goldguard.execution.models import OrderIntent


@pytest.fixture
def futures_broker() -> PaperFuturesBroker:
    return PaperFuturesBroker(
        starting_collateral=Decimal("100.00"),
        fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0"),
    )


@pytest.mark.asyncio
async def test_futures_position_is_isolated_and_cost_adjusted(
    futures_broker: PaperFuturesBroker,
) -> None:
    # 0.001 BTC @ 50000 = $50 notional. At 5x leverage -> $10 margin.
    intent = OrderIntent(
        intent_id="i-1",
        client_order_id="c-1",
        mode=ExecutionMode.PAPER,
        product=ProductKind.FUTURES,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        position_side=PositionSide.LONG,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.001"),
        price=Decimal("50000.00"),
        margin_mode=MarginMode.ISOLATED,
        leverage=5,
    )
    result = await futures_broker.submit(intent)
    assert result.success is True
    position = result.position
    assert position is not None
    assert position.margin_mode == MarginMode.ISOLATED
    assert position.isolated_margin == Decimal("10.00")

    # Apply funding
    futures_broker.apply_funding("BTCUSDT", Decimal("0.0001"))
    assert futures_broker.collateral < Decimal("100.00") - Decimal("10.00")

    # Price update & close
    futures_broker.on_price("BTCUSDT", Decimal("55000.00"))
    close_res = await futures_broker.close(position.position_id, ExitReason.TAKE_PROFIT)
    assert close_res.success is True
    assert close_res.position is not None
    assert close_res.position.status == PositionStatus.CLOSED


@pytest.mark.asyncio
async def test_futures_rejects_order_without_observed_or_explicit_price() -> None:
    broker = PaperFuturesBroker(starting_collateral=Decimal("1000.00"))
    intent = OrderIntent(
        intent_id="missing-price",
        client_order_id="missing-price",
        mode=ExecutionMode.PAPER,
        product=ProductKind.FUTURES,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        position_side=PositionSide.LONG,
        quantity=Decimal("0.01"),
        margin_mode=MarginMode.ISOLATED,
        leverage=2,
    )

    with pytest.raises(FuturesOrderRejected, match="market price"):
        await broker.submit(intent)


@pytest.mark.asyncio
async def test_futures_one_way_mode_rejects_opposing_open_position() -> None:
    broker = PaperFuturesBroker(starting_collateral=Decimal("10000.00"))
    await broker.submit(
        OrderIntent(
            intent_id="long",
            client_order_id="long",
            mode=ExecutionMode.PAPER,
            product=ProductKind.FUTURES,
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            position_side=PositionSide.LONG,
            quantity=Decimal("0.01"),
            price=Decimal("60000"),
            margin_mode=MarginMode.ISOLATED,
            leverage=2,
        )
    )

    with pytest.raises(FuturesOrderRejected, match="one-way"):
        await broker.submit(
            OrderIntent(
                intent_id="short",
                client_order_id="short",
                mode=ExecutionMode.PAPER,
                product=ProductKind.FUTURES,
                symbol="BTCUSDT",
                side=OrderSide.SELL,
                position_side=PositionSide.SHORT,
                quantity=Decimal("0.01"),
                price=Decimal("60000"),
                margin_mode=MarginMode.ISOLATED,
                leverage=2,
            )
        )
