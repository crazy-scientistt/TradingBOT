from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter

from goldguard.domain.enums import ExecutionMode
from goldguard.operations.stack import collect_stack_diagnostics
from goldguard.readmodels.dashboard import DashboardReadModel
from goldguard.storage.execution_repository import ExecutionRepository
from goldguard.web.schemas.dashboard import (
    AvailabilityEnvelope,
    OrderItemSchema,
    PositionItemSchema,
)

router = APIRouter(prefix="/api", tags=["execution_views"])


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _envelope(
    data: Any,
    *,
    source: str,
    detail: str | None,
    stale: bool = False,
    availability: str = "available",
) -> dict[str, Any]:
    return {
        "availability": availability,
        "source": source,
        "observed_at": _now(),
        "stale": stale,
        "detail": detail,
        "data": data,
    }


@router.get("/orders", response_model=AvailabilityEnvelope[list[OrderItemSchema]])
def get_orders() -> dict[str, Any]:
    now = _now()
    from goldguard.web import app as app_module

    orders: list[dict[str, Any]] = []
    if app_module._db is not None:
        with app_module._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM execution_orders ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
            for row in rows:
                orders.append(
                    {
                        "order_id": str(row["order_id"]),
                        "client_order_id": str(row["client_order_id"]),
                        "symbol": str(row["symbol"]),
                        "product": str(row["product"]),
                        "side": str(row["side"]),
                        "order_type": str(row["order_type"]),
                        "quantity": str(row["quantity_text"]),
                        "price": (
                            str(row["price_text"]) if row["price_text"] is not None else None
                        ),
                        "status": str(row["status"]),
                        "created_at": str(row["created_at"]),
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
    now = _now()
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
            fee = Decimal("0")
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


@router.get("/holdings")
def get_holdings() -> dict[str, Any]:
    from goldguard.web import app as app_module

    snap = DashboardReadModel(database=app_module._db).snapshot()
    return snap["holdings"]


@router.get("/pnl")
def get_pnl() -> dict[str, Any]:
    from goldguard.web import app as app_module

    snap = DashboardReadModel(database=app_module._db).snapshot()
    return snap["pnl"]


@router.get("/diagnostics")
async def get_diagnostics() -> dict[str, Any]:
    from goldguard.web import app as app_module

    settings = app_module._settings
    if settings is None:
        from goldguard.config import Settings

        settings = Settings()
    data = await collect_stack_diagnostics(
        settings=settings,
        database_ready=app_module._db is not None,
        paper_broker_ready=app_module._broker is not None,
        http_client=app_module._provider_http_client,
        dataset_status=getattr(app_module, "_dataset_status_label", lambda: "UNKNOWN")(),
        reflection_count=(
            len(app_module._reflection_repo.list_reflections(limit=200))
            if app_module._reflection_repo is not None
            else None
        ),
        hermes_proposal_ok=getattr(app_module, "_hermes_proposal_ok", None),
    )
    blockers = list(data.get("blockers") or [])
    return _envelope(
        data,
        source="runtime",
        detail=None if not blockers else "startup dependencies not ready",
    )


# /api/trades and /api/dashboard are owned by app.py — do not duplicate those paths.
