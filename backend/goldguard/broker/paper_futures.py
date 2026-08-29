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


class InsufficientMargin(Exception):
    pass


class FuturesOrderRejected(Exception):
    pass


class PaperFuturesBroker:
    def __init__(
        self,
        starting_collateral: Decimal,
        fee_rate: Decimal = Decimal("0.0005"),
        slippage_rate: Decimal = Decimal("0.0002"),
    ) -> None:
        if starting_collateral <= 0:
            raise ValueError("starting collateral must be positive")
        self._collateral = starting_collateral
        self._fee_rate = fee_rate
        self._slippage_rate = slippage_rate
        self._orders: dict[str, OrderRecord] = {}
        self._positions: dict[tuple[str, PositionSide], PositionRecord] = {}
        self._prices: dict[str, Decimal] = {}
        self._funding_paid: dict[tuple[str, PositionSide], Decimal] = {}

    @property
    def collateral(self) -> Decimal:
        return self._collateral

    def open_positions(self) -> tuple[PositionRecord, ...]:
        return tuple(
            position
            for position in self._positions.values()
            if position.status == PositionStatus.OPEN
        )

    def on_price(self, symbol: str, price: Decimal) -> None:
        self._prices[symbol] = price
        for (sym, side), pos in list(self._positions.items()):
            if sym == symbol and pos.status == PositionStatus.OPEN:
                if side == PositionSide.LONG:
                    unrealized = (price - pos.entry_price) * pos.quantity
                else:
                    unrealized = (pos.entry_price - price) * pos.quantity
                self._positions[(sym, side)] = pos.model_copy(
                    update={
                        "current_price": price,
                        "unrealized_pnl": unrealized,
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                )

    def apply_funding(self, symbol: str, rate: Decimal) -> None:
        for (sym, side), pos in list(self._positions.items()):
            if sym == symbol and pos.status == PositionStatus.OPEN:
                notional = (pos.current_price or pos.entry_price) * pos.quantity
                funding_amount = notional * rate
                if side == PositionSide.LONG:
                    self._collateral -= funding_amount
                    self._funding_paid[(sym, side)] = (
                        self._funding_paid.get((sym, side), Decimal("0")) + funding_amount
                    )
                elif side == PositionSide.SHORT:
                    self._collateral += funding_amount
                    self._funding_paid[(sym, side)] = (
                        self._funding_paid.get((sym, side), Decimal("0")) - funding_amount
                    )

    async def submit(self, intent: OrderIntent) -> ExecutionResult:
        if intent.product != ProductKind.FUTURES:
            raise FuturesOrderRejected(f"futures broker cannot process {intent.product} order")

        now = datetime.now(UTC).isoformat()
        symbol = intent.symbol
        side = intent.side
        pos_side = (
            intent.position_side
            if intent.position_side != PositionSide.BOTH
            else (PositionSide.LONG if side == OrderSide.BUY else PositionSide.SHORT)
        )
        key = (symbol, pos_side)

        price = intent.price or self._prices.get(symbol)
        if price is None:
            raise FuturesOrderRejected(f"market price is unavailable for {symbol}")
        if not intent.reduce_only:
            opposing = next(
                (
                    position
                    for (open_symbol, open_side), position in self._positions.items()
                    if open_symbol == symbol
                    and open_side != pos_side
                    and position.status == PositionStatus.OPEN
                ),
                None,
            )
            if opposing is not None:
                raise FuturesOrderRejected(
                    f"one-way mode already has an opposing {opposing.side.value} position"
                )
        slip = self._slippage_rate if side == OrderSide.BUY else -self._slippage_rate
        fill_price = price * (Decimal("1") + slip)
        notional = fill_price * intent.quantity
        fee = notional * self._fee_rate
        initial_margin = notional / Decimal(str(intent.leverage))

        if not intent.reduce_only:
            total_required = initial_margin + fee
            if total_required > self._collateral:
                raise InsufficientMargin(
                    f"insufficient collateral: required {total_required}, "
                    f"available {self._collateral}"
                )

            self._collateral -= total_required
            order = OrderRecord(
                order_id=f"ord-{uuid.uuid4().hex[:12]}",
                intent_id=intent.intent_id,
                client_order_id=intent.client_order_id,
                mode=ExecutionMode.PAPER,
                product=ProductKind.FUTURES,
                symbol=symbol,
                side=side,
                position_side=pos_side,
                order_type=intent.order_type,
                quantity=intent.quantity,
                price=intent.price,
                status=OrderStatus.FILLED,
                filled_quantity=intent.quantity,
                avg_price=fill_price,
                fee=fee,
                fee_asset="USDT",
                margin_mode=MarginMode.ISOLATED,
                leverage=intent.leverage,
                reduce_only=False,
                created_at=now,
                updated_at=now,
            )
            self._orders[intent.client_order_id] = order

            existing = self._positions.get(key)
            if existing is None or existing.status == PositionStatus.CLOSED:
                liq_diff = fill_price / Decimal(str(intent.leverage)) * Decimal("0.90")
                if pos_side == PositionSide.LONG:
                    liq_price = fill_price - liq_diff
                else:
                    liq_price = fill_price + liq_diff

                pos = PositionRecord(
                    position_id=f"pos-{uuid.uuid4().hex[:12]}",
                    mode=ExecutionMode.PAPER,
                    product=ProductKind.FUTURES,
                    symbol=symbol,
                    side=pos_side,
                    quantity=intent.quantity,
                    entry_price=fill_price,
                    current_price=fill_price,
                    liquidation_price=liq_price,
                    margin_mode=MarginMode.ISOLATED,
                    leverage=intent.leverage,
                    isolated_margin=initial_margin,
                    unrealized_pnl=Decimal("0"),
                    realized_pnl=-fee,
                    opened_at=now,
                    updated_at=now,
                    status=PositionStatus.OPEN,
                )
            else:
                new_qty = existing.quantity + intent.quantity
                new_entry = (
                    existing.entry_price * existing.quantity + fill_price * intent.quantity
                ) / new_qty
                new_margin = existing.isolated_margin + initial_margin
                pos = existing.model_copy(
                    update={
                        "quantity": new_qty,
                        "entry_price": new_entry,
                        "current_price": fill_price,
                        "isolated_margin": new_margin,
                        "realized_pnl": existing.realized_pnl - fee,
                        "updated_at": now,
                    }
                )

            self._positions[key] = pos
            return ExecutionResult(success=True, order=order, position=pos)

        else:
            existing = self._positions.get(key)
            if existing is None or existing.status == PositionStatus.CLOSED:
                raise FuturesOrderRejected(f"no open position to reduce for {key}")

            close_qty = min(intent.quantity, existing.quantity)
            if pos_side == PositionSide.LONG:
                gross_pnl = (fill_price - existing.entry_price) * close_qty
            else:
                gross_pnl = (existing.entry_price - fill_price) * close_qty

            released_margin = existing.isolated_margin * (close_qty / existing.quantity)
            net_return = released_margin + gross_pnl - fee
            self._collateral += net_return

            order = OrderRecord(
                order_id=f"ord-{uuid.uuid4().hex[:12]}",
                intent_id=intent.intent_id,
                client_order_id=intent.client_order_id,
                mode=ExecutionMode.PAPER,
                product=ProductKind.FUTURES,
                symbol=symbol,
                side=side,
                position_side=pos_side,
                order_type=intent.order_type,
                quantity=close_qty,
                price=intent.price,
                status=OrderStatus.FILLED,
                filled_quantity=close_qty,
                avg_price=fill_price,
                fee=fee,
                fee_asset="USDT",
                margin_mode=MarginMode.ISOLATED,
                leverage=existing.leverage,
                reduce_only=True,
                created_at=now,
                updated_at=now,
            )
            self._orders[intent.client_order_id] = order

            remaining_qty = existing.quantity - close_qty
            if remaining_qty <= Decimal("0"):
                closed_pos = existing.model_copy(
                    update={
                        "quantity": Decimal("0"),
                        "isolated_margin": Decimal("0"),
                        "unrealized_pnl": Decimal("0"),
                        "realized_pnl": existing.realized_pnl + gross_pnl - fee,
                        "status": PositionStatus.CLOSED,
                        "updated_at": now,
                    }
                )
                del self._positions[key]
                return ExecutionResult(success=True, order=order, position=closed_pos)
            else:
                updated_pos = existing.model_copy(
                    update={
                        "quantity": remaining_qty,
                        "isolated_margin": existing.isolated_margin - released_margin,
                        "realized_pnl": existing.realized_pnl + gross_pnl - fee,
                        "updated_at": now,
                    }
                )
                self._positions[key] = updated_pos
                return ExecutionResult(success=True, order=order, position=updated_pos)

    async def cancel(self, client_order_id: str) -> OrderRecord:
        order = self._orders.get(client_order_id)
        if order is None:
            raise FuturesOrderRejected(f"order {client_order_id} not found")
        return order

    async def close(self, position_id: str, reason: ExitReason) -> ExecutionResult:
        matching_key = None
        for key, pos in self._positions.items():
            if pos.position_id == position_id:
                matching_key = key
                break
        if matching_key is None:
            raise FuturesOrderRejected(f"position {position_id} not found")

        sym, pos_side = matching_key
        pos = self._positions[matching_key]
        close_side = OrderSide.SELL if pos_side == PositionSide.LONG else OrderSide.BUY
        intent = OrderIntent(
            intent_id=f"close-{uuid.uuid4().hex[:12]}",
            client_order_id=f"close-order-{uuid.uuid4().hex[:12]}",
            mode=ExecutionMode.PAPER,
            product=ProductKind.FUTURES,
            symbol=sym,
            side=close_side,
            position_side=pos_side,
            order_type=OrderType.MARKET,
            quantity=pos.quantity,
            margin_mode=MarginMode.ISOLATED,
            leverage=pos.leverage,
            reduce_only=True,
        )
        return await self.submit(intent)

    async def snapshot(self) -> AccountSnapshot:
        total_unrealized = Decimal("0")
        total_used_margin = Decimal("0")
        for pos in self._positions.values():
            if pos.status == PositionStatus.OPEN:
                total_unrealized += pos.unrealized_pnl
                total_used_margin += pos.isolated_margin

        total_equity = self._collateral + total_used_margin + total_unrealized
        open_count = len([p for p in self._positions.values() if p.status == PositionStatus.OPEN])
        return AccountSnapshot(
            mode=ExecutionMode.PAPER,
            total_equity_usdt=total_equity,
            free_margin_usdt=self._collateral,
            used_margin_usdt=total_used_margin,
            unrealized_pnl_usdt=total_unrealized,
            positions_count=open_count,
            observed_at=datetime.now(UTC).isoformat(),
        )
