from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from goldguard.domain.enums import (
    ExecutionMode,
    MarginMode,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    PositionStatus,
    ProductKind,
    TimeInForce,
)


class MarketScope(BaseModel):
    model_config = ConfigDict(frozen=True)
    mode: ExecutionMode
    product: ProductKind
    symbol: str


class OrderIntent(BaseModel):
    model_config = ConfigDict(frozen=True)
    intent_id: str
    client_order_id: str
    mode: ExecutionMode
    product: ProductKind
    symbol: str
    side: OrderSide
    position_side: PositionSide = PositionSide.BOTH
    order_type: OrderType = OrderType.MARKET
    quantity: Decimal = Field(gt=Decimal("0"))
    price: Decimal | None = None
    stop_price: Decimal | None = None
    margin_mode: MarginMode = MarginMode.ISOLATED
    leverage: int = Field(default=1, ge=1, le=125)
    reduce_only: bool = False
    time_in_force: TimeInForce = TimeInForce.GTC
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    correlation_id: str = ""

    @model_validator(mode="after")
    def validate_product_rules(self) -> Self:
        if self.product == ProductKind.FUTURES:
            if self.margin_mode != MarginMode.ISOLATED:
                raise ValueError("futures orders require isolated margin mode in this release")
            if self.leverage < 1:
                raise ValueError("futures orders require leverage >= 1")
        elif self.product == ProductKind.SPOT:
            if self.leverage != 1:
                raise ValueError("spot orders cannot use leverage")
            if self.side == OrderSide.SELL and self.position_side == PositionSide.SHORT:
                raise ValueError("spot does not support short positions")
        return self


class OrderRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id: str
    intent_id: str
    client_order_id: str
    mode: ExecutionMode
    product: ProductKind
    symbol: str
    side: OrderSide
    position_side: PositionSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None = None
    stop_price: Decimal | None = None
    status: OrderStatus
    filled_quantity: Decimal = Decimal("0")
    avg_price: Decimal | None = None
    fee: Decimal = Decimal("0")
    fee_asset: str = "USDT"
    margin_mode: MarginMode = MarginMode.ISOLATED
    leverage: int = 1
    reduce_only: bool = False
    created_at: str
    updated_at: str


class FillRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    fill_id: str
    order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    position_side: PositionSide
    price: Decimal
    quantity: Decimal
    fee: Decimal
    fee_asset: str = "USDT"
    realized_pnl: Decimal = Decimal("0")
    occurred_at: str


class PositionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    position_id: str
    mode: ExecutionMode
    product: ProductKind
    symbol: str
    side: PositionSide
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal | None = None
    liquidation_price: Decimal | None = None
    margin_mode: MarginMode = MarginMode.ISOLATED
    leverage: int = 1
    isolated_margin: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    opened_at: str
    updated_at: str
    status: PositionStatus = PositionStatus.OPEN


class ProtectionPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    position_id: str
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    trailing_stop_delta: Decimal | None = None
    max_drawdown_limit: Decimal | None = None


class AccountSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    mode: ExecutionMode
    total_equity_usdt: Decimal
    free_margin_usdt: Decimal
    used_margin_usdt: Decimal
    unrealized_pnl_usdt: Decimal
    positions_count: int
    observed_at: str


class ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    success: bool
    order: OrderRecord | None = None
    position: PositionRecord | None = None
    error_code: str | None = None
    error_message: str | None = None

