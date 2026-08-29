from __future__ import annotations

from decimal import Decimal
from typing import Any

from goldguard.broker.paper_futures import PaperFuturesBroker
from goldguard.broker.paper_spot import PaperSpotBroker
from goldguard.domain.enums import ExitReason, PositionSide, ProductKind
from goldguard.execution.models import (
    AccountSnapshot,
    ExecutionResult,
    OrderIntent,
    OrderRecord,
    PositionRecord,
    ProtectionPlan,
)


class PaperPortfolioBroker:
    def __init__(
        self,
        spot: PaperSpotBroker,
        futures: PaperFuturesBroker,
        ledger: Any = None,
    ) -> None:
        self._spot = spot
        self._futures = futures
        self._ledger = ledger
        self._protections: dict[str, ProtectionPlan] = {}

    @property
    def spot(self) -> PaperSpotBroker:
        return self._spot

    @property
    def futures(self) -> PaperFuturesBroker:
        return self._futures

    async def submit(self, intent: OrderIntent) -> ExecutionResult:
        broker = self._spot if intent.product == ProductKind.SPOT else self._futures
        result = await broker.submit(intent)
        return result

    async def cancel(
        self, client_order_id: str, product: ProductKind = ProductKind.SPOT
    ) -> OrderRecord:
        broker = self._spot if product == ProductKind.SPOT else self._futures
        return await broker.cancel(client_order_id)

    async def close(
        self,
        position_id: str,
        reason: ExitReason,
        product: ProductKind = ProductKind.SPOT,
    ) -> ExecutionResult:
        broker = self._spot if product == ProductKind.SPOT else self._futures
        return await broker.close(position_id, reason)

    async def snapshot(self) -> AccountSnapshot:
        spot_snap = await self._spot.snapshot()
        futures_snap = await self._futures.snapshot()
        total_equity = spot_snap.total_equity_usdt + futures_snap.total_equity_usdt
        free_margin = spot_snap.free_margin_usdt + futures_snap.free_margin_usdt
        used_margin = spot_snap.used_margin_usdt + futures_snap.used_margin_usdt
        unrealized = spot_snap.unrealized_pnl_usdt + futures_snap.unrealized_pnl_usdt
        pos_count = spot_snap.positions_count + futures_snap.positions_count

        return AccountSnapshot(
            mode=spot_snap.mode,
            total_equity_usdt=total_equity,
            free_margin_usdt=free_margin,
            used_margin_usdt=used_margin,
            unrealized_pnl_usdt=unrealized,
            positions_count=pos_count,
            observed_at=spot_snap.observed_at,
        )

    def install_protection(self, plan: ProtectionPlan) -> None:
        positions = (*self._spot.open_positions(), *self._futures.open_positions())
        position = next((item for item in positions if item.position_id == plan.position_id), None)
        if position is None:
            raise ValueError(f"cannot protect unknown position {plan.position_id}")
        if plan.stop_loss_price is None or plan.take_profit_price is None:
            raise ValueError("stop loss and take profit are required")
        reference_price = position.current_price or position.entry_price
        if position.side == PositionSide.LONG and not (
            plan.stop_loss_price < reference_price < plan.take_profit_price
        ):
            raise ValueError("long protection must bracket the current price")
        if position.side == PositionSide.SHORT and not (
            plan.take_profit_price < reference_price < plan.stop_loss_price
        ):
            raise ValueError("short protection must bracket the current price")
        self._protections[plan.position_id] = plan

    def protection_active(self, position_id: str) -> bool:
        return position_id in self._protections

    def open_positions(self) -> tuple[PositionRecord, ...]:
        return (*self._spot.open_positions(), *self._futures.open_positions())

    async def process_price(
        self,
        product: ProductKind,
        symbol: str,
        price: Decimal,
    ) -> tuple[ExecutionResult, ...]:
        broker = self._spot if product == ProductKind.SPOT else self._futures
        broker.on_price(symbol, price)
        results: list[ExecutionResult] = []
        for position in broker.open_positions():
            if position.symbol != symbol:
                continue
            protection = self._protections.get(position.position_id)
            if protection is None:
                continue
            stop_hit = (
                position.side == PositionSide.LONG
                and protection.stop_loss_price is not None
                and price <= protection.stop_loss_price
            ) or (
                position.side == PositionSide.SHORT
                and protection.stop_loss_price is not None
                and price >= protection.stop_loss_price
            )
            target_hit = (
                position.side == PositionSide.LONG
                and protection.take_profit_price is not None
                and price >= protection.take_profit_price
            ) or (
                position.side == PositionSide.SHORT
                and protection.take_profit_price is not None
                and price <= protection.take_profit_price
            )
            if not stop_hit and not target_hit:
                continue
            reason = ExitReason.STOP_LOSS if stop_hit else ExitReason.TAKE_PROFIT
            result = await broker.close(position.position_id, reason)
            self._protections.pop(position.position_id, None)
            results.append(result)
        return tuple(results)
