from __future__ import annotations

from decimal import Decimal

import pytest
from goldguard.broker.paper_futures import PaperFuturesBroker
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

