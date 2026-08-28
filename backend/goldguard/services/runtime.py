from __future__ import annotations

import asyncio
import hashlib
import inspect
import threading
from collections.abc import AsyncGenerator
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Protocol, cast
from uuid import uuid4

from goldguard.ai.gemini import AiAssessment, DecisionRequest
from goldguard.broker.base import ClosedPaperTrade, PaperFill, PaperPosition
from goldguard.broker.paper import PaperBroker
from goldguard.config import Settings
from goldguard.context.calendar import CalendarEvent, EconomicCalendar
from goldguard.context.models import ContextItem, ContextSnapshot, ContextSource
from goldguard.domain.enums import BotState, ExitReason, OrderSide
from goldguard.domain.models import Candle, Quote, TradePlan
from goldguard.market.binance import SymbolFilters
from goldguard.observability.events import AgentEvent, EventBus
from goldguard.risk.engine import RiskDecision, RiskEngine
from goldguard.risk.state_machine import StateMachine
from goldguard.services.coordinator import (
    AiVetoGate,
    ChecklistGate,
    DecisionOutcome,
    ExitOutcome,
    TradingCoordinator,
)
from goldguard.storage.database import Database
from goldguard.storage.repositories import AgentEventRepository, GenomeRepository, LedgerRepository
from goldguard.strategy.indicators import atr_wilder, ema_series, median_volume_ratio, rsi_wilder
from goldguard.strategy.runtime import FeatureSnapshot, GenomeRuntime

_MARKET_SOURCE_URL = (
    "https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints"
)


def _calendar_item_summary(event: CalendarEvent, *, active: bool) -> str:
    flag = "BLACKOUT — " if active else ""
    when = event.when.strftime("%Y-%m-%d %H:%M UTC")
    return f"{flag}{event.title} ({event.country} {event.impact}) at {when}"


_RUNTIME_ERROR_RECORDED_ATTR = "_goldguard_runtime_error_recorded"


def is_runtime_error_recorded(error: BaseException) -> bool:
    """Return whether the same exception instance already has a durable error row."""
    return bool(getattr(error, _RUNTIME_ERROR_RECORDED_ATTR, False))


def mark_runtime_error_recorded(error: BaseException) -> None:
    """Mark an exception instance after its durable error row has been written."""
    setattr(error, _RUNTIME_ERROR_RECORDED_ATTR, True)


@dataclass(frozen=True)
class RuntimeStatus:
    state: BotState
    running: bool
    paused: bool
    halted: bool
    paper_account_id: str
    has_position: bool
    market_verified: bool
    market_source: str
    degraded_reasons: tuple[str, ...]
    rehydration_error: str | None


class AsyncAiVetoGate(Protocol):
    async def decide(self, request: DecisionRequest) -> AiAssessment: ...


class _AsyncDecisionAdapter:
    """Runs an async veto engine on a private loop so the sync coordinator can call it."""

    def __init__(self, gate: AsyncAiVetoGate) -> None:
        self._gate = gate
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="goldguard-ai-veto",
            daemon=True,
        )
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def decide(self, request: DecisionRequest) -> AiAssessment:
        future: Future[AiAssessment] = asyncio.run_coroutine_threadsafe(
            self._gate.decide(request), self._loop
        )
        return future.result(timeout=35)

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=1)


class TradingRuntime:
    def __init__(
        self,
        *,
        database: Database,
        settings: Settings,
        broker: PaperBroker,
        genome_repo: GenomeRepository,
        ledger_repo: LedgerRepository,
        strategy_runtime: GenomeRuntime,
        risk_engine: RiskEngine,
        filters: SymbolFilters | None,
        state_machine: StateMachine,
        candles_15m: list[Candle],
        candles_1h: list[Candle],
        latest_quote: Quote | None,
        checklist: ChecklistGate | None = None,
        ai_veto: AiVetoGate | AsyncAiVetoGate | None = None,
        market_source: str = "startup-degraded",
        market_verified: bool = False,
        calendar: EconomicCalendar | None = None,
    ) -> None:
        self._database = database
        self._settings = settings
        self._broker = broker
        self._ledger_repo = ledger_repo
        self._state_machine = state_machine
        self._filters = filters
        self._candles_15m = list(candles_15m)
        self._candles_1h = list(candles_1h)
        self._latest_quote = latest_quote
        self._market_source = market_source
        self._market_verified = market_verified
        self._calendar = calendar
        self._degraded_reasons: tuple[str, ...] = ()
        self._event_bus = EventBus(sink=AgentEventRepository(database))
        self._ai_veto = self._wrap_ai_gate(ai_veto)
        self._coordinator = TradingCoordinator(
            broker=broker,
            genome_repo=genome_repo,
            ledger_repo=ledger_repo,
            runtime=strategy_runtime,
            risk_engine=risk_engine,
            checklist=checklist,
            ai_veto=self._ai_veto,
            filters=filters,
            blackout_check=self._is_event_blackout,
        )
        self._paper_account_id = (
            self._ledger_repo.current_paper_session_id()
            or self._ledger_repo.create_paper_session(self._settings.paper_starting_balance)
        )
        self._rehydration_error = self._rehydrate_broker_state()
        self._state = BotState.PAPER_READY
        self._paused = False
        self._halted = False
        self._restore_runtime_state()
        self._refresh_market_status()

    def apply_knobs(
        self,
        settings: Settings,
        risk_engine: RiskEngine,
        *,
        reset_session: bool,
    ) -> str:
        """Apply in-app paper knobs without a Railway restart. Reset requires a flat book."""
        if reset_session and self._broker.position is not None:
            raise RuntimeError("close the open paper position before changing starting balance")
        self._settings = settings
        self._coordinator.risk_engine = risk_engine
        if not reset_session:
            return self._paper_account_id
        session_id = self._ledger_repo.create_paper_session(settings.paper_starting_balance)
        self._paper_account_id = session_id
        self._broker.reset_account(settings.paper_starting_balance)
        self._rehydration_error = None
        return session_id

    def _is_event_blackout(self, when: datetime) -> bool:
        if self._calendar is None:
            return False
        flagged, _event = self._calendar.is_blackout(when)
        return flagged

    def configure_market_inputs(
        self,
        *,
        source: str,
        verified: bool,
        filters: SymbolFilters | None,
        candles_15m: list[Candle],
        candles_1h: list[Candle] | None = None,
        latest_quote: Quote | None = None,
    ) -> None:
        self._market_source = source
        self._market_verified = verified
        self._filters = filters
        self._coordinator.filters = filters
        self._candles_15m = list(candles_15m)
        self._candles_1h = (
            list(candles_1h)
            if candles_1h is not None
            else self._aggregate_hourly_candles(self._candles_15m)
        )
        self._latest_quote = latest_quote
        self._refresh_market_status()

    def start(self) -> None:
        if self._halted:
            raise RuntimeError("paper runtime is halted and requires manual reset")
        if self._rehydration_error is not None:
            raise RuntimeError(
                f"persisted paper state cannot be reconstructed: {self._rehydration_error}"
            )
        if self._degraded_reasons:
            joined = ", ".join(self._degraded_reasons)
            raise RuntimeError(f"verified market inputs required before start: {joined}")

        self._paused = False
        if self._state is BotState.DISARMED:
            self._transition_to(BotState.PAPER_READY, "PAPER_RUNTIME_READY")

        target = (
            BotState.RUNNING_OPEN if self._broker.position is not None else BotState.RUNNING_FLAT
        )
        reason = (
            "PAPER_RUNTIME_RESUMED" if self._state is BotState.COOLDOWN else "PAPER_RUNTIME_STARTED"
        )
        self._transition_to(target, reason)
        self._publish_event(
            action="HOLD",
            reason="Paper runtime started",
            reason_codes=("RUNTIME_STARTED",),
            payload={
                "state": self._state.value,
                "paper_account_id": self._paper_account_id,
                "market_source": self._market_source,
            },
        )

    def pause(self) -> None:
        if self._halted:
            return
        self._paused = True
        target = BotState.COOLDOWN if self._broker.position is not None else BotState.DISARMED
        self._transition_to(target, "PAPER_RUNTIME_PAUSED")
        self._publish_event(
            action="HOLD",
            reason="New paper entries paused",
            reason_codes=("RUNTIME_PAUSED",),
            payload={"state": self._state.value, "paper_account_id": self._paper_account_id},
        )

    def stop(self) -> None:
        if self._broker.position is not None:
            if self._latest_quote is None:
                raise RuntimeError("latest quote unavailable for emergency paper exit")
            closed_trade = self._broker.exit_long(
                self._latest_quote,
                client_order_id=f"halt-{int(self._latest_quote.observed_at.timestamp())}",
                reason=ExitReason.EMERGENCY,
            )
            self._persist_closed_trade(closed_trade, exit_fill=closed_trade.exit_fill)
            self._record_equity_snapshot(self._latest_quote)
        self._paused = False
        self._halted = True
        self._transition_to(BotState.EMERGENCY_STOPPED, "EMERGENCY_STOP")
        self._publish_event(
            action="STOP",
            reason="Paper runtime halted",
            reason_codes=("RUNTIME_HALTED",),
            payload={"state": self._state.value, "paper_account_id": self._paper_account_id},
            audit_worthy=True,
        )

    def status(self) -> RuntimeStatus:
        return RuntimeStatus(
            state=self._state,
            running=self._state
            in (BotState.RUNNING_FLAT, BotState.RUNNING_OPEN, BotState.COOLDOWN),
            paused=self._paused,
            halted=self._halted,
            paper_account_id=self._paper_account_id,
            has_position=self._broker.position is not None,
            market_verified=not self._degraded_reasons and self._market_verified,
            market_source=self._market_source,
            degraded_reasons=self._degraded_reasons,
            rehydration_error=self._rehydration_error,
        )

    def process_closed_candle(self, candle: Candle, quote: Quote) -> DecisionOutcome:
        try:
            return self._process_closed_candle(candle, quote)
        except Exception as exc:
            if not is_runtime_error_recorded(exc):
                self.record_runtime_error(str(exc))
                mark_runtime_error_recorded(exc)
            raise

    def record_runtime_error(self, detail: str) -> str:
        """Persist a root runtime/ingestion failure exactly once."""
        return self._ledger_repo.record_runtime_error(detail)

    def _process_closed_candle(self, candle: Candle, quote: Quote) -> DecisionOutcome:
        self._latest_quote = quote
        if self._halted:
            return DecisionOutcome(False, "RUNTIME_HALTED", ("RUNTIME_HALTED",))
        if self._rehydration_error is not None:
            return DecisionOutcome(False, "RUNTIME_BLOCKED", ("RUNTIME_REHYDRATION_FAILED",))
        if self._state not in (BotState.RUNNING_FLAT, BotState.RUNNING_OPEN, BotState.COOLDOWN):
            return DecisionOutcome(False, "RUNTIME_NOT_RUNNING", ("RUNTIME_NOT_RUNNING",))
        if candle.timeframe != self._settings.entry_timeframe:
            raise ValueError(
                f"expected {self._settings.entry_timeframe} candle, got {candle.timeframe}"
            )
        if not candle.closed:
            raise ValueError("runtime only accepts closed candles")

        self._upsert_candle(candle)
        if self._paused and self._broker.position is None:
            outcome = DecisionOutcome(False, "PAUSED", ("PAUSED_NEW_ENTRIES",))
            self._publish_decision(candle, quote, outcome, None)
            return outcome

        features = self._build_feature_snapshot(quote)
        context_snapshot = self._build_context_snapshot(candle, quote, features)
        context_snapshot_id = self._ledger_repo.save_context_snapshot(
            snapshot=context_snapshot,
            event_time=candle.close_time,
            freshness="fresh" if features.quote_fresh else "stale",
        )
        outcome = self._coordinator.scan_closed_candle(
            symbol=candle.symbol,
            closed_at=candle.close_time,
            quote=quote,
            features=features,
            context_snapshot=context_snapshot,
            account_scope=self._paper_account_id,
        )

        if outcome.decision_chain_id is not None and outcome.ai_assessment is not None:
            self._ledger_repo.save_ai_decision(
                decision_chain_id=outcome.decision_chain_id,
                context_snapshot_id=context_snapshot_id,
                assessment=outcome.ai_assessment,
            )
        if outcome.decision_chain_id is not None and outcome.risk_decision is not None:
            self._persist_risk_decision(outcome.decision_chain_id, outcome.risk_decision)
        if outcome.fill is not None:
            self._persist_entry(outcome.fill)
            self._record_equity_snapshot(quote)
        if outcome.closed_trade is not None:
            self._persist_closed_trade(
                outcome.closed_trade, exit_fill=outcome.closed_trade.exit_fill
            )
            self._record_equity_snapshot(quote)

        self._sync_state_after_broker_change()
        self._publish_decision(candle, quote, outcome, features)
        return outcome

    def process_quote(self, quote: Quote) -> ExitOutcome | None:
        try:
            return self._process_quote(quote)
        except Exception as exc:
            if not is_runtime_error_recorded(exc):
                self.record_runtime_error(str(exc))
                mark_runtime_error_recorded(exc)
            raise

    def _process_quote(self, quote: Quote) -> ExitOutcome | None:
        self._latest_quote = quote
        outcome = self._coordinator.monitor_open_position(quote)
        if outcome is None or outcome.closed_trade is None:
            return outcome
        self._persist_closed_trade(outcome.closed_trade, exit_fill=outcome.closed_trade.exit_fill)
        self._record_equity_snapshot(quote)
        self._sync_state_after_broker_change()
        self._publish_exit(quote, outcome)
        return outcome

    def recent_events(self, limit: int = 30) -> tuple[AgentEvent, ...]:
        return self._event_bus.recent(limit)

    def subscribe_events(self) -> AsyncGenerator[AgentEvent, None]:
        """Live fanout for the SSE endpoint. Slow consumers lose oldest events, never block."""
        return self._event_bus.subscribe()

    def candles(self, timeframe: str) -> tuple[Candle, ...]:
        return tuple(self._candles_1h if timeframe == "1h" else self._candles_15m)

    def latest_quote(self) -> Quote | None:
        return self._latest_quote

    def shutdown(self) -> None:
        if isinstance(self._ai_veto, _AsyncDecisionAdapter):
            self._ai_veto.close()

    @staticmethod
    def _wrap_ai_gate(ai_veto: AiVetoGate | AsyncAiVetoGate | None) -> AiVetoGate | None:
        if ai_veto is None:
            return None
        if inspect.iscoroutinefunction(getattr(ai_veto, "decide", None)):
            return _AsyncDecisionAdapter(cast(AsyncAiVetoGate, ai_veto))
        return cast(AiVetoGate, ai_veto)

    def _restore_runtime_state(self) -> None:
        stored_state = self._load_state()
        self._halted = stored_state is BotState.EMERGENCY_STOPPED
        self._paused = stored_state is BotState.COOLDOWN
        if stored_state is BotState.EMERGENCY_STOPPED:
            self._state = BotState.EMERGENCY_STOPPED
            return
        if stored_state is None or stored_state in (
            BotState.BOOTING,
            BotState.PAPER_READY,
            BotState.DISARMED,
        ):
            # ponytail: boot normalisation, not an operational move — state_transitions stays
            # the audit trail of what the running bot did, so no row is written here.
            self._state = BotState.PAPER_READY
            self._persist_app_state()
            return

        transition = self._state_machine.on_restart(stored_state)
        self._state = transition.to_state
        self._persist_app_state()
        self._ledger_repo.record_state_transition(
            from_state=transition.from_state.value,
            to_state=transition.to_state.value,
            reason=transition.reason,
        )

    def _load_state(self) -> BotState | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT bot_state FROM app_state WHERE singleton = 1"
            ).fetchone()
        if row is None:
            return None
        try:
            return BotState(str(row["bot_state"]))
        except ValueError:
            return None

    def _refresh_market_status(self) -> None:
        reasons: list[str] = []
        if not self._market_verified:
            reasons.append("MARKET_NOT_VERIFIED")
        if self._filters is None:
            reasons.append("MARKET_FILTERS_UNAVAILABLE")
        if len(self._candles_15m) < 50:
            reasons.append("INSUFFICIENT_15M_HISTORY")
        if len(self._candles_1h) < 50:
            reasons.append("INSUFFICIENT_1H_HISTORY")
        if self._latest_quote is None:
            reasons.append("LATEST_QUOTE_UNAVAILABLE")
        self._degraded_reasons = tuple(reasons)

    def _persist_app_state(self) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE app_state SET bot_state = ? WHERE singleton = 1",
                (self._state.value,),
            )

    def _transition_to(self, target: BotState, reason: str) -> None:
        current = self._state
        if current is target:
            self._persist_app_state()
            return
        transition = self._state_machine.transition(current, target, reason=reason)
        self._state = transition.to_state
        self._persist_app_state()
        self._ledger_repo.record_state_transition(
            from_state=transition.from_state.value,
            to_state=transition.to_state.value,
            reason=transition.reason,
        )

    def _sync_state_after_broker_change(self) -> None:
        if self._halted:
            self._transition_to(BotState.EMERGENCY_STOPPED, "EMERGENCY_STOP")
            return
        if self._state not in (BotState.RUNNING_FLAT, BotState.RUNNING_OPEN, BotState.COOLDOWN):
            # A disarmed/ready runtime still protects an inherited position, but closing it
            # must never re-arm the bot for new entries.
            return
        if self._paused:
            target = BotState.COOLDOWN if self._broker.position is not None else BotState.DISARMED
        else:
            target = (
                BotState.RUNNING_OPEN
                if self._broker.position is not None
                else BotState.RUNNING_FLAT
            )
        self._transition_to(target, "POSITION_STATUS_UPDATED")

    def _rehydrate_broker_state(self) -> str | None:
        session = self._ledger_repo.get_paper_session(self._paper_account_id)
        if session is None:
            return "current paper session missing"

        trade_rows = self._ledger_repo.list_trades(self._paper_account_id)
        snapshot = self._ledger_repo.latest_equity_snapshot(self._paper_account_id)
        if trade_rows and snapshot is None:
            return "latest equity snapshot missing"

        if not trade_rows:
            self._broker._cash = session.initial_balance
            self._broker._position = None
            self._broker._fills = []
            self._broker._order_results = {}
            return None

        order_rows = self._ledger_repo.list_order_fills(self._paper_account_id)
        fills_by_order: dict[str, PaperFill] = {}
        order_client_ids: dict[str, str] = {}
        ordered_fills: list[PaperFill] = []

        for row in order_rows:
            order_id = str(row["order_id"])
            client_order_id = str(row["client_order_id"])
            order_client_ids[order_id] = client_order_id
            if row["fill_id"] is None:
                continue
            fill = PaperFill(
                client_order_id=client_order_id,
                side=OrderSide(str(row["side"])),
                quantity=Decimal(str(row["quantity_text"])),
                price=Decimal(str(row["price_text"])),
                fee=Decimal(str(row["fee_text"])),
                filled_at=datetime.fromisoformat(str(row["occurred_at"])),
            )
            fills_by_order[order_id] = fill
            ordered_fills.append(fill)

        order_results: dict[str, PaperFill | ClosedPaperTrade] = {}
        open_position: PaperPosition | None = None
        ordered_fills.sort(key=lambda fill: fill.filled_at)

        for trade in trade_rows:
            entry_fill = fills_by_order.get(str(trade["entry_order_id"]))
            if entry_fill is None:
                return f"entry fill missing for trade {trade['id']}"
            order_results[entry_fill.client_order_id] = entry_fill
            if str(trade["status"]) == "CLOSED":
                exit_order_id = str(trade["exit_order_id"])
                exit_fill = fills_by_order.get(exit_order_id)
                if exit_fill is None:
                    return f"exit fill missing for trade {trade['id']}"
                exit_client_order_id = order_client_ids.get(exit_order_id)
                if exit_client_order_id is None:
                    return f"exit order missing for trade {trade['id']}"
                order_results[exit_client_order_id] = ClosedPaperTrade(
                    entry_fill=entry_fill,
                    exit_fill=exit_fill,
                    exit_reason=self._infer_exit_reason(exit_client_order_id),
                    realized_pnl=Decimal(str(trade["realized_pnl_text"] or "0")),
                )
                continue

            plan_payload = self._ledger_repo.load_trade_plan(
                paper_account_id=self._paper_account_id,
                opened_at=str(trade["opened_at"]),
            )
            if plan_payload is None:
                return f"trade plan missing for open trade {trade['id']}"
            open_position = PaperPosition(
                plan=TradePlan.model_validate(plan_payload),
                entry_fill=entry_fill,
            )

        self._broker._cash = (
            Decimal(str(snapshot["cash_text"])) if snapshot else session.initial_balance
        )
        self._broker._position = open_position
        self._broker._fills = ordered_fills
        self._broker._order_results = order_results
        return None

    def _upsert_candle(self, candle: Candle) -> None:
        duplicate = next(
            (
                index
                for index, current in enumerate(self._candles_15m)
                if current.close_time == candle.close_time and current.symbol == candle.symbol
            ),
            None,
        )
        if duplicate is None:
            self._candles_15m.append(candle)
            self._candles_15m.sort(key=lambda current: current.close_time)
        else:
            self._candles_15m[duplicate] = candle
        if not self._candles_1h:
            self._candles_1h = self._aggregate_hourly_candles(self._candles_15m)
        elif len(self._candles_15m) >= 4 and len(self._candles_15m) % 4 == 0:
            next_hour = self._aggregate_hour_from_batch(self._candles_15m[-4:])
            if next_hour is not None:
                if self._candles_1h and self._candles_1h[-1].close_time == next_hour.close_time:
                    self._candles_1h[-1] = next_hour
                elif not self._candles_1h or self._candles_1h[-1].close_time < next_hour.close_time:
                    self._candles_1h.append(next_hour)
        self._refresh_market_status()

    def _build_feature_snapshot(self, quote: Quote) -> FeatureSnapshot:
        candles_15m = self._candles_15m[-250:]
        candles_1h = self._candles_1h[-250:]
        latest = candles_15m[-1]
        previous = candles_15m[-2] if len(candles_15m) > 1 else latest
        close_values_15m = [float(candle.close) for candle in candles_15m]
        close_values_1h = [float(candle.close) for candle in candles_1h]
        high_values_15m = [float(candle.high) for candle in candles_15m]
        low_values_15m = [float(candle.low) for candle in candles_15m]
        volume_values_15m = [float(candle.volume) for candle in candles_15m]

        ema20 = ema_series(close_values_15m, 20)
        ema50 = ema_series(close_values_15m, 50)
        ema50_1h_series = ema_series(close_values_1h, 50) if close_values_1h else []
        ema200_1h_series = ema_series(close_values_1h, 200) if close_values_1h else []
        rsi_values = rsi_wilder(close_values_15m, 14)
        atr_values = atr_wilder(high_values_15m, low_values_15m, close_values_15m, 14)

        ema50_1h = ema50_1h_series[-1] if ema50_1h_series else float(latest.close)
        ema200_1h = ema200_1h_series[-1] if ema200_1h_series else float(latest.close)
        prior_ema50_1h = ema50_1h_series[-5] if len(ema50_1h_series) >= 5 else ema50_1h
        atr14 = atr_values[-1] if atr_values and atr_values[-1] is not None else None
        previous_rsi = rsi_values[-2] if len(rsi_values) >= 2 else None
        current_rsi = rsi_values[-1] if rsi_values else None
        volume_ratio = (
            median_volume_ratio(volume_values_15m, 20) if len(volume_values_15m) >= 20 else 0.0
        )
        quote_fresh = abs((quote.observed_at - latest.close_time).total_seconds()) <= 120

        return FeatureSnapshot(
            previous_close=float(previous.close),
            latest_close=float(latest.close),
            ema20_15m=ema20[-1] if ema20 else float(latest.close),
            ema50_15m=ema50[-1] if ema50 else float(latest.close),
            previous_rsi14=previous_rsi if previous_rsi is not None else 50.0,
            rsi14=current_rsi if current_rsi is not None else 50.0,
            atr14=atr14 if atr14 is not None else float(latest.high - latest.low),
            atr_rate=(atr14 / float(latest.close))
            if atr14 is not None and float(latest.close) > 0
            else 0.0,
            volume_ratio=volume_ratio,
            spread_rate=float(quote.spread_rate),
            latest_close_1h=close_values_1h[-1] if close_values_1h else float(latest.close),
            ema50_1h=ema50_1h,
            ema200_1h=ema200_1h,
            ema50_slope_1h=(ema50_1h - prior_ema50_1h) / 5 if close_values_1h else 0.0,
            consecutive_closes_below_ema50=self._consecutive_closes_below_ema50(candles_15m, ema50),
            sufficient_history=len(candles_15m) >= 50 and len(candles_1h) >= 50,
            contiguous=self._is_contiguous(candles_15m[-50:], timedelta(minutes=15)),
            quote_fresh=quote_fresh,
        )

    def _build_context_snapshot(
        self,
        candle: Candle,
        quote: Quote,
        features: FeatureSnapshot,
    ) -> ContextSnapshot:
        sources = [
            ContextSource(
                url=_MARKET_SOURCE_URL,
                title="Binance market data endpoints",
                published_at=None,
            )
        ]
        items = [
            ContextItem(
                summary=(
                    f"Closed {candle.symbol} candle at {candle.close_time.isoformat()} "
                    f"with spread rate {float(quote.spread_rate):0.6f}; "
                    f"{'contiguous history' if features.contiguous else 'history gap'}."
                ),
                driver="market-data",
                direction="neutral",
                severity="low" if features.quote_fresh else "medium",
                published_at=quote.observed_at,
                source_indexes=(0,),
                contradictory=False,
            )
        ]
        if self._calendar is not None:
            sources.append(
                ContextSource(
                    url="https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                    title="USD high-impact event calendar",
                    published_at=self._calendar.updated_at,
                )
            )
            blackout, active = self._calendar.is_blackout(quote.observed_at)
            for event in self._calendar.upcoming(limit=4):
                items.append(
                    ContextItem(
                        summary=_calendar_item_summary(event, active=blackout and active is event),
                        driver="macro",
                        direction="neutral",
                        severity="high" if event.high_impact_usd else "medium",
                        published_at=event.when,
                        source_indexes=(1,),
                        contradictory=False,
                    )
                )
        return ContextSnapshot.build(
            fetched_at=quote.observed_at,
            sources=tuple(sources),
            items=tuple(items),
            conflict_level="HIGH" if self._is_event_blackout(quote.observed_at) else "LOW",
        )

    @staticmethod
    def _aggregate_hourly_candles(candles_15m: list[Candle]) -> list[Candle]:
        hourly: list[Candle] = []
        for start in range(0, len(candles_15m), 4):
            batch = candles_15m[start : start + 4]
            if len(batch) < 4:
                break
            hour = TradingRuntime._aggregate_hour_from_batch(batch)
            if hour is not None:
                hourly.append(hour)
        return hourly

    @staticmethod
    def _aggregate_hour_from_batch(batch: list[Candle]) -> Candle | None:
        if len(batch) != 4:
            return None
        return Candle(
            symbol=batch[0].symbol,
            timeframe="1h",
            open_time=batch[0].open_time,
            close_time=batch[-1].close_time,
            open=batch[0].open,
            high=max(candle.high for candle in batch),
            low=min(candle.low for candle in batch),
            close=batch[-1].close,
            volume=sum((candle.volume for candle in batch), Decimal("0")),
            closed=True,
        )

    @staticmethod
    def _consecutive_closes_below_ema50(candles: list[Candle], ema50: list[float]) -> int:
        count = 0
        for candle, average in zip(reversed(candles), reversed(ema50), strict=False):
            if float(candle.close) < average:
                count += 1
                continue
            break
        return count

    @staticmethod
    def _is_contiguous(candles: list[Candle], expected_gap: timedelta) -> bool:
        if len(candles) <= 1:
            return True
        for previous, current in pairwise(candles):
            if current.open_time - previous.open_time != expected_gap:
                return False
        return True

    def _persist_risk_decision(self, decision_chain_id: str, risk_decision: RiskDecision) -> None:
        self._ledger_repo.save_risk_decision(
            decision_chain_id=decision_chain_id,
            approved=risk_decision.approved,
            details={
                "reason_codes": risk_decision.reason_codes,
                "plan": risk_decision.plan.model_dump(mode="json") if risk_decision.plan else None,
            },
        )

    def _persist_entry(self, fill: PaperFill) -> None:
        order_id = self._stable_id("order", fill.client_order_id)
        trade_id = self._stable_id("trade", fill.client_order_id)
        fill_id = self._stable_id("fill", fill.client_order_id)
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO orders(
                    id, mode, paper_account_id, client_order_id, side,
                    quantity_text, status, created_at
                ) VALUES (?, 'paper', ?, ?, ?, ?, 'FILLED', ?)
                """,
                (
                    order_id,
                    self._paper_account_id,
                    fill.client_order_id,
                    fill.side.value,
                    str(fill.quantity),
                    fill.filled_at.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO fills(
                    id, order_id, price_text, quantity_text, fee_text, occurred_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    fill_id,
                    order_id,
                    str(fill.price),
                    str(fill.quantity),
                    str(fill.fee),
                    fill.filled_at.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO trades(
                    id, mode, paper_account_id, entry_order_id, status, opened_at
                ) VALUES (?, 'paper', ?, ?, 'OPEN', ?)
                """,
                (trade_id, self._paper_account_id, order_id, fill.filled_at.isoformat()),
            )

    def _persist_closed_trade(self, trade: ClosedPaperTrade, *, exit_fill: PaperFill) -> None:
        entry_order_id = self._stable_id("order", trade.entry_fill.client_order_id)
        exit_order_id = self._stable_id("order", exit_fill.client_order_id)
        trade_id = self._stable_id("trade", trade.entry_fill.client_order_id)
        fill_id = self._stable_id("fill", exit_fill.client_order_id)
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO orders(
                    id, mode, paper_account_id, client_order_id, side,
                    quantity_text, status, created_at
                ) VALUES (?, 'paper', ?, ?, ?, ?, 'FILLED', ?)
                """,
                (
                    exit_order_id,
                    self._paper_account_id,
                    exit_fill.client_order_id,
                    exit_fill.side.value,
                    str(exit_fill.quantity),
                    exit_fill.filled_at.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO fills(
                    id, order_id, price_text, quantity_text, fee_text, occurred_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    fill_id,
                    exit_order_id,
                    str(exit_fill.price),
                    str(exit_fill.quantity),
                    str(exit_fill.fee),
                    exit_fill.filled_at.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT INTO trades(
                    id, mode, paper_account_id, entry_order_id, status, opened_at
                ) VALUES (?, 'paper', ?, ?, 'OPEN', ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    trade_id,
                    self._paper_account_id,
                    entry_order_id,
                    trade.entry_fill.filled_at.isoformat(),
                ),
            )
            connection.execute(
                """
                UPDATE trades
                SET exit_order_id = ?, status = 'CLOSED', realized_pnl_text = ?, closed_at = ?
                WHERE id = ?
                """,
                (
                    exit_order_id,
                    str(trade.realized_pnl),
                    exit_fill.filled_at.isoformat(),
                    trade_id,
                ),
            )

    def _record_equity_snapshot(self, quote: Quote) -> None:
        snapshot_id = str(uuid4())
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO equity_snapshots(
                    id, paper_account_id, equity_text, cash_text, observed_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    self._paper_account_id,
                    str(self._broker.equity(quote)),
                    str(self._broker.cash),
                    quote.observed_at.isoformat(),
                ),
            )

    def _publish_decision(
        self,
        candle: Candle,
        quote: Quote,
        outcome: DecisionOutcome,
        features: FeatureSnapshot | None,
    ) -> None:
        action = (
            "BUY"
            if outcome.fill is not None
            else "SELL"
            if outcome.closed_trade is not None
            else "HOLD"
        )
        payload: dict[str, object] = {
            "symbol": candle.symbol,
            "timeframe": candle.timeframe,
            "candle_close_time": candle.close_time.isoformat(),
            "paper_account_id": self._paper_account_id,
            "spread_rate": float(quote.spread_rate),
            "state": self._state.value,
            "market_source": self._market_source,
            # The API rebuilds the decision-pipeline card from this, so keep it machine-readable.
            "outcome_action": outcome.action,
        }
        if features is not None:
            payload["features"] = {
                "latest_close": features.latest_close,
                "rsi14": features.rsi14,
                "atr14": features.atr14,
                "volume_ratio": features.volume_ratio,
                "quote_fresh": features.quote_fresh,
            }
        self._publish_event(
            action=action,
            reason=outcome.action.replace("_", " ").title(),
            reason_codes=outcome.reason_codes,
            payload=payload,
            audit_worthy=outcome.fill is not None or outcome.closed_trade is not None,
        )

    def _publish_exit(self, quote: Quote, outcome: ExitOutcome) -> None:
        action = "TARGET" if outcome.reason == "TAKE_PROFIT_TRIGGERED" else "STOP"
        self._publish_event(
            action=action,
            reason=outcome.reason.replace("_", " ").title(),
            reason_codes=(outcome.reason,),
            payload={
                "paper_account_id": self._paper_account_id,
                "observed_at": quote.observed_at.isoformat(),
                "bid": str(quote.bid),
                "state": self._state.value,
                "market_source": self._market_source,
            },
            audit_worthy=True,
        )

    def _publish_event(
        self,
        *,
        action: str,
        reason: str,
        reason_codes: tuple[str, ...],
        payload: dict[str, object],
        audit_worthy: bool = False,
    ) -> None:
        self._event_bus.publish(
            AgentEvent.create(
                action=action,
                reason=reason,
                reason_codes=reason_codes,
                payload=payload,
                audit_worthy=audit_worthy,
            )
        )

    def _stable_id(self, kind: str, client_order_id: str) -> str:
        material = f"{kind}|{self._paper_account_id}|{client_order_id}"
        return hashlib.sha256(material.encode()).hexdigest()

    @staticmethod
    def _infer_exit_reason(client_order_id: str) -> ExitReason:
        if client_order_id.startswith("sl-"):
            return ExitReason.STOP_LOSS
        if client_order_id.startswith("tp-"):
            return ExitReason.TAKE_PROFIT
        if client_order_id.startswith("halt-"):
            return ExitReason.EMERGENCY
        if client_order_id.startswith("exit-"):
            return ExitReason.REGIME_INVALIDATION
        return ExitReason.AI_RISK_REDUCTION
