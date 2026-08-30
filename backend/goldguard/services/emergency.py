from __future__ import annotations

from typing import Any

from goldguard.broker.paper_portfolio import PaperPortfolioBroker
from goldguard.domain.enums import ExitReason, OrderStatus, ProductKind
from goldguard.execution.models import MarketScope


class EmergencyService:
    def __init__(
        self,
        broker: PaperPortfolioBroker,
        coordinator: Any = None,
    ) -> None:
        self.broker = broker
        self.coordinator = coordinator

    def pause(self) -> None:
        if self.coordinator is not None:
            self.coordinator.pause_entries()

    async def cancel_entries(self, scopes: tuple[MarketScope, ...] | list[MarketScope]) -> int:
        self.pause()
        wanted = {(scope.product, scope.symbol) for scope in scopes}
        cancelled = 0
        for order in list(self.broker.spot._orders.values()):
            if (ProductKind.SPOT, order.symbol) not in wanted:
                continue
            if order.status != OrderStatus.OPEN:
                continue
            await self.broker.spot.cancel(order.client_order_id)
            cancelled += 1
        for order in list(self.broker.futures._orders.values()):
            if (ProductKind.FUTURES, order.symbol) not in wanted:
                continue
            if order.status != OrderStatus.OPEN:
                continue
            await self.broker.futures.cancel(order.client_order_id)
            cancelled += 1
        return cancelled

    async def close_owned_positions(
        self,
        scopes: tuple[MarketScope, ...] | list[MarketScope],
        reason: ExitReason = ExitReason.EMERGENCY,
    ) -> int:
        closed_count = 0
        for scope in scopes:
            if scope.product == ProductKind.SPOT:
                for sym, pos in list(self.broker.spot._positions.items()):
                    if sym == scope.symbol:
                        await self.broker.spot.close(pos.position_id, reason)
                        closed_count += 1
            elif scope.product == ProductKind.FUTURES:
                for (sym, _), pos in list(self.broker.futures._positions.items()):
                    if sym == scope.symbol:
                        await self.broker.futures.close(pos.position_id, reason)
                        closed_count += 1
        return closed_count

