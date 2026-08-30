from __future__ import annotations

from decimal import Decimal

import pytest
from goldguard.broker.paper_futures import PaperFuturesBroker
from goldguard.broker.paper_portfolio import PaperPortfolioBroker
from goldguard.broker.paper_spot import PaperSpotBroker
from goldguard.domain.enums import (
    ExecutionMode,
    ExitReason,
    MarginMode,
    OrderSide,
    OrderStatus,
    ProductKind,
)
from goldguard.execution.models import MarketScope, OrderIntent
from goldguard.services.emergency import EmergencyService


@pytest.mark.asyncio
async def test_emergency_service_closes_positions() -> None:
    spot = PaperSpotBroker(starting_cash=Decimal("1000.00"))
    futures = PaperFuturesBroker(starting_collateral=Decimal("1000.00"))
    broker = PaperPortfolioBroker(spot=spot, futures=futures)
    emergency = EmergencyService(broker=broker)

    # Open spot and futures positions
    await spot.submit(
        OrderIntent(
            intent_id="i-spot",
            client_order_id="c-spot",
            mode=ExecutionMode.PAPER,
            product=ProductKind.SPOT,
            symbol="PAXGUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            price=Decimal("2500.00"),
        )
    )
    await futures.submit(
        OrderIntent(
            intent_id="i-fut",
            client_order_id="c-fut",
            mode=ExecutionMode.PAPER,
            product=ProductKind.FUTURES,
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
            price=Decimal("60000.00"),
            margin_mode=MarginMode.ISOLATED,
            leverage=5,
        )
    )

    paxg_scope = MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol="PAXGUSDT")
    btc_scope = MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.FUTURES, symbol="BTCUSDT")

    # Ensure brokers have observed prices for close orders
    spot.on_price("PAXGUSDT", Decimal("2500.00"))
    futures.on_price("BTCUSDT", Decimal("60000.00"))

    closed = await emergency.close_owned_positions([paxg_scope, btc_scope], ExitReason.EMERGENCY)
    assert closed == 2

    snap = await broker.snapshot()
    assert snap.positions_count == 0


@pytest.mark.asyncio
async def test_emergency_cancels_open_orders() -> None:
    spot = PaperSpotBroker(starting_cash=Decimal("1000.00"))
    futures = PaperFuturesBroker(starting_collateral=Decimal("0"))
    broker = PaperPortfolioBroker(spot=spot, futures=futures)
    emergency = EmergencyService(broker=broker)
    spot.on_price("PAXGUSDT", Decimal("2500.00"))
    await spot.submit(
        OrderIntent(
            intent_id="i-open",
            client_order_id="c-open",
            mode=ExecutionMode.PAPER,
            product=ProductKind.SPOT,
            symbol="PAXGUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            price=Decimal("2500.00"),
        )
    )
    filled = spot._orders["c-open"]
    spot._orders["c-open"] = filled.model_copy(update={"status": OrderStatus.OPEN})
    scope = MarketScope(mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol="PAXGUSDT")
    cancelled = await emergency.cancel_entries([scope])
    assert cancelled == 1
    assert spot._orders["c-open"].status == OrderStatus.CANCELLED

