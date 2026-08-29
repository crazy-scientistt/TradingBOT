from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AvailabilityEnvelope[T](BaseModel):
    model_config = ConfigDict(extra="forbid")
    availability: str  # "available", "degraded", "unavailable"
    source: str
    observed_at: str
    stale: bool
    detail: str | None = None
    data: T | None = None


class OrderItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    client_order_id: str
    symbol: str
    product: str
    side: str
    order_type: str
    quantity: str
    price: str | None = None
    status: str
    created_at: str


class PositionItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
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

