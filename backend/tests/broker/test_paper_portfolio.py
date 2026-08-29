from __future__ import annotations

from decimal import Decimal

import pytest
from goldguard.broker.paper_futures import PaperFuturesBroker
from goldguard.broker.paper_portfolio import PaperPortfolioBroker
from goldguard.broker.paper_spot import PaperSpotBroker
from goldguard.domain.enums import (
    ExecutionMode,
    MarginMode,
    OrderSide,
    OrderType,
    PositionSide,
    ProductKind,
)
from goldguard.execution.models import OrderIntent


@pytest.mark.asyncio
async def test_portfolio_broker_delegates_by_product() -> None:
    spot = PaperSpotBroker(starting_cash=Decimal("500.00"))
    futures = PaperFuturesBroker(starting_collateral=Decimal("500.00"))
    portfolio = PaperPortfolioBroker(spot=spot, futures=futures)

    snapshot_init = await portfolio.snapshot()
    assert snapshot_init.total_equity_usdt == Decimal("1000.00")
    assert snapshot_init.positions_count == 0

    # Submit spot buy
    spot_intent = OrderIntent(
        intent_id="i-spot",
        client_order_id="c-spot",
        mode=ExecutionMode.PAPER,
        product=ProductKind.SPOT,
        symbol="PAXGUSDT",
        side=OrderSide.BUY,
        position_side=PositionSide.LONG,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
        price=Decimal("1000.00"),
    )
    res_spot = await portfolio.submit(spot_intent)
    assert res_spot.success is True

    # Submit futures short
    futures_intent = OrderIntent(
        intent_id="i-fut",
        client_order_id="c-fut",
        mode=ExecutionMode.PAPER,
        product=ProductKind.FUTURES,
        symbol="ETHUSDT",
        side=OrderSide.SELL,
        position_side=PositionSide.SHORT,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
        price=Decimal("2000.00"),
        margin_mode=MarginMode.ISOLATED,
        leverage=10,
    )
    res_fut = await portfolio.submit(futures_intent)
    assert res_fut.success is True

    snapshot = await portfolio.snapshot()
    assert snapshot.positions_count == 2

