"""Autonomous paper owner: portfolio broker + coordinator + genome planner."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from goldguard.broker.paper_futures import PaperFuturesBroker
from goldguard.broker.paper_portfolio import PaperPortfolioBroker
from goldguard.broker.paper_spot import PaperSpotBroker
from goldguard.config import Settings
from goldguard.domain.enums import BotState, ExecutionMode, ExitReason, ProductKind
from goldguard.domain.models import Candle, Quote
from goldguard.domain.profile import AutonomousProfile
from goldguard.execution.models import MarketScope
from goldguard.market.catalog import SymbolCatalog, SymbolNotEligible
from goldguard.memory.recorder import LearningRecorder
from goldguard.risk.circuit_breaker import CircuitBreaker
from goldguard.services.emergency import EmergencyService
from goldguard.services.execution_coordinator import ExecutionCoordinator
from goldguard.services.genome_planner import GenomeEntryPlanner
from goldguard.services.market_supervisor import MarketSupervisor
from goldguard.services.runtime import RuntimeStatus
from goldguard.services.runtime_supervisor import RuntimeSupervisor
from goldguard.storage.database import Database
from goldguard.storage.execution_repository import ExecutionRepository
from goldguard.storage.repositories import GenomeRepository, ReflectionRepository


class AutonomousRuntime:
    def __init__(
        self,
        *,
        settings: Settings,
        database: Database,
        profile: AutonomousProfile,
        genome_repo: GenomeRepository,
        reflection_repo: ReflectionRepository | None,
        spot_client: object | None = None,
    ) -> None:
        self._settings = settings
        self._database = database
        self._profile = profile
        self._genome_repo = genome_repo
        cash = settings.paper_starting_balance
        self._spot = PaperSpotBroker(
            starting_cash=cash,
            fee_rate=settings.taker_fee_rate,
            slippage_rate=settings.slippage_rate,
        )
        self._futures = PaperFuturesBroker(
            starting_collateral=cash if profile.futures_enabled else Decimal("0")
        )
        self._broker = PaperPortfolioBroker(spot=self._spot, futures=self._futures)
        self._books: dict[str, dict[str, list[Candle]]] = {}
        self._planner = GenomeEntryPlanner(self._books, cash)
        self._coordinator = ExecutionCoordinator(
            broker=self._broker,
            repository=ExecutionRepository(database),
            database=database,
            entry_planner=self._planner,
        )
        self._catalog = SymbolCatalog(spot_client=spot_client, futures_client=None)
        self._market = MarketSupervisor(catalog=self._catalog)
        self._breaker = CircuitBreaker()
        self._emergency = EmergencyService(broker=self._broker, coordinator=self._coordinator)
        self._supervisor = RuntimeSupervisor(
            profile=profile,
            market=self._market,
            broker=self._broker,
            coordinator=self._coordinator,
            breaker=self._breaker,
            emergency=self._emergency,
        )
        self._learning = (
            LearningRecorder(reflection_repo) if reflection_repo is not None else None
        )
        self._running = False
        self._paused = True
        self._halted = False
        self._mae: dict[str, Decimal] = {}
        self._mfe: dict[str, Decimal] = {}
        self._flatten_task: asyncio.Task[None] | None = None

    @property
    def broker(self) -> PaperPortfolioBroker:
        return self._broker

    @property
    def supervisor(self) -> RuntimeSupervisor:
        return self._supervisor

    def apply_profile(self, profile: AutonomousProfile) -> None:
        self._profile = profile
        self._supervisor.apply_profile(profile)

    def start(self) -> None:
        if self._halted:
            raise RuntimeError("paper runtime is halted and requires manual reset")
        self._running = True
        self._paused = False
        self._supervisor._running = True
        self._coordinator.resume_entries()

    def pause(self) -> None:
        self._paused = True
        self._coordinator.pause_entries()

    def stop(self) -> None:
        self._paused = True
        self._running = False
        self._halted = True
        self._coordinator.pause_entries()
        self._supervisor._running = False
        try:
            loop = asyncio.get_running_loop()
            self._flatten_task = loop.create_task(self._flatten())
        except RuntimeError:
            asyncio.run(self._flatten())

    async def _flatten(self) -> None:
        scopes = self._supervisor.market_scopes()
        await self._emergency.cancel_entries(scopes)
        await self._emergency.close_owned_positions(scopes, ExitReason.EMERGENCY)

    def shutdown(self) -> None:
        self._running = False
        self._paused = True

    def seed_history(
        self, symbol: str, candles_15m: list[Candle], candles_1h: list[Candle]
    ) -> None:
        book = self._books.setdefault(symbol, {"15m": [], "1h": []})
        book["15m"] = list(candles_15m)
        book["1h"] = list(candles_1h)

    def status(self) -> RuntimeStatus:
        open_positions = self._broker.open_positions()
        return RuntimeStatus(
            state=BotState.EMERGENCY_STOPPED
            if self._halted
            else (
                BotState.RUNNING_OPEN
                if self._running and open_positions
                else BotState.RUNNING_FLAT
                if self._running
                else BotState.PAPER_READY
            ),
            running=self._running and not self._paused and not self._halted,
            paused=self._paused,
            halted=self._halted,
            paper_account_id="paper-autonomous",
            has_position=bool(open_positions),
            market_verified=True,
            market_source="binance-public",
            degraded_reasons=(),
            rehydration_error=None,
        )

    def pnl_by_symbol(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for position in self._broker.open_positions():
            rows.append(
                {
                    "symbol": position.symbol,
                    "product": position.product.value,
                    "quantity": str(position.quantity),
                    "entry": str(position.entry_price),
                    "unrealized": str(position.unrealized_pnl),
                    "side": position.side.value,
                }
            )
        return rows

    async def on_quote(self, quote: Quote, symbol: str | None = None) -> None:
        target = symbol or self._settings.symbol
        if target not in self._profile.spot_pairs:
            return
        mid = (quote.bid + quote.ask) / Decimal("2")
        self._spot.on_price(target, mid)
        self._track_excursion(target, mid)
        scope = MarketScope(
            mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol=target
        )
        results = await self._coordinator.manage_positions(scope, quote)
        if results.action == "STOP" and results.result is not None:
            await self._record_close(target, results.result)

    async def on_closed_candle(self, candle: Candle, quote: Quote) -> None:
        if candle.symbol not in self._profile.spot_pairs:
            return
        book = self._books.setdefault(candle.symbol, {"15m": [], "1h": []})
        series = book["15m"]
        if not series or series[-1].close_time != candle.close_time:
            series.append(candle)
        self._spot.on_price(candle.symbol, candle.close)
        scope = MarketScope(
            mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol=candle.symbol
        )
        self._supervisor.note_closed_candle(scope, candle, quote)
        await self.on_quote(quote, symbol=candle.symbol)
        if not self._running or self._paused or self._halted:
            return
        if not self._supervisor.new_entries_allowed(scope):
            return
        if not await self._catalog_allows(candle.symbol):
            return
        self._planner.set_cash(self._spot.cash)
        outcome = await self._coordinator.evaluate(scope, candle)
        if outcome.action == "ENTER":
            self._planner.mark_open(candle.symbol)
            self._mae[candle.symbol] = Decimal("0")
            self._mfe[candle.symbol] = Decimal("0")

    async def _catalog_allows(self, symbol: str) -> bool:
        if self._catalog.spot_client is None:
            return True
        try:
            if self._catalog._snapshot is None:
                await self._catalog.refresh()
            self._catalog.require(ProductKind.SPOT, symbol)
            return True
        except (SymbolNotEligible, Exception):
            return False

    async def _record_close(self, symbol: str, result: object) -> None:
        self._planner.mark_flat(symbol)
        position = getattr(result, "position", None)
        if position is None or self._learning is None:
            return
        trade_id = f"auto-{getattr(position, 'position_id', symbol)}"
        realized = Decimal(str(getattr(position, "realized_pnl", "0")))
        fee = Decimal("0")
        order = getattr(result, "order", None)
        if order is not None:
            fee = Decimal(str(getattr(order, "fee", "0")))
        from goldguard.broker.base import ClosedPaperTrade, PaperFill
        from goldguard.domain.enums import ExitReason, OrderSide

        now = datetime.now(UTC)
        dummy_entry = PaperFill(
            client_order_id=f"entry-{trade_id}",
            side=OrderSide.BUY,
            quantity=Decimal(str(position.quantity or "0")) or Decimal("0.0001"),
            price=Decimal(str(position.entry_price)),
            fee=fee / Decimal("2"),
            filled_at=now,
        )
        dummy_exit = PaperFill(
            client_order_id=f"exit-{trade_id}",
            side=OrderSide.SELL,
            quantity=dummy_entry.quantity,
            price=Decimal(str(position.current_price or position.entry_price)),
            fee=fee / Decimal("2"),
            filled_at=now,
        )
        closed = ClosedPaperTrade(
            entry_fill=dummy_entry,
            exit_fill=dummy_exit,
            exit_reason=ExitReason.TAKE_PROFIT
            if realized >= 0
            else ExitReason.STOP_LOSS,
            realized_pnl=realized,
        )
        genome = self._genome_repo.get_active_genome()
        self._learning.record_closed_trade(
            closed,
            trade_id=trade_id,
            symbol=symbol,
            genome_id=genome.genome_id if genome is not None else None,
            mae=self._mae.get(symbol, Decimal("0")),
            mfe=self._mfe.get(symbol, Decimal("0")),
        )

    def _track_excursion(self, symbol: str, price: Decimal) -> None:
        for position in self._broker.open_positions():
            if position.symbol != symbol:
                continue
            unrealized = (price - position.entry_price) * position.quantity
            self._mae[symbol] = min(self._mae.get(symbol, Decimal("0")), unrealized)
            self._mfe[symbol] = max(self._mfe.get(symbol, Decimal("0")), unrealized)
