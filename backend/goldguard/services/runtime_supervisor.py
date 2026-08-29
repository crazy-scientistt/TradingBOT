from __future__ import annotations

from goldguard.broker.paper_portfolio import PaperPortfolioBroker
from goldguard.domain.enums import ProductKind
from goldguard.domain.profile import AutonomousProfile
from goldguard.execution.models import MarketScope
from goldguard.risk.circuit_breaker import CircuitBreaker
from goldguard.services.emergency import EmergencyService
from goldguard.services.execution_coordinator import ExecutionCoordinator
from goldguard.services.market_supervisor import MarketSupervisor


class RuntimeSupervisor:
    def __init__(
        self,
        profile: AutonomousProfile,
        market: MarketSupervisor,
        broker: PaperPortfolioBroker,
        coordinator: ExecutionCoordinator,
        breaker: CircuitBreaker,
        emergency: EmergencyService,
    ) -> None:
        self._profile = profile
        self._market = market
        self._broker = broker
        self._coordinator = coordinator
        self._breaker = breaker
        self._emergency = emergency
        self._disabled_scopes: set[MarketScope] = set()
        self._running = False
        self._daily_trade_count = 0

    def market_scopes(self) -> tuple[MarketScope, ...]:
        scopes: list[MarketScope] = []
        mode = self._profile.execution_mode
        if self._profile.spot_enabled:
            for s in self._profile.spot_pairs:
                scopes.append(MarketScope(mode=mode, product=ProductKind.SPOT, symbol=s))
        if self._profile.futures_enabled:
            for f in self._profile.futures_pairs:
                scopes.append(MarketScope(mode=mode, product=ProductKind.FUTURES, symbol=f))
        return tuple(scopes)

    def apply_profile(self, profile: AutonomousProfile) -> None:
        self._profile = profile

    def disable_scope(self, scope: MarketScope) -> None:
        self._disabled_scopes.add(scope)

    def enable_scope(self, scope: MarketScope) -> None:
        self._disabled_scopes.discard(scope)

    def new_entries_allowed(self, scope: MarketScope) -> bool:
        if not self._running:
            return False
        if scope in self._disabled_scopes:
            return False
        if self._breaker._tripped:
            return False
        return self._daily_trade_count < 1000

    def protection_active(self, position_id: str) -> bool:
        return self._broker.protection_active(position_id)

    async def start(self) -> None:
        self._running = True
        await self._market.start(self.market_scopes())

    async def pause(self) -> None:
        self._coordinator.pause_entries()

    async def stop(self) -> None:
        self._running = False
        await self._market.stop()
