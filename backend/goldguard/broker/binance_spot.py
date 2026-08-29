from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from goldguard.broker.binance_common import (
    SPOT_MIN_NOTIONAL,
    SPOT_QTY_STEP,
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


class BinanceSpotBroker:
    def __init__(self, transport: BinanceTransport, repository: Any = None) -> None:
        self.transport = transport
        self.repository = repository
        self._orders: dict[str, OrderRecord] = {}

    async def submit(self, intent: OrderIntent) -> ExecutionResult:
        quantity = quantize_qty(intent.quantity, SPOT_QTY_STEP)
        if quantity <= 0:
            return ExecutionResult(
                success=False,
                error_code="QTY_BELOW_STEP",
                error_message="quantity is below the PAXG lot step",
            )
        if intent.price is not None and quantity * intent.price < SPOT_MIN_NOTIONAL:
            return ExecutionResult(
                success=False,
                error_code="MIN_NOTIONAL",
                error_message="notional is below the exchange minimum",
            )

        params: dict[str, Any] = {
            "symbol": intent.symbol,
            "side": intent.side.value,
            "type": intent.order_type.value,
            "quantity": format(quantity, "f"),
            "newClientOrderId": intent.client_order_id,
        }
        if intent.price is not None and intent.order_type.value != "MARKET":
            params["price"] = format(intent.price, "f")
            params["timeInForce"] = intent.time_in_force.value

        try:
            payload = await self.transport.request(
                ProductKind.SPOT, "POST", "/api/v3/order", params, signed=True
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
            intent, payload, quantity, product=ProductKind.SPOT
        )
        if result.order is not None:
            self._orders[intent.client_order_id] = result.order
        return result

    async def _query_by_client_id(self, client_order_id: str) -> Any | None:
        try:
            return await self.transport.request(
                ProductKind.SPOT,
                "GET",
                "/api/v3/order",
                {"origClientOrderId": client_order_id},
                signed=True,
            )
        except BinanceTransportError:
            return None

    async def cancel(self, client_order_id: str) -> OrderRecord:
        payload = await self.transport.request(
            ProductKind.SPOT,
            "DELETE",
            "/api/v3/order",
            {"origClientOrderId": client_order_id},
            signed=True,
        )
        local = self._orders.get(client_order_id)
        if not isinstance(payload, dict) and local is None:
            raise ValueError(f"order {client_order_id} not found")
        if isinstance(payload, dict):
            intent_stub = local
            if intent_stub is None:
                raise ValueError(f"order {client_order_id} not found")
            result = result_from_binance_payload(
                OrderIntent(
                    intent_id=intent_stub.intent_id,
                    client_order_id=client_order_id,
                    mode=intent_stub.mode,
                    product=intent_stub.product,
                    symbol=intent_stub.symbol,
                    side=intent_stub.side,
                    position_side=intent_stub.position_side,
                    order_type=intent_stub.order_type,
                    quantity=intent_stub.quantity,
                    price=intent_stub.price,
                    leverage=intent_stub.leverage,
                    reduce_only=intent_stub.reduce_only,
                    created_at=intent_stub.created_at,
                ),
                payload,
                intent_stub.quantity,
                product=ProductKind.SPOT,
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
                ProductKind.SPOT, "GET", "/api/v3/account", {}, signed=True
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
        free = Decimal("0")
        locked = Decimal("0")
        if isinstance(account, dict):
            for row in account.get("balances", []):
                if row.get("asset") == "USDT":
                    free = Decimal(str(row.get("free", "0")))
                    locked = Decimal(str(row.get("locked", "0")))
                    break
        return AccountSnapshot(
            mode=ExecutionMode.LIVE,
            total_equity_usdt=free + locked,
            free_margin_usdt=free,
            used_margin_usdt=locked,
            unrealized_pnl_usdt=Decimal("0"),
            positions_count=0,
            observed_at=now,
        )
