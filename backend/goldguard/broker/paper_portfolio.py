from __future__ import annotations

from typing import Any

from goldguard.broker.paper_futures import PaperFuturesBroker
from goldguard.broker.paper_spot import PaperSpotBroker
from goldguard.domain.enums import ExitReason, ProductKind
from goldguard.execution.models import (
    AccountSnapshot,
    ExecutionResult,
    OrderIntent,
    OrderRecord,
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

