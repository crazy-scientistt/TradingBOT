from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from goldguard.domain.enums import (
    ExecutionMode,
    MarginMode,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    ProductKind,
)
from goldguard.execution.models import OrderIntent, OrderRecord, PositionRecord
from goldguard.storage.database import Database
from goldguard.storage.execution_repository import ExecutionRepository


def test_execution_repository_intents_orders_positions(tmp_path: Path) -> None:
    db = Database(tmp_path / "repo_test.db")
    db.migrate()
    repo = ExecutionRepository(db)

    intent = OrderIntent(
        intent_id="i-1",
        client_order_id="c-1",
        mode=ExecutionMode.PAPER,
        product=ProductKind.SPOT,
        symbol="PAXGUSDT",
        side=OrderSide.BUY,
        position_side=PositionSide.LONG,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
        price=Decimal("2500.00"),
    )

    saved_intent, created = repo.create_intent_once(intent)
    assert created is True
    assert saved_intent.client_order_id == "c-1"

    # Duplicate intent attempt
    saved_again, created_again = repo.create_intent_once(intent)
    assert created_again is False
    assert saved_again.client_order_id == "c-1"

    # Save order and position
    order = OrderRecord(
        order_id="ord-1",
        intent_id="i-1",
        client_order_id="c-1",
        mode=ExecutionMode.PAPER,
        product=ProductKind.SPOT,
        symbol="PAXGUSDT",
        side=OrderSide.BUY,
        position_side=PositionSide.LONG,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
        status=OrderStatus.FILLED,
        filled_quantity=Decimal("0.1"),
        avg_price=Decimal("2500.00"),
        fee=Decimal("0.25"),
        created_at="2026-08-29T00:00:00+00:00",
        updated_at="2026-08-29T00:00:01+00:00",
    )
    repo.save_order(order)

    pos = PositionRecord(
        position_id="pos-1",
        mode=ExecutionMode.PAPER,
        product=ProductKind.SPOT,
        symbol="PAXGUSDT",
        side=PositionSide.LONG,
        quantity=Decimal("0.1"),
        entry_price=Decimal("2500.00"),
        current_price=Decimal("2550.00"),
        margin_mode=MarginMode.ISOLATED,
        leverage=1,
        isolated_margin=Decimal("250.00"),
        unrealized_pnl=Decimal("5.00"),
        opened_at="2026-08-29T00:00:00+00:00",
        updated_at="2026-08-29T00:00:05+00:00",
    )
    repo.save_position(pos)

    open_positions = repo.get_open_positions(ExecutionMode.PAPER)
    assert len(open_positions) == 1
    assert open_positions[0].symbol == "PAXGUSDT"

