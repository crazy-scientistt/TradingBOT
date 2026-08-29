from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from goldguard.broker.binance_common import (
    FUTURES_QTY_STEP,
    quantize_qty,
    result_from_binance_payload,
)
from goldguard.domain.enums import ExecutionMode, ExitReason, ProductKind
from goldguard.exchange.binance_transport import (
    BinanceTimeoutError,
    BinanceTransport,
    BinanceTransportError,
)
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
        await self.transport.request(
            ProductKind.FUTURES,
            "POST",
            "/fapi/v1/positionSide/dual",
            {"dualSidePosition": "false"},
            signed=True,
        )

    async def _ensure_isolated(self, symbol: str) -> None:
        await self.transport.request(
            ProductKind.FUTURES,
            "POST",
            "/fapi/v1/marginType",
            {"symbol": symbol, "marginType": "ISOLATED"},
            signed=True,
        )

    async def _set_leverage(self, symbol: str, leverage: int) -> None:
        await self.transport.request(
            ProductKind.FUTURES,
            "POST",
            "/fapi/v1/leverage",
            {"symbol": symbol, "leverage": str(leverage)},
            signed=True,
        )

    async def submit(self, intent: OrderIntent) -> ExecutionResult:
        quantity = quantize_qty(intent.quantity, FUTURES_QTY_STEP)
        if quantity <= 0:
            return ExecutionResult(
                success=False,
                error_code="QTY_BELOW_STEP",
                error_message="quantity is below the futures lot step",
            )

        try:
            await self._ensure_one_way_mode()
            await self._ensure_isolated(intent.symbol)
            await self._set_leverage(intent.symbol, intent.leverage)
        except BinanceTransportError as exc:
            return ExecutionResult(
                success=False,
                error_code="FUTURES_PREP_FAILED",
                error_message=str(exc),
            )

        params: dict[str, Any] = {
            "symbol": intent.symbol,
            "side": intent.side.value,
            "positionSide": intent.position_side.value,
            "type": intent.order_type.value,
            "quantity": format(quantity, "f"),
            "newClientOrderId": intent.client_order_id,
            "reduceOnly": "true" if intent.reduce_only else "false",
        }

        try:
            payload = await self.transport.request(
                ProductKind.FUTURES, "POST", "/fapi/v1/order", params, signed=True
            )
        except BinanceTimeoutError:
            payload = await self._query_by_client_id(intent.client_order_id)
            if payload is None:
                return ExecutionResult(
                    success=False,
                    error_code="TIMEOUT_UNCONFIRMED",
                    error_message="timeout after submit; order not confirmed",
                )
        except BinanceTransportError as exc:
            return ExecutionResult(
                success=False,
                error_code="TRANSPORT_ERROR",
                error_message=str(exc),
            )

        result = result_from_binance_payload(
            intent, payload, quantity, product=ProductKind.FUTURES
        )
        if result.order is not None:
            self._orders[intent.client_order_id] = result.order
        return result

    async def _query_by_client_id(self, client_order_id: str) -> Any | None:
        try:
            return await self.transport.request(
                ProductKind.FUTURES,
                "GET",
                "/fapi/v1/order",
                {"origClientOrderId": client_order_id},
                signed=True,
            )
        except BinanceTransportError:
            return None

    async def cancel(self, client_order_id: str) -> OrderRecord:
        order = self._orders.get(client_order_id)
        payload = await self.transport.request(
            ProductKind.FUTURES,
            "DELETE",
            "/fapi/v1/order",
            {"origClientOrderId": client_order_id},
            signed=True,
        )
        if order is None:
            raise ValueError(f"order {client_order_id} not found")
        if isinstance(payload, dict):
            result = result_from_binance_payload(
                OrderIntent(
                    intent_id=order.intent_id,
                    client_order_id=client_order_id,
                    mode=order.mode,
                    product=order.product,
                    symbol=order.symbol,
                    side=order.side,
                    position_side=order.position_side,
                    order_type=order.order_type,
                    quantity=order.quantity,
                    price=order.price,
                    margin_mode=order.margin_mode,
                    leverage=order.leverage,
                    reduce_only=order.reduce_only,
                    created_at=order.created_at,
                ),
                payload,
                order.quantity,
                product=ProductKind.FUTURES,
            )
            if result.order is not None:
                self._orders[client_order_id] = result.order
                return result.order
        raise ValueError(f"order {client_order_id} not found")

    async def close(self, position_id: str, reason: ExitReason) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            error_code="POSITION_NOT_OWNED",
            error_message="live close requires an owned reconciled position",
        )

    async def snapshot(self) -> AccountSnapshot:
        now = datetime.now(UTC).isoformat()
        try:
            account = await self.transport.request(
                ProductKind.FUTURES, "GET", "/fapi/v2/account", {}, signed=True
            )
        except BinanceTransportError:
            return AccountSnapshot(
                mode=ExecutionMode.LIVE,
                total_equity_usdt=Decimal("0"),
                free_margin_usdt=Decimal("0"),
                used_margin_usdt=Decimal("0"),
                unrealized_pnl_usdt=Decimal("0"),
                positions_count=0,
                observed_at=now,
            )
        equity = Decimal("0")
        available = Decimal("0")
        if isinstance(account, dict):
            if account.get("totalWalletBalance") is not None:
                equity = Decimal(str(account["totalWalletBalance"]))
            if account.get("availableBalance") is not None:
                available = Decimal(str(account["availableBalance"]))
        return AccountSnapshot(
            mode=ExecutionMode.LIVE,
            total_equity_usdt=equity,
            free_margin_usdt=available,
            used_margin_usdt=max(Decimal("0"), equity - available),
            unrealized_pnl_usdt=Decimal(str(account.get("totalUnrealizedProfit", "0")))
            if isinstance(account, dict)
            else Decimal("0"),
            positions_count=0,
            observed_at=now,
        )
