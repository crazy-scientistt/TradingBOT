from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from goldguard.domain.enums import (
    ExecutionMode,
    ExitReason,
    MarginMode,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    PositionStatus,
    ProductKind,
)
from goldguard.execution.models import (
    AccountSnapshot,
    ExecutionResult,
    OrderIntent,
    OrderRecord,
    PositionRecord,
)


class InsufficientBalance(Exception):
    pass


class SpotOrderRejected(Exception):
    pass


class PaperSpotBroker:
    def __init__(
        self,
        starting_cash: Decimal,
        fee_rate: Decimal = Decimal("0.001"),
        slippage_rate: Decimal = Decimal("0.0002"),
    ) -> None:
        if starting_cash <= 0:
            raise ValueError("starting cash must be positive")
        self._cash = starting_cash
        self._fee_rate = fee_rate
        self._slippage_rate = slippage_rate
        self._orders: dict[str, OrderRecord] = {}
        self._positions: dict[str, PositionRecord] = {}  # keyed by symbol
        self._prices: dict[str, Decimal] = {}

    @property
    def cash(self) -> Decimal:
        return self._cash

    def on_price(self, symbol: str, price: Decimal) -> None:
        self._prices[symbol] = price
        if symbol in self._positions:
            pos = self._positions[symbol]
            unrealized = (price - pos.entry_price) * pos.quantity
            self._positions[symbol] = pos.model_copy(
                update={
                    "current_price": price,
                    "unrealized_pnl": unrealized,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )

    async def submit(self, intent: OrderIntent) -> ExecutionResult:
        if intent.product != ProductKind.SPOT:
            raise SpotOrderRejected(f"spot broker cannot process {intent.product} order")

        now = datetime.now(UTC).isoformat()
        symbol = intent.symbol
        price = intent.price or self._prices.get(symbol) or Decimal("1000.00")

        if intent.side == OrderSide.BUY:
            fill_price = price * (Decimal("1") + self._slippage_rate)
            notional = fill_price * intent.quantity
            fee = notional * self._fee_rate
            total_required = notional + fee

            if total_required > self._cash:
                raise InsufficientBalance(
                    f"insufficient cash: required {total_required}, available {self._cash}"
                )

            self._cash -= total_required
            order = OrderRecord(
                order_id=f"ord-{uuid.uuid4().hex[:12]}",
                intent_id=intent.intent_id,
                client_order_id=intent.client_order_id,
                mode=ExecutionMode.PAPER,
                product=ProductKind.SPOT,
                symbol=symbol,
                side=OrderSide.BUY,
                position_side=PositionSide.LONG,
                order_type=intent.order_type,
                quantity=intent.quantity,
                price=intent.price,
                status=OrderStatus.FILLED,
                filled_quantity=intent.quantity,
                avg_price=fill_price,
                fee=fee,
                fee_asset="USDT",
                margin_mode=MarginMode.ISOLATED,
                leverage=1,
                reduce_only=False,
                created_at=now,
                updated_at=now,
            )
            self._orders[intent.client_order_id] = order

            existing = self._positions.get(symbol)
            if existing is None:
                pos = PositionRecord(
                    position_id=f"pos-{uuid.uuid4().hex[:12]}",
                    mode=ExecutionMode.PAPER,
                    product=ProductKind.SPOT,
                    symbol=symbol,
                    side=PositionSide.LONG,
                    quantity=intent.quantity,
                    entry_price=fill_price,
                    current_price=fill_price,
                    margin_mode=MarginMode.ISOLATED,
                    leverage=1,
                    isolated_margin=notional,
                    unrealized_pnl=Decimal("0"),
                    realized_pnl=Decimal("0"),
                    opened_at=now,
                    updated_at=now,
                    status=PositionStatus.OPEN,
                )
            else:
                new_qty = existing.quantity + intent.quantity
                new_entry = (
                    existing.entry_price * existing.quantity + fill_price * intent.quantity
                ) / new_qty
                pos = existing.model_copy(
                    update={
                        "quantity": new_qty,
                        "entry_price": new_entry,
                        "current_price": fill_price,
                        "isolated_margin": new_entry * new_qty,
                        "updated_at": now,
                    }
                )
            self._positions[symbol] = pos
            return ExecutionResult(success=True, order=order, position=pos)

        elif intent.side == OrderSide.SELL:
            existing = self._positions.get(symbol)
            if existing is None or existing.quantity < intent.quantity:
                held = existing.quantity if existing else Decimal("0")
                raise InsufficientBalance(
                    f"insufficient asset to sell: holding {held}, requested {intent.quantity}"
                )

            fill_price = price * (Decimal("1") - self._slippage_rate)
            gross = fill_price * intent.quantity
            fee = gross * self._fee_rate
            net = gross - fee
            cost_basis = existing.entry_price * intent.quantity
            realized = net - cost_basis

            self._cash += net
            order = OrderRecord(
                order_id=f"ord-{uuid.uuid4().hex[:12]}",
                intent_id=intent.intent_id,
                client_order_id=intent.client_order_id,
                mode=ExecutionMode.PAPER,
                product=ProductKind.SPOT,
                symbol=symbol,
                side=OrderSide.SELL,
                position_side=PositionSide.LONG,
                order_type=intent.order_type,
                quantity=intent.quantity,
                price=intent.price,
                status=OrderStatus.FILLED,
                filled_quantity=intent.quantity,
                avg_price=fill_price,
                fee=fee,
                fee_asset="USDT",
                margin_mode=MarginMode.ISOLATED,
                leverage=1,
                reduce_only=True,
                created_at=now,
                updated_at=now,
            )
            self._orders[intent.client_order_id] = order

            new_qty = existing.quantity - intent.quantity
            if new_qty <= Decimal("0"):
                del self._positions[symbol]
                closed_pos = existing.model_copy(
                    update={
                        "quantity": Decimal("0"),
                        "realized_pnl": existing.realized_pnl + realized,
                        "status": PositionStatus.CLOSED,
                        "updated_at": now,
                    }
                )
                return ExecutionResult(success=True, order=order, position=closed_pos)
            else:
                updated_pos = existing.model_copy(
                    update={
                        "quantity": new_qty,
                        "realized_pnl": existing.realized_pnl + realized,
                        "isolated_margin": existing.entry_price * new_qty,
                        "updated_at": now,
                    }
                )
                self._positions[symbol] = updated_pos
                return ExecutionResult(success=True, order=order, position=updated_pos)

        raise SpotOrderRejected(f"unsupported side {intent.side}")

    async def cancel(self, client_order_id: str) -> OrderRecord:
        order = self._orders.get(client_order_id)
        if order is None:
            raise SpotOrderRejected(f"order {client_order_id} not found")
        if order.status == OrderStatus.OPEN:
            order = order.model_copy(
                update={
                    "status": OrderStatus.CANCELLED,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
            self._orders[client_order_id] = order
        return order

    async def close(self, position_id: str, reason: ExitReason) -> ExecutionResult:
        matching_symbol = None
        for sym, pos in self._positions.items():
            if pos.position_id == position_id:
                matching_symbol = sym
                break
        if matching_symbol is None:
            raise SpotOrderRejected(f"position {position_id} not found")

        pos = self._positions[matching_symbol]
        intent = OrderIntent(
            intent_id=f"close-{uuid.uuid4().hex[:12]}",
            client_order_id=f"close-order-{uuid.uuid4().hex[:12]}",
            mode=ExecutionMode.PAPER,
            product=ProductKind.SPOT,
            symbol=matching_symbol,
            side=OrderSide.SELL,
            position_side=PositionSide.LONG,
            order_type=OrderType.MARKET,
            quantity=pos.quantity,
            margin_mode=MarginMode.ISOLATED,
            leverage=1,
            reduce_only=True,
        )
        return await self.submit(intent)

    async def snapshot(self) -> AccountSnapshot:
        total_unrealized = Decimal("0")
        total_used_margin = Decimal("0")
        for pos in self._positions.values():
            total_unrealized += pos.unrealized_pnl
            total_used_margin += pos.isolated_margin

        total_equity = self._cash + total_used_margin + total_unrealized
        return AccountSnapshot(
            mode=ExecutionMode.PAPER,
            total_equity_usdt=total_equity,
            free_margin_usdt=self._cash,
            used_margin_usdt=total_used_margin,
            unrealized_pnl_usdt=total_unrealized,
            positions_count=len(self._positions),
            observed_at=datetime.now(UTC).isoformat(),
        )

