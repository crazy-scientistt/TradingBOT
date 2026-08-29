from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter

from goldguard.domain.enums import ExecutionMode
from goldguard.storage.execution_repository import ExecutionRepository
from goldguard.web.schemas.dashboard import (
    AvailabilityEnvelope,
    OrderItemSchema,
    PositionItemSchema,
)

router = APIRouter(prefix="/api", tags=["execution_views"])


@router.get("/orders", response_model=AvailabilityEnvelope[list[OrderItemSchema]])
def get_orders() -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    from goldguard.web import app as app_module

    orders: list[dict[str, Any]] = []
    if app_module._db is not None:
        with app_module._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM execution_orders ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
            for r in rows:
                orders.append(
                    {
                        "order_id": str(r["order_id"]),
                        "client_order_id": str(r["client_order_id"]),
                        "symbol": str(r["symbol"]),
                        "product": str(r["product"]),
                        "side": str(r["side"]),
                        "order_type": str(r["order_type"]),
                        "quantity": str(r["quantity_text"]),
                        "price": (
                            str(r["price_text"]) if r["price_text"] is not None else None
                        ),
                        "status": str(r["status"]),
                        "created_at": str(r["created_at"]),
                    }
                )

    return {
        "availability": "available",
        "source": "execution_ledger",
        "observed_at": now,
        "stale": False,
        "detail": None if orders else "no orders placed yet",
        "data": orders,
    }


@router.get("/positions", response_model=AvailabilityEnvelope[list[PositionItemSchema]])
def get_positions() -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    from goldguard.web import app as app_module

    positions: list[dict[str, Any]] = []
    if app_module._db is not None:
        repo = ExecutionRepository(app_module._db)
        open_pos = repo.get_open_positions(ExecutionMode.PAPER)
        for pos in open_pos:
            curr = pos.current_price or pos.entry_price
            if pos.side.value == "LONG":
                gross = (curr - pos.entry_price) * pos.quantity
            else:
                gross = (pos.entry_price - curr) * pos.quantity
            fee = pos.entry_price * pos.quantity * Decimal("0.0005")
            funding = Decimal("0")
            slippage = Decimal("0")
            net = gross - fee - funding - slippage
            positions.append(
                {
                    "position_id": pos.position_id,
                    "symbol": pos.symbol,
                    "product": pos.product.value,
                    "side": pos.side.value,
                    "quantity": str(pos.quantity),
                    "entry_price": str(pos.entry_price),
                    "current_price": str(curr),
                    "gross_pnl_usdt": str(gross.quantize(Decimal("0.01"))),
                    "fees_usdt": str(fee.quantize(Decimal("0.01"))),
                    "funding_usdt": str(funding.quantize(Decimal("0.01"))),
                    "slippage_usdt": str(slippage.quantize(Decimal("0.01"))),
                    "net_pnl_usdt": str(net.quantize(Decimal("0.01"))),
                    "leverage": pos.leverage,
                }
            )

    return {
        "availability": "available",
        "source": "execution_positions",
        "observed_at": now,
        "stale": False,
        "detail": None if positions else "no open positions",
        "data": positions,
    }

