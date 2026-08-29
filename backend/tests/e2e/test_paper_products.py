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
    PositionSide,
    ProductKind,
)
from goldguard.execution.models import OrderIntent


@pytest.mark.asyncio
async def test_multi_pair_spot_and_futures_paper_trading() -> None:
    spot = PaperSpotBroker(starting_cash=Decimal("5000.00"))
    futures = PaperFuturesBroker(starting_collateral=Decimal("5000.00"))
    portfolio = PaperPortfolioBroker(spot=spot, futures=futures)

    # 1. Spot PAXG
    spot_res = await portfolio.submit(
        OrderIntent(
            intent_id="i-1",
            client_order_id="c-1",
            mode=ExecutionMode.PAPER,
            product=ProductKind.SPOT,
            symbol="PAXGUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("1.0"),
            price=Decimal("2500.00"),
        )
    )
    assert spot_res.success is True

    # 2. Futures BTC Long
    btc_res = await portfolio.submit(
        OrderIntent(
            intent_id="i-2",
            client_order_id="c-2",
            mode=ExecutionMode.PAPER,
            product=ProductKind.FUTURES,
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            position_side=PositionSide.LONG,
            quantity=Decimal("0.05"),
            price=Decimal("60000.00"),
            margin_mode=MarginMode.ISOLATED,
            leverage=10,
        )
    )
    assert btc_res.success is True

    # 3. Futures ETH Short
    eth_res = await portfolio.submit(
        OrderIntent(
            intent_id="i-3",
            client_order_id="c-3",
            mode=ExecutionMode.PAPER,
            product=ProductKind.FUTURES,
            symbol="ETHUSDT",
            side=OrderSide.SELL,
            position_side=PositionSide.SHORT,
            quantity=Decimal("0.5"),
            price=Decimal("2500.00"),
            margin_mode=MarginMode.ISOLATED,
            leverage=5,
        )
    )
    assert eth_res.success is True

    snap = await portfolio.snapshot()
    assert snap.positions_count == 3

