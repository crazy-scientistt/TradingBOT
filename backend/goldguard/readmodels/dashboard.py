from __future__ import annotations

from dataclasses import dataclass


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

