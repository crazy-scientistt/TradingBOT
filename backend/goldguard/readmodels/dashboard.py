from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DashboardPositionView:
    position_id: str
    symbol: str
    product: str
    side: str
    quantity: str
    entry_price: str
    current_price: str
    gross_pnl_usdt: str
    fees_usdt: str
    funding_usdt: str
    slippage_usdt: str
    net_pnl_usdt: str
    leverage: int


@dataclass(frozen=True, slots=True)
class DashboardOrderView:
    order_id: str
    client_order_id: str
    symbol: str
    product: str
    side: str
    order_type: str
    quantity: str
    price: str | None
    status: str
    created_at: str


def _envelope(
    data: Any,
    *,
    source: str,
    observed_at: str,
    detail: str | None,
    stale: bool = False,
    availability: str = "available",
) -> dict[str, Any]:
    return {
        "availability": availability,
        "source": source,
        "observed_at": observed_at,
        "stale": stale,
        "detail": detail,
        "data": data,
    }


class DashboardReadModel:
    """Read-only dashboard projection. Never fabricates trades or fills."""

    def __init__(self, database: Any = None) -> None:
        self._database = database

    def snapshot(self, now: datetime | None = None) -> dict[str, Any]:
        observed_at = (now or datetime.now(UTC)).isoformat()
        orders: list[dict[str, Any]] = []
        positions: list[dict[str, Any]] = []
        holdings: list[dict[str, Any]] = []
        pnl: list[dict[str, Any]] = []
        equity = "0"

        if self._database is not None:
            with self._database.connect() as conn:
                order_rows = conn.execute(
                    "SELECT * FROM execution_orders ORDER BY created_at DESC LIMIT 100"
                ).fetchall()
                for row in order_rows:
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
                                str(row["price_text"])
                                if row["price_text"] is not None
                                else None
                            ),
                            "status": str(row["status"]),
                            "created_at": str(row["created_at"]),
                        }
                    )

        return {
            "equity": equity,
            "mode": "PAPER",
            "orders": _envelope(
                orders,
                source="execution_ledger",
                observed_at=observed_at,
                detail=None if orders else "no orders placed yet",
            ),
            "positions": _envelope(
                positions,
                source="execution_positions",
                observed_at=observed_at,
                detail=None if positions else "no open positions",
            ),
            "holdings": _envelope(
                holdings,
                source="execution_holdings",
                observed_at=observed_at,
                detail=None if holdings else "no holdings",
            ),
            "pnl": _envelope(
                pnl,
                source="execution_pnl",
                observed_at=observed_at,
                detail=None if pnl else "no realized pnl yet",
            ),
            "diagnostics": _envelope(
                {"blockers": [], "checks": []},
                source="runtime",
                observed_at=observed_at,
                detail=None,
            ),
        }
