from __future__ import annotations

import asyncio
import hashlib
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from goldguard.ai.decision import DecisionVetoEngine
from goldguard.ai.gemini import AiAssessment, DecisionRequest
from goldguard.broker.base import ClosedPaperTrade, PaperFill
from goldguard.broker.paper import PaperBroker
from goldguard.config import Settings
from goldguard.context.models import ContextItem, ContextSnapshot, ContextSource
from goldguard.context.playbook import ProfessionalChecklist
from goldguard.domain.enums import BotState, ExitReason
from goldguard.domain.models import Candle, Quote
from goldguard.market.binance import SymbolFilters
from goldguard.observability.events import AgentEvent, EventBus
from goldguard.risk.engine import RiskEngine
from goldguard.risk.state_machine import StateMachine
from goldguard.services.coordinator import DecisionOutcome, ExitOutcome, TradingCoordinator
from goldguard.storage.database import Database
from goldguard.storage.repositories import AgentEventRepository, GenomeRepository, LedgerRepository
from goldguard.strategy.indicators import atr_wilder, ema_series, median_volume_ratio, rsi_wilder
from goldguard.strategy.runtime import FeatureSnapshot, GenomeRuntime

_MARKET_SOURCE_URL = (
    "https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints"
)


@dataclass(frozen=True)
class RuntimeStatus:
    state: BotState
    running: bool
    paused: bool
    halted: bool
    paper_account_id: str
    has_position: bool


class _AsyncDecisionAdapter:
    def __init__(self, engine: DecisionVetoEngine) -> None:
        self._engine = engine
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
        future = asyncio.run_coroutine_threadsafe(self._engine.decide(request), self._loop)
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
        filters: SymbolFilters,
        state_machine: StateMachine,
        candles_15m: list[Candle],
        candles_1h: list[Candle],
        latest_quote: Quote,
        checklist: ProfessionalChecklist | None = None,
        ai_veto: DecisionVetoEngine | None = None,
    ) -> None:
        self._database = database
        self._settings = settings
        self._broker = broker
        self._ledger_repo = ledger_repo
        self._state_machine = state_machine
        self._filters = filters
        self._candles_15m = candles_15m
        self._candles_1h = candles_1h
        self._latest_quote = latest_quote
        self._event_bus = EventBus(sink=AgentEventRepository(database))
        self._ai_veto = _AsyncDecisionAdapter(ai_veto) if ai_veto is not None else None
        self._coordinator = TradingCoordinator(
            broker=broker,
            genome_repo=genome_repo,
            ledger_repo=ledger_repo,
            runtime=strategy_runtime,
            risk_engine=risk_engine,
            checklist=checklist,
            ai_veto=self._ai_veto,
            filters=filters,
        )
        self._paper_account_id = (
            self._ledger_repo.current_paper_session_id()
            or self._ledger_repo.create_paper_session(self._settings.paper_starting_balance)
        )
        stored_state = self._load_state()
        self._halted = stored_state is BotState.EMERGENCY_STOPPED
        self._paused = False
        if stored_state is None:
            self._state = BotState.PAPER_READY
        elif stored_state is BotState.BOOTING:
            self._state = BotState.DISARMED
        elif self._halted:
            self._state = self._state_machine.on_restart(stored_state).to_state
        elif stored_state is BotState.PAPER_READY:
            self._state = BotState.PAPER_READY
        else:
            self._state = self._state_machine.on_restart(stored_state).to_state
        if not self._halted:
            self._persist_state()

    def start(self) -> None:
        if self._halted:
            raise RuntimeError("paper runtime is halted and requires manual reset")
        self._paused = False
        if self._state is BotState.DISARMED:
            self._state = self._state_machine.transition(
                self._state,
                BotState.PAPER_READY,
                reason="PAPER_RUNTIME_READY",
            ).to_state
        target_state = BotState.RUNNING_OPEN if self._broker.position is not None else BotState.RUNNING_FLAT
        self._state = self._state_machine.transition(
            self._state,
            target_state,
            reason="PAPER_RUNTIME_STARTED",
        ).to_state
        self._persist_state()
        self._publish_event(
            action="HOLD",
            reason="Paper runtime started",
            reason_codes=("RUNTIME_STARTED",),
            payload={"state": self._state.value, "paper_account_id": self._paper_account_id},
        )

    def pause(self) -> None:
        if self._halted:
            return
        self._paused = True
        self._state = BotState.COOLDOWN if self._broker.position is not None else BotState.DISARMED
        self._persist_state()
        self._publish_event(
            action="HOLD",
            reason="New paper entries paused",
            reason_codes=("RUNTIME_PAUSED",),
            payload={"state": self._state.value, "paper_account_id": self._paper_account_id},
        )

    def stop(self) -> None:
        if self._broker.position is not None:
            closed_trade = self._broker.exit_long(
                self._latest_quote,
                client_order_id=f"halt-{int(self._latest_quote.observed_at.timestamp())}",
                reason=ExitReason.EMERGENCY,
            )
            self._persist_closed_trade(closed_trade, exit_fill=closed_trade.exit_fill)
            self._record_equity_snapshot(self._latest_quote)
        self._paused = False
        self._halted = True
        self._state = BotState.EMERGENCY_STOPPED
        self._persist_state()
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
            running=self._state in (BotState.RUNNING_FLAT, BotState.RUNNING_OPEN, BotState.COOLDOWN),
            paused=self._paused,
            halted=self._halted,
            paper_account_id=self._paper_account_id,
            has_position=self._broker.position is not None,
        )

    def process_closed_candle(self, candle: Candle, quote: Quote) -> DecisionOutcome:
        self._latest_quote = quote
        if self._halted:
            return DecisionOutcome(False, "RUNTIME_HALTED", ("RUNTIME_HALTED",))
        if self._state not in (BotState.RUNNING_FLAT, BotState.RUNNING_OPEN, BotState.COOLDOWN):
            return DecisionOutcome(False, "RUNTIME_NOT_RUNNING", ("RUNTIME_NOT_RUNNING",))
        if candle.timeframe != self._settings.entry_timeframe:
            raise ValueError(f"expected {self._settings.entry_timeframe} candle, got {candle.timeframe}")
        if not candle.closed:
            raise ValueError("runtime only accepts closed candles")

        self._upsert_candle(candle)
        if self._paused and self._broker.position is None:
            outcome = DecisionOutcome(False, "PAUSED", ("PAUSED_NEW_ENTRIES",))
            self._publish_decision(candle, quote, outcome, None)
            return outcome

        features = self._build_feature_snapshot(quote)
        context_snapshot = self._build_context_snapshot(candle, quote, features)
        outcome = self._coordinator.scan_closed_candle(
            symbol=candle.symbol,
            closed_at=candle.close_time,
            quote=quote,
            features=features,
            context_snapshot=context_snapshot,
            account_scope=self._paper_account_id,
        )

        if outcome.fill is not None:
            self._persist_entry(outcome.fill)
            self._record_equity_snapshot(quote)
        if outcome.closed_trade is not None:
            self._persist_closed_trade(outcome.closed_trade, exit_fill=outcome.closed_trade.exit_fill)
            self._record_equity_snapshot(quote)

        self._sync_state_after_broker_change()
        self._publish_decision(candle, quote, outcome, features)
        return outcome

    def process_quote(self, quote: Quote) -> ExitOutcome | None:
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

    def shutdown(self) -> None:
        if self._ai_veto is not None:
            self._ai_veto.close()

    def _load_state(self) -> BotState | None:
        with self._database.connect() as connection:
            row = connection.execute("SELECT bot_state FROM app_state WHERE singleton = 1").fetchone()
        if row is None:
            return None
        try:
            return BotState(str(row["bot_state"]))
        except ValueError:
            return None

    def _persist_state(self) -> None:
        with self._database.transaction() as connection:
            connection.execute(
                "UPDATE app_state SET bot_state = ? WHERE singleton = 1",
                (self._state.value,),
            )

    def _sync_state_after_broker_change(self) -> None:
        if self._halted:
            self._state = BotState.EMERGENCY_STOPPED
        elif self._broker.position is not None:
            self._state = BotState.COOLDOWN if self._paused else BotState.RUNNING_OPEN
        else:
            self._state = BotState.DISARMED if self._paused else BotState.RUNNING_FLAT
        self._persist_state()

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
        self._candles_1h[:] = self._aggregate_hourly_candles(self._candles_15m)

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
            median_volume_ratio(volume_values_15m, 20)
            if len(volume_values_15m) >= 20
            else 0.0
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
            atr_rate=(
                (atr14 / float(latest.close))
                if atr14 is not None and float(latest.close) > 0
                else 0.0
            ),
            volume_ratio=volume_ratio,
            spread_rate=float(quote.spread_rate),
            latest_close_1h=close_values_1h[-1] if close_values_1h else float(latest.close),
            ema50_1h=ema50_1h,
            ema200_1h=ema200_1h,
            ema50_slope_1h=(ema50_1h - prior_ema50_1h) / 5 if close_values_1h else 0.0,
            consecutive_closes_below_ema50=self._consecutive_closes_below_ema50(
                candles_15m,
                ema50,
            ),
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
        return ContextSnapshot.build(
            fetched_at=quote.observed_at,
            sources=(
                ContextSource(
                    url=_MARKET_SOURCE_URL,
                    title="Binance market data endpoints",
                    published_at=None,
                ),
            ),
            items=(
                ContextItem(
                    summary=(
                        f"Closed {candle.symbol} candle at {candle.close_time.isoformat()} "
                        f"with spread rate {float(quote.spread_rate):0.6f}; "
                        f"{'history is contiguous' if features.contiguous else 'history gap detected'}."
                    ),
                    driver="market-data",
                    direction="neutral",
                    severity="low" if features.quote_fresh else "medium",
                    published_at=quote.observed_at,
                    source_indexes=(0,),
                    contradictory=False,
                ),
            ),
            conflict_level="LOW",
        )

    @staticmethod
    def _aggregate_hourly_candles(candles_15m: list[Candle]) -> list[Candle]:
        hourly: list[Candle] = []
        for start in range(0, len(candles_15m) - 3, 4):
            batch = candles_15m[start : start + 4]
            if any(candle.timeframe != "15m" for candle in batch):
                continue
            hourly.append(
                Candle(
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
            )
        return hourly

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
        for previous, current in zip(candles, candles[1:], strict=True):
            if current.open_time - previous.open_time != expected_gap:
                return False
        return True

    def _persist_entry(self, fill: PaperFill) -> None:
        order_id = self._stable_id("order", fill.client_order_id)
        trade_id = self._stable_id("trade", fill.client_order_id)
        fill_id = self._stable_id("fill", fill.client_order_id)
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO orders(
                    id, mode, paper_account_id, client_order_id, side, quantity_text, status, created_at
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
                INSERT OR IGNORE INTO fills(id, order_id, price_text, quantity_text, fee_text, occurred_at)
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
                    id, mode, paper_account_id, client_order_id, side, quantity_text, status, created_at
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
                INSERT OR IGNORE INTO fills(id, order_id, price_text, quantity_text, fee_text, occurred_at)
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
                INSERT INTO equity_snapshots(id, paper_account_id, equity_text, cash_text, observed_at)
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
        action = "BUY" if outcome.fill is not None else "SELL" if outcome.closed_trade is not None else "HOLD"
        payload = {
            "symbol": candle.symbol,
            "timeframe": candle.timeframe,
            "candle_close_time": candle.close_time.isoformat(),
            "paper_account_id": self._paper_account_id,
            "spread_rate": float(quote.spread_rate),
            "state": self._state.value,
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
