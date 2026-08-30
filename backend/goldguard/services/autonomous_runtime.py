"""Autonomous paper owner: portfolio broker + coordinator + genome planner."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from goldguard.ai.gemini import AiAssessment
from goldguard.broker.paper_futures import PaperFuturesBroker
from goldguard.broker.paper_portfolio import PaperPortfolioBroker
from goldguard.broker.paper_spot import PaperSpotBroker
from goldguard.config import Settings
from goldguard.domain.enums import AiDecision, BotState, ExecutionMode, ExitReason, ProductKind
from goldguard.domain.models import Candle, Quote
from goldguard.domain.profile import AutonomousProfile
from goldguard.execution.models import MarketScope
from goldguard.market.catalog import SymbolCatalog, SymbolNotEligible
from goldguard.memory.recorder import LearningRecorder
from goldguard.observability.events import AgentEvent, EventBus
from goldguard.risk.circuit_breaker import CircuitBreaker
from goldguard.services.emergency import EmergencyService
from goldguard.services.execution_coordinator import ExecutionCoordinator
from goldguard.services.genome_planner import GenomeEntryPlanner
from goldguard.services.market_supervisor import MarketSupervisor
from goldguard.services.runtime import RuntimeStatus
from goldguard.services.runtime_supervisor import RuntimeSupervisor
from goldguard.storage.database import Database
from goldguard.storage.execution_repository import ExecutionRepository
from goldguard.storage.repositories import GenomeRepository, LedgerRepository, ReflectionRepository

logger = logging.getLogger("goldguard.autonomous")


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
        self._planner = GenomeEntryPlanner(self._books, cash, genome_repo=genome_repo)
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
        self._last_quotes: dict[str, dict[str, str]] = {}
        self._last_evals: dict[str, dict[str, str]] = {}
        self._flatten_task: asyncio.Task[None] | None = None
        self._dataset_status = lambda: "OK"
        self._ledger = LedgerRepository(database)
        self._paper_account_id = (
            self._ledger.current_paper_session_id()
            or self._ledger.create_paper_session(cash)
        )
        self._events = EventBus(max_events=200)
        self._last_equity_at: datetime | None = None

    def set_dataset_status(self, getter: object) -> None:
        if callable(getter):
            self._dataset_status = getter

    def set_paper_account(self, account_id: str) -> None:
        if account_id:
            self._paper_account_id = account_id

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
        if self._learning is not None:
            self._learning.drain_outbox()
        self._record_equity_snapshot(force=True)
        self._events.publish(
            AgentEvent.create(
                action="HOLD",
                reason="Paper runtime started",
                reason_codes=("RUNTIME_STARTED",),
                payload={
                    "state": "RUNNING_FLAT",
                    "paper_account_id": self._paper_account_id,
                    "outcome_action": "NO_ACTION",
                },
            )
        )

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
            paper_account_id=self._paper_account_id,
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

    def recent_events(self, limit: int = 30) -> tuple[AgentEvent, ...]:
        return self._events.recent(limit)

    def subscribe_events(self) -> AsyncGenerator[AgentEvent, None]:
        return self._events.subscribe()

    async def on_quote(self, quote: Quote, symbol: str | None = None) -> None:
        target = symbol or self._settings.symbol
        if target not in self._profile.spot_pairs:
            return
        mid = (quote.bid + quote.ask) / Decimal("2")
        self._last_quotes[target] = {
            "symbol": target,
            "mid": f"{mid:.4f}".rstrip("0").rstrip("."),
            "bid": str(quote.bid),
            "ask": str(quote.ask),
            "observed_at": quote.observed_at.isoformat(),
        }
        self._spot.on_price(target, mid)
        self._track_excursion(target, mid)
        scope = MarketScope(
            mode=ExecutionMode.PAPER, product=ProductKind.SPOT, symbol=target
        )
        results = await self._coordinator.manage_positions(scope, quote)
        if results.action == "STOP" and results.result is not None:
            await self._record_close(target, results.result)
        self._record_equity_snapshot(quote.observed_at)

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
            self._remember_eval(
                candle, action="WATCH", reason="paper_not_armed", persist=False
            )
            return
        if not self._supervisor.new_entries_allowed(scope):
            self._remember_eval(candle, action="HOLD", reason="new_entries_blocked")
            return
        if not await self._catalog_allows(candle.symbol):
            self._remember_eval(candle, action="HOLD", reason="symbol_not_eligible")
            return
        # Historical 3y CORRUPT blocks Hermes promotion, not live 15m paper.
        self._planner.set_cash(self._spot.cash)
        outcome = await self._coordinator.evaluate(scope, candle)
        self._remember_eval(
            candle,
            action=outcome.action,
            reason=outcome.reason or outcome.action,
        )
        if outcome.action == "ENTER":
            self._planner.mark_open(candle.symbol)
            self._mae[candle.symbol] = Decimal("0")
            self._mfe[candle.symbol] = Decimal("0")
            self._record_equity_snapshot(force=True)

    async def evaluate_latest_bars(self) -> None:
        """Score the last closed 15m on Start so the ledger is not empty for 15 minutes."""
        if not self._running or self._paused or self._halted:
            return
        try:
            symbols = [
                symbol
                for symbol, book in self._books.items()
                if book.get("15m")
            ]
            if not symbols:
                logger.info("no seeded 15m books to evaluate on start")
                return
            for symbol in symbols:
                series = self._books[symbol]["15m"]
                candle = series[-1]
                last = self._last_quotes.get(symbol)
                if last:
                    quote = Quote(
                        bid=Decimal(str(last["bid"])),
                        ask=Decimal(str(last["ask"])),
                        observed_at=datetime.fromisoformat(last["observed_at"]),
                    )
                else:
                    quote = Quote(
                        bid=candle.close, ask=candle.close, observed_at=candle.close_time
                    )
                await self.on_closed_candle(candle, quote)
        except Exception:
            logger.exception("failed to evaluate seeded 15m bars on start")

    def context_rows(self) -> list[dict[str, object]]:
        """What the paper agent last read. Empty until a live quote or closed bar arrives."""
        rows: list[dict[str, object]] = []
        for symbol, payload in self._last_evals.items():
            close_time = payload.get("close_time") or ""
            rows.append(
                {
                    "id": f"eval-{symbol}-{close_time}",
                    "category": "agent",
                    "title": (
                        f"{symbol} last closed 15m {payload.get('close')} → "
                        f"{payload.get('action')} ({payload.get('reason')})"
                    ),
                    "direction": "bullish"
                    if payload.get("action") == "ENTER"
                    else "neutral",
                    "severity": "medium",
                    "contradictory": False,
                    "source": "paper-agent",
                    "time": close_time[11:16] if len(close_time) >= 16 else "",
                }
            )
        if self._last_evals:
            return rows
        if self._last_quotes:
            latest = max(self._last_quotes.values(), key=lambda item: item.get("observed_at", ""))
            observed = latest.get("observed_at") or ""
            rows.append(
                {
                    "id": f"watch-{latest.get('symbol')}-{observed}",
                    "category": "agent",
                    "title": (
                        f"Agent is reading {latest.get('symbol')} mid {latest.get('mid')} live. "
                        "Entries wait for the next closed 15m candle."
                    ),
                    "direction": "neutral",
                    "severity": "low",
                    "contradictory": False,
                    "source": "paper-agent",
                    "time": observed[11:16] if len(observed) >= 16 else "",
                }
            )
        return rows

    async def _catalog_allows(self, symbol: str) -> bool:
        if symbol not in self._profile.spot_pairs:
            return False
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
        from goldguard.domain.enums import OrderSide

        opened = getattr(position, "opened_at", None)
        try:
            entry_at = datetime.fromisoformat(str(opened)) if opened else datetime.now(UTC)
        except ValueError:
            entry_at = datetime.now(UTC)
        now = datetime.now(UTC)
        qty = Decimal(str(position.quantity or "0")) or Decimal("0.0001")
        exit_price = Decimal(
            str(getattr(order, "avg_price", None) or position.current_price or position.entry_price)
        )
        entry_fill = PaperFill(
            client_order_id=f"entry-{trade_id}",
            side=OrderSide.BUY,
            quantity=qty,
            price=Decimal(str(position.entry_price)),
            fee=fee / Decimal("2"),
            filled_at=entry_at,
        )
        exit_fill = PaperFill(
            client_order_id=getattr(order, "client_order_id", None) or f"exit-{trade_id}",
            side=OrderSide.SELL,
            quantity=qty,
            price=exit_price,
            fee=fee / Decimal("2") if order is None else fee,
            filled_at=now,
        )
        closed = ClosedPaperTrade(
            entry_fill=entry_fill,
            exit_fill=exit_fill,
            exit_reason=ExitReason.TAKE_PROFIT if realized >= 0 else ExitReason.STOP_LOSS,
            realized_pnl=realized,
        )
        genome = self._genome_repo.get_active_genome()
        with self._database.transaction() as connection:
            self._learning.record_closed_trade(
                closed,
                trade_id=trade_id,
                symbol=symbol,
                genome_id=genome.genome_id if genome is not None else None,
                mae=self._mae.get(symbol, Decimal("0")),
                mfe=self._mfe.get(symbol, Decimal("0")),
                connection=connection,
            )
        self._mae.pop(symbol, None)
        self._mfe.pop(symbol, None)
        self._learning.drain_outbox()
        self._record_equity_snapshot(force=True)

    def _track_excursion(self, symbol: str, price: Decimal) -> None:
        for position in self._broker.open_positions():
            if position.symbol != symbol:
                continue
            unrealized = (price - position.entry_price) * position.quantity
            self._mae[symbol] = min(self._mae.get(symbol, Decimal("0")), unrealized)
            self._mfe[symbol] = max(self._mfe.get(symbol, Decimal("0")), unrealized)

    def _mark_to_market(self) -> tuple[Decimal, Decimal]:
        cash = self._spot.cash
        equity = cash
        for position in self._broker.open_positions():
            equity += Decimal(str(position.unrealized_pnl or "0"))
        return equity, cash

    def _record_equity_snapshot(
        self, when: datetime | None = None, *, force: bool = False
    ) -> None:
        now = when or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        if (
            not force
            and self._last_equity_at is not None
            and (now - self._last_equity_at) < timedelta(seconds=30)
        ):
            return
        equity, cash = self._mark_to_market()
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO equity_snapshots(
                    id, paper_account_id, equity_text, cash_text, observed_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    self._paper_account_id,
                    str(equity),
                    str(cash),
                    now.isoformat(),
                ),
            )
        self._last_equity_at = now

    def _pipeline_action(self, action: str, reason: str) -> str:
        if action == "ENTER":
            return "ENTRY_FILLED"
        if reason in {"new_entries_blocked", "symbol_not_eligible"}:
            return "RISK_REJECTED"
        if reason in {"INSUFFICIENT_HISTORY"}:
            return "NO_ACTION"
        return "NO_ACTION"

    def _remember_eval(
        self,
        candle: Candle,
        *,
        action: str,
        reason: str,
        persist: bool = True,
    ) -> None:
        close_time = candle.close_time.isoformat()
        self._last_evals[candle.symbol] = {
            "symbol": candle.symbol,
            "action": action,
            "reason": reason,
            "close": str(candle.close),
            "close_time": close_time,
        }
        if not persist:
            return
        outcome_action = self._pipeline_action(action, reason)
        self._events.publish(
            AgentEvent.create(
                action=action,
                reason=reason,
                reason_codes=(reason,),
                payload={
                    "symbol": candle.symbol,
                    "timeframe": candle.timeframe,
                    "candle_close_time": close_time,
                    "paper_account_id": self._paper_account_id,
                    "outcome_action": outcome_action,
                    "close": str(candle.close),
                },
                audit_worthy=True,
            )
        )
        chain_id = self._ledger.record_decision_chain(
            mode="paper",
            account_scope=self._paper_account_id,
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            candle_close_time=close_time,
        )
        decision = AiDecision.APPROVE_ENTRY if action == "ENTER" else AiDecision.HOLD
        self._ledger.save_ai_decision(
            decision_chain_id=chain_id,
            context_snapshot_id=None,
            assessment=AiAssessment(
                decision=decision,
                confidence=100 if action == "ENTER" else 60,
                reason_codes=(reason,),
                rationale=reason,
                memory_refs=(),
                prompt_hash="paper-agent",
                model="genome-planner",
            ),
        )
        self._ledger.save_risk_decision(
            decision_chain_id=chain_id,
            approved=action == "ENTER",
            details={"reason_codes": [reason], "plan": {"action": action}},
        )
