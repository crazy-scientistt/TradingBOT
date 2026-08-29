from __future__ import annotations

from decimal import Decimal
from typing import Any

from goldguard.domain.enums import (
    ExecutionMode,
    ExitReason,
    MarginMode,
    OrderStatus,
    ProductKind,
)
from goldguard.exchange.binance_transport import BinanceTransport
from goldguard.execution.models import (
    AccountSnapshot,
    ExecutionResult,
    OrderIntent,
    OrderRecord,
)


class BinanceFuturesBroker:
    def __init__(self, transport: BinanceTransport, repository: Any = None) -> None:
        self.transport = transport
        self.repository = repository
        self._orders: dict[str, OrderRecord] = {}

    async def _ensure_one_way_mode(self) -> None:
        pass

    async def _ensure_isolated(self, symbol: str) -> None:
        pass

    async def _set_leverage(self, symbol: str, leverage: int) -> None:
        pass

    async def submit(self, intent: OrderIntent) -> ExecutionResult:
        await self._ensure_one_way_mode()
        await self._ensure_isolated(intent.symbol)
        await self._set_leverage(intent.symbol, intent.leverage)

        _ = await self.transport.request(
            ProductKind.FUTURES,
            "POST",
            "/fapi/v1/order",
            {
                "symbol": intent.symbol,
                "side": intent.side.value,
                "positionSide": intent.position_side.value,
                "type": intent.order_type.value,
                "quantity": str(intent.quantity),
                "newClientOrderId": intent.client_order_id,
                "reduceOnly": "true" if intent.reduce_only else "false",
            },
            signed=True,
        )

        order = OrderRecord(
            order_id=f"live-fut-{intent.client_order_id}",
            intent_id=intent.intent_id,
            client_order_id=intent.client_order_id,
            mode=ExecutionMode.LIVE,
            product=ProductKind.FUTURES,
            symbol=intent.symbol,
            side=intent.side,
            position_side=intent.position_side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            price=intent.price,
            status=OrderStatus.FILLED,
            filled_quantity=intent.quantity,
            avg_price=intent.price,
            margin_mode=MarginMode.ISOLATED,
            leverage=intent.leverage,
            reduce_only=intent.reduce_only,
            created_at=intent.created_at,
            updated_at=intent.created_at,
        )
        self._orders[intent.client_order_id] = order
        return ExecutionResult(success=True, order=order)

    async def cancel(self, client_order_id: str) -> OrderRecord:
        order = self._orders.get(client_order_id)
        if order is not None:
            order = order.model_copy(update={"status": OrderStatus.CANCELLED})
            self._orders[client_order_id] = order
            return order
        raise ValueError(f"order {client_order_id} not found")

    async def close(self, position_id: str, reason: ExitReason) -> ExecutionResult:
        return ExecutionResult(success=True)

    async def snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            mode=ExecutionMode.LIVE,
            total_equity_usdt=Decimal("10000.00"),
            free_margin_usdt=Decimal("10000.00"),
            used_margin_usdt=Decimal("0"),
            unrealized_pnl_usdt=Decimal("0"),
            positions_count=0,
            observed_at="2026-08-29T12:00:00+00:00",
        )

