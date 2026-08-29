from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any

from goldguard.domain.enums import (
    ExecutionMode,
    MarginMode,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductKind,
)
from goldguard.execution.models import ExecutionResult, OrderIntent, OrderRecord

BINANCE_STATUS_MAP = {
    "NEW": OrderStatus.OPEN,
    "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
    "FILLED": OrderStatus.FILLED,
    "CANCELED": OrderStatus.CANCELLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
    "EXPIRED": OrderStatus.EXPIRED,
    "PENDING_CANCEL": OrderStatus.OPEN,
}

SPOT_QTY_STEP = Decimal("0.0001")
FUTURES_QTY_STEP = Decimal("0.001")
SPOT_MIN_NOTIONAL = Decimal("10")


def quantize_qty(qty: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return qty
    return (qty / step).to_integral_value(rounding=ROUND_DOWN) * step


def map_binance_status(raw: object) -> OrderStatus | None:
    if not isinstance(raw, str):
        return None
    return BINANCE_STATUS_MAP.get(raw.upper())


def decimal_field(payload: dict[str, Any], *keys: str) -> Decimal | None:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return Decimal(str(payload[key]))
    return None


def result_from_binance_payload(
    intent: OrderIntent,
    payload: object,
    quantity: Decimal,
    *,
    product: ProductKind,
) -> ExecutionResult:
    if not isinstance(payload, dict):
        return ExecutionResult(
            success=False,
            error_code="MALFORMED_EXCHANGE_RESPONSE",
            error_message="exchange response was not an object",
        )

    status = map_binance_status(payload.get("status"))
    if status is None:
        return ExecutionResult(
            success=False,
            error_code="MALFORMED_EXCHANGE_RESPONSE",
            error_message="exchange status missing",
        )

    filled = decimal_field(payload, "executedQty", "executed_qty", "origQty")
    executed = decimal_field(payload, "executedQty", "executed_qty")
    if status == OrderStatus.FILLED and executed is None:
        return ExecutionResult(
            success=False,
            error_code="MALFORMED_EXCHANGE_RESPONSE",
            error_message="filled status without executed quantity",
        )

    exchange_order_id = payload.get("orderId", payload.get("order_id"))
    if exchange_order_id in (None, ""):
        return ExecutionResult(
            success=False,
            error_code="MALFORMED_EXCHANGE_RESPONSE",
            error_message="exchange order id missing",
        )

    avg = decimal_field(payload, "avgPrice", "price")
    now = datetime.now(UTC).isoformat()
    order = OrderRecord(
        order_id=str(exchange_order_id),
        intent_id=intent.intent_id,
        client_order_id=intent.client_order_id,
        mode=ExecutionMode.LIVE,
        product=product,
        symbol=intent.symbol,
        side=intent.side if isinstance(intent.side, OrderSide) else OrderSide(str(intent.side)),
        position_side=intent.position_side,
        order_type=(
            intent.order_type
            if isinstance(intent.order_type, OrderType)
            else OrderType(str(intent.order_type))
        ),
        quantity=quantity,
        price=intent.price,
        status=status,
        filled_quantity=filled if filled is not None else Decimal("0"),
        avg_price=avg,
        margin_mode=intent.margin_mode if product == ProductKind.FUTURES else MarginMode.ISOLATED,
        leverage=intent.leverage,
        reduce_only=intent.reduce_only,
        created_at=intent.created_at,
        updated_at=now,
    )
    success = status in {
        OrderStatus.FILLED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.OPEN,
        OrderStatus.PENDING,
    }
    return ExecutionResult(success=success, order=order)
