from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import timedelta
from decimal import Decimal

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
        self._stale_block = False
        self._tasks: list[asyncio.Task[None]] = []

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
        if self._stale_block:
            return False
        if getattr(self._coordinator, "_entries_paused", False):
            return False
        # Micro-Trade rolling count HOLDs at 1000 completed cycles.
        return self._daily_trade_count < 1000

    def protection_active(self, position_id: str) -> bool:
        return self._broker.protection_active(position_id)

    def _loss_limit_usdt(self) -> Decimal:
        raw = getattr(self._profile.risk, "rolling_24h_loss_limit", None)
        if raw is None:
            return Decimal("500")
        return Decimal(str(raw))

    def _market_is_stale(self) -> bool:
        scopes = self.market_scopes()
        if not scopes:
            return False
        max_age = timedelta(seconds=30)
        return any(not self._market.fresh(scope, max_age) for scope in scopes)

    def _open_positions(self) -> tuple[object, ...]:
        opener = getattr(self._broker, "open_positions", None)
        if callable(opener):
            return tuple(opener())
        spot = getattr(self._broker, "spot", None)
        futures = getattr(self._broker, "futures", None)
        positions: list[object] = []
        if spot is not None:
            positions.extend(spot.open_positions())
        if futures is not None:
            positions.extend(futures.open_positions())
        return tuple(positions)

    async def _entry_loop(self) -> None:
        try:
            while self._running:
                for scope in self.market_scopes():
                    if self.new_entries_allowed(scope):
                        # Do not invent fake orders. Entries require a real planner.
                        pass
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise

    async def _protection_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(1)
                for position in self._open_positions():
                    position_id = getattr(position, "position_id", None)
                    if position_id is None:
                        continue
                    # Keep existing broker protection live; never invent SL/TP prices.
                    self._broker.protection_active(str(position_id))
        except asyncio.CancelledError:
            raise

    async def _breaker_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(1)
                result = await self._breaker.evaluate(self._loss_limit_usdt())
                if result.tripped:
                    # Trip already disables new entries via breaker._tripped.
                    pass
        except asyncio.CancelledError:
            raise

    async def _freshness_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(1)
                self._stale_block = self._market_is_stale()
        except asyncio.CancelledError:
            raise

    async def start(self) -> None:
        self._running = True
        self._stale_block = False
        await self._market.start(self.market_scopes())
        if not self._tasks:
            self._tasks = [
                asyncio.create_task(self._entry_loop(), name="entry-loop"),
                asyncio.create_task(self._protection_loop(), name="protection-loop"),
                asyncio.create_task(self._breaker_loop(), name="breaker-loop"),
                asyncio.create_task(self._freshness_loop(), name="freshness-loop"),
            ]

    async def pause(self) -> None:
        self._coordinator.pause_entries()

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks = []
        await self._market.stop()
