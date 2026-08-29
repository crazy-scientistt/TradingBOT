from __future__ import annotations

from decimal import Decimal

import pytest
from goldguard.domain.enums import (
    ExecutionMode,
    MarginMode,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    ProductKind,
)
from goldguard.execution.models import (
    OrderIntent,
    OrderRecord,
    PositionRecord,
    ProtectionPlan,
)
from pydantic import ValidationError


def test_futures_intent_requires_isolated_margin_and_leverage() -> None:
    intent = OrderIntent.model_validate(
        {
            "intent_id": "intent-1",
            "client_order_id": "gg-1",
            "mode": "paper",
            "product": "futures",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "position_side": "LONG",
            "order_type": "MARKET",
            "quantity": "0.001",
            "margin_mode": "isolated",
            "leverage": 3,
            "reduce_only": False,
        }
    )
    assert intent.margin_mode == MarginMode.ISOLATED
    assert intent.leverage == 3
    assert intent.product == ProductKind.FUTURES


def test_futures_intent_rejects_cross_margin() -> None:
    with pytest.raises(ValidationError, match="isolated margin"):
        OrderIntent.model_validate(
            {
                "intent_id": "intent-1",
                "client_order_id": "gg-1",
                "mode": "paper",
                "product": "futures",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "position_side": "LONG",
                "order_type": "MARKET",
                "quantity": "0.001",
                "margin_mode": "cross",
                "leverage": 3,
            }
        )


def test_spot_intent_rejects_leverage_and_shorting() -> None:
    with pytest.raises(ValidationError, match="leverage"):
        OrderIntent.model_validate(
            {
                "intent_id": "intent-1",
                "client_order_id": "gg-1",
                "mode": "paper",
                "product": "spot",
                "symbol": "PAXGUSDT",
                "side": "BUY",
                "position_side": "LONG",
                "order_type": "MARKET",
                "quantity": "0.01",
                "leverage": 5,
            }
        )

    with pytest.raises(ValidationError, match="short"):
        OrderIntent.model_validate(
            {
                "intent_id": "intent-1",
                "client_order_id": "gg-1",
                "mode": "paper",
                "product": "spot",
                "symbol": "PAXGUSDT",
                "side": "SELL",
                "position_side": "SHORT",
                "order_type": "MARKET",
                "quantity": "0.01",
                "leverage": 1,
            }
        )


def test_order_record_and_fill_record_models() -> None:
    order = OrderRecord(
        order_id="ord-1",
        intent_id="intent-1",
        client_order_id="gg-1",
        mode=ExecutionMode.PAPER,
        product=ProductKind.FUTURES,
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        position_side=PositionSide.LONG,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
        status=OrderStatus.FILLED,
        filled_quantity=Decimal("0.01"),
        avg_price=Decimal("60000.00"),
        fee=Decimal("0.60"),
        created_at="2026-08-29T00:00:00+00:00",
        updated_at="2026-08-29T00:00:01+00:00",
    )
    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == Decimal("0.01")


def test_position_record_and_protection_plan() -> None:
    pos = PositionRecord(
        position_id="pos-1",
        mode=ExecutionMode.PAPER,
        product=ProductKind.FUTURES,
        symbol="ETHUSDT",
        side=PositionSide.LONG,
        quantity=Decimal("0.5"),
        entry_price=Decimal("2500.00"),
        current_price=Decimal("2550.00"),
        liquidation_price=Decimal("2000.00"),
        margin_mode=MarginMode.ISOLATED,
        leverage=5,
        isolated_margin=Decimal("250.00"),
        unrealized_pnl=Decimal("25.00"),
        opened_at="2026-08-29T00:00:00+00:00",
        updated_at="2026-08-29T00:00:10+00:00",
    )
    assert pos.unrealized_pnl == Decimal("25.00")

    plan = ProtectionPlan(
        position_id="pos-1",
        stop_loss_price=Decimal("2450.00"),
        take_profit_price=Decimal("2600.00"),
    )
    assert plan.stop_loss_price == Decimal("2450.00")

