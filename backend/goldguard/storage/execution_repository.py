from __future__ import annotations

from decimal import Decimal

from goldguard.domain.enums import (
    ExecutionMode,
    MarginMode,
    OrderSide,
    OrderType,
    PositionSide,
    PositionStatus,
    ProductKind,
    TimeInForce,
)
from goldguard.execution.models import (
    OrderIntent,
    OrderRecord,
    PositionRecord,
)
from goldguard.storage.database import Database


class ExecutionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_intent_once(self, intent: OrderIntent) -> tuple[OrderIntent, bool]:
        with self.database.transaction() as tx:
            existing = tx.execute(
                "SELECT * FROM execution_intents WHERE client_order_id = ?",
                (intent.client_order_id,),
            ).fetchone()
            if existing is not None:
                return (
                    OrderIntent(
                        intent_id=str(existing["intent_id"]),
                        client_order_id=str(existing["client_order_id"]),
                        mode=ExecutionMode(str(existing["mode"])),
                        product=ProductKind(str(existing["product"])),
                        symbol=str(existing["symbol"]),
                        side=OrderSide(str(existing["side"])),
                        position_side=PositionSide(str(existing["position_side"])),
                        order_type=OrderType(str(existing["order_type"])),
                        quantity=Decimal(str(existing["quantity_text"])),
                        price=(
                            Decimal(str(existing["price_text"]))
                            if existing["price_text"] is not None
                            else None
                        ),
                        stop_price=(
                            Decimal(str(existing["stop_price_text"]))
                            if existing["stop_price_text"] is not None
                            else None
                        ),
                        margin_mode=MarginMode(str(existing["margin_mode"])),
                        leverage=int(existing["leverage"]),
                        reduce_only=bool(existing["reduce_only"]),
                        time_in_force=TimeInForce(str(existing["time_in_force"])),
                        created_at=str(existing["created_at"]),
                        correlation_id=str(existing["correlation_id"] or ""),
                    ),
                    False,
                )

            tx.execute(
                "INSERT INTO execution_intents "
                "(intent_id, client_order_id, mode, product, symbol, side, position_side, "
                "order_type, quantity_text, price_text, stop_price_text, margin_mode, "
                "leverage, reduce_only, time_in_force, correlation_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    intent.intent_id,
                    intent.client_order_id,
                    intent.mode.value,
                    intent.product.value,
                    intent.symbol,
                    intent.side.value,
                    intent.position_side.value,
                    intent.order_type.value,
                    str(intent.quantity),
                    str(intent.price) if intent.price is not None else None,
                    str(intent.stop_price) if intent.stop_price is not None else None,
                    intent.margin_mode.value,
                    intent.leverage,
                    1 if intent.reduce_only else 0,
                    intent.time_in_force.value,
                    intent.correlation_id,
                    intent.created_at,
                ),
            )
            return intent, True

    def save_order(self, order: OrderRecord) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                "INSERT OR REPLACE INTO execution_orders "
                "(order_id, intent_id, client_order_id, mode, product, symbol, side, "
                "position_side, order_type, quantity_text, price_text, stop_price_text, "
                "status, filled_quantity_text, avg_price_text, fee_text, fee_asset, "
                "margin_mode, leverage, reduce_only, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order.order_id,
                    order.intent_id,
                    order.client_order_id,
                    order.mode.value,
                    order.product.value,
                    order.symbol,
                    order.side.value,
                    order.position_side.value,
                    order.order_type.value,
                    str(order.quantity),
                    str(order.price) if order.price is not None else None,
                    str(order.stop_price) if order.stop_price is not None else None,
                    order.status.value,
                    str(order.filled_quantity),
                    str(order.avg_price) if order.avg_price is not None else None,
                    str(order.fee),
                    order.fee_asset,
                    order.margin_mode.value,
                    order.leverage,
                    1 if order.reduce_only else 0,
                    order.created_at,
                    order.updated_at,
                ),
            )

    def save_position(self, position: PositionRecord) -> None:
        with self.database.transaction() as tx:
            tx.execute(
                "INSERT OR REPLACE INTO execution_positions "
                "(position_id, mode, product, symbol, side, quantity_text, entry_price_text, "
                "current_price_text, liquidation_price_text, margin_mode, leverage, "
                "isolated_margin_text, unrealized_pnl_text, realized_pnl_text, status, "
                "opened_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    position.position_id,
                    position.mode.value,
                    position.product.value,
                    position.symbol,
                    position.side.value,
                    str(position.quantity),
                    str(position.entry_price),
                    str(position.current_price) if position.current_price is not None else None,
                    (
                        str(position.liquidation_price)
                        if position.liquidation_price is not None
                        else None
                    ),
                    position.margin_mode.value,
                    position.leverage,
                    str(position.isolated_margin),
                    str(position.unrealized_pnl),
                    str(position.realized_pnl),
                    position.status.value,
                    position.opened_at,
                    position.updated_at,
                ),
            )

    def get_open_positions(self, mode: ExecutionMode) -> list[PositionRecord]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM execution_positions WHERE mode = ? AND status = 'OPEN'",
                (mode.value,),
            ).fetchall()
            return [
                PositionRecord(
                    position_id=str(r["position_id"]),
                    mode=ExecutionMode(str(r["mode"])),
                    product=ProductKind(str(r["product"])),
                    symbol=str(r["symbol"]),
                    side=PositionSide(str(r["side"])),
                    quantity=Decimal(str(r["quantity_text"])),
                    entry_price=Decimal(str(r["entry_price_text"])),
                    current_price=(
                        Decimal(str(r["current_price_text"]))
                        if r["current_price_text"] is not None
                        else None
                    ),
                    liquidation_price=(
                        Decimal(str(r["liquidation_price_text"]))
                        if r["liquidation_price_text"] is not None
                        else None
                    ),
                    margin_mode=MarginMode(str(r["margin_mode"])),
                    leverage=int(r["leverage"]),
                    isolated_margin=Decimal(str(r["isolated_margin_text"])),
                    unrealized_pnl=Decimal(str(r["unrealized_pnl_text"])),
                    realized_pnl=Decimal(str(r["realized_pnl_text"])),
                    opened_at=str(r["opened_at"]),
                    updated_at=str(r["updated_at"]),
                    status=PositionStatus.OPEN,
                )
                for r in rows
            ]

