from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from goldguard.ai.gemini import AiAssessment, DecisionRequest
from goldguard.broker.base import Broker, ClosedPaperTrade, PaperFill
from goldguard.context.models import ContextSnapshot
from goldguard.context.playbook import ChecklistInputs, ChecklistResult
from goldguard.domain.enums import AiDecision, CandidateAction, ChecklistAction, ExitReason
from goldguard.domain.models import Quote, TradePlan
from goldguard.market.binance import SymbolFilters
from goldguard.risk.engine import RiskContext, RiskDecision, RiskEngine
from goldguard.storage.repositories import GenomeRepository, LedgerRepository
from goldguard.strategy.genome import StrategyGenome, genome_hash, trend_pullback_v1
from goldguard.strategy.runtime import FeatureSnapshot, GenomeRuntime


@dataclass(frozen=True)
class DecisionOutcome:
    executed: bool
    action: str
    reason_codes: tuple[str, ...]
    decision_chain_id: str | None = None
    plan: TradePlan | None = None
    fill: PaperFill | None = None
    closed_trade: ClosedPaperTrade | None = None
    ai_assessment: AiAssessment | None = None
    risk_decision: RiskDecision | None = None


@dataclass(frozen=True)
class ExitOutcome:
    closed_trade: ClosedPaperTrade | None = None
    reason: str = ""


class ChecklistGate(Protocol):
    def evaluate(self, inputs: ChecklistInputs) -> ChecklistResult: ...


class AiVetoGate(Protocol):
    def decide(self, request: DecisionRequest) -> AiAssessment: ...


class TradingCoordinator:
    """Durable coordinator owning the full candidate → context → veto → risk → fill pipeline.

    Enforces idempotent closed-candle scanning, fail-closed entry evaluation,
    and instantaneous fail-open position protection without AI/network latency.
    """

    def __init__(
        self,
        *,
        broker: Broker,
        genome_repo: GenomeRepository,
        ledger_repo: LedgerRepository,
        runtime: GenomeRuntime,
        risk_engine: RiskEngine,
        checklist: ChecklistGate | None,
        ai_veto: AiVetoGate | None,
        filters: SymbolFilters | None,
        lease_name: str = "coordinator_worker",
    ) -> None:
        self.broker = broker
        self.genome_repo = genome_repo
        self.ledger_repo = ledger_repo
        self.runtime = runtime
        self.risk_engine = risk_engine
        self.checklist = checklist
        self.ai_veto = ai_veto
        self.filters = filters
        self.lease_name = lease_name
        self._processed_candles: set[str] = set()

    def scan_closed_candle(
        self,
        *,
        symbol: str,
        closed_at: datetime,
        quote: Quote,
        features: FeatureSnapshot,
        context_snapshot: ContextSnapshot | None = None,
        memory_summaries: tuple[dict[str, object], ...] = (),
        account_scope: str = "default_paper",
    ) -> DecisionOutcome:
        candle_key = f"{symbol}:{closed_at.isoformat()}"
        if candle_key in self._processed_candles and self.broker.position is not None:
            return DecisionOutcome(False, "POSITION_ALREADY_OPEN", ("POSITION_ALREADY_OPEN",))
        if candle_key in self._processed_candles:
            return DecisionOutcome(False, "ALREADY_PROCESSED", ("IDEMPOTENT_SKIP",))

        # Record idempotent decision chain in ledger
        decision_chain_id = self.ledger_repo.record_decision_chain(
            mode="paper",
            account_scope=account_scope,
            symbol=symbol,
            timeframe="15m",
            candle_close_time=closed_at.isoformat(),
        )

        active_genome: StrategyGenome = self.genome_repo.get_active_genome() or trend_pullback_v1()
        current_g_hash = genome_hash(active_genome)

        # Case 1: Open position monitoring on closed candle
        if self.broker.position is not None:
            eval_result = self.runtime.evaluate(active_genome, features, has_position=True)
            if eval_result.action is CandidateAction.EXIT_CANDIDATE:
                exit_reason = (
                    ExitReason.REGIME_INVALIDATION
                    if "REGIME_INVALIDATION" in eval_result.reason_codes
                    else ExitReason.AI_RISK_REDUCTION
                )
                closed_trade = self.broker.exit_long(
                    quote,
                    client_order_id=f"exit-{int(closed_at.timestamp())}",
                    reason=exit_reason,
                )
                self._processed_candles.add(candle_key)
                return DecisionOutcome(
                    True,
                    "EXIT_TRIGGERED",
                    eval_result.reason_codes,
                    decision_chain_id=decision_chain_id,
                    closed_trade=closed_trade,
                )

            self._processed_candles.add(candle_key)
            return DecisionOutcome(False, "POSITION_ALREADY_OPEN", ("POSITION_ALREADY_OPEN",))

        # Case 2: Flat position — evaluate entry candidate
        eval_result = self.runtime.evaluate(active_genome, features, has_position=False)
        if eval_result.action is not CandidateAction.ENTRY_CANDIDATE:
            self._processed_candles.add(candle_key)
            return DecisionOutcome(
                False,
                "NO_ACTION",
                eval_result.reason_codes,
                decision_chain_id=decision_chain_id,
            )

        # Evidence & Professional Checklist Gate
        if self.checklist is not None:
            if context_snapshot is None:
                raise ValueError("context_snapshot is required when checklist gate is enabled")
            checklist_result = self.checklist.evaluate(
                ChecklistInputs(
                    context=context_snapshot,
                    now=quote.observed_at,
                    data_healthy=features.sufficient_history
                    and features.contiguous
                    and features.quote_fresh,
                    exchange_normal=True,
                    liquidity_acceptable=features.spread_rate <= 0.0015,
                    regime_clear=True,
                    deterministic_setup=True,
                    complete_trade_plan=True,
                    risk_budget_available=True,
                    cooldown_clear=True,
                    event_blackout=False,
                )
            )
            if checklist_result.action is not ChecklistAction.PASS:
                self._processed_candles.add(candle_key)
                return DecisionOutcome(
                    False,
                    "CHECKLIST_HELD",
                    checklist_result.reason_codes,
                    decision_chain_id=decision_chain_id,
                )

        # AI Veto Gate
        ai_assessment: AiAssessment | None = None
        if self.ai_veto is not None:
            ai_assessment = self.ai_veto.decide(
                DecisionRequest(
                    candidate=eval_result.action,
                    strategy_version=active_genome.genome_id,
                    features={
                        "previous_close": features.previous_close,
                        "latest_close": features.latest_close,
                        "ema20_15m": features.ema20_15m,
                        "ema50_15m": features.ema50_15m,
                        "previous_rsi14": features.previous_rsi14,
                        "rsi14": features.rsi14,
                        "atr14": features.atr14,
                        "atr_rate": features.atr_rate,
                        "volume_ratio": features.volume_ratio,
                        "spread_rate": features.spread_rate,
                        "latest_close_1h": features.latest_close_1h,
                        "ema50_1h": features.ema50_1h,
                        "ema200_1h": features.ema200_1h,
                        "ema50_slope_1h": features.ema50_slope_1h,
                        "consecutive_closes_below_ema50": features.consecutive_closes_below_ema50,
                        "sufficient_history": features.sufficient_history,
                        "contiguous": features.contiguous,
                        "quote_fresh": features.quote_fresh,
                    },
                    context={
                        "content_hash": context_snapshot.content_hash if context_snapshot else "",
                        "conflict_level": context_snapshot.conflict_level
                        if context_snapshot
                        else "UNKNOWN",
                        "source_count": len(context_snapshot.sources) if context_snapshot else 0,
                        "item_count": len(context_snapshot.items) if context_snapshot else 0,
                    },
                    memory_summaries=memory_summaries,
                )
            )
            if ai_assessment.decision is not AiDecision.APPROVE_ENTRY:
                self._processed_candles.add(candle_key)
                return DecisionOutcome(
                    False,
                    "AI_VETO_REJECTED",
                    ai_assessment.reason_codes,
                    decision_chain_id=decision_chain_id,
                    ai_assessment=ai_assessment,
                )

        if self.filters is None:
            self._processed_candles.add(candle_key)
            return DecisionOutcome(
                False,
                "MARKET_FILTERS_UNAVAILABLE",
                ("MARKET_FILTERS_UNAVAILABLE",),
                decision_chain_id=decision_chain_id,
                ai_assessment=ai_assessment,
            )

        # Deterministic Risk Sizing Gate
        risk_context = RiskContext(
            equity=self.broker.cash,
            available_cash=self.broker.cash,
            entry=quote.ask,
            atr=Decimal(str(features.atr14)),
            fee_rate=Decimal("0.001"),
            filters=self.filters,
            rolling_24h_loss_rate=Decimal("0"),
            peak_drawdown_rate=Decimal("0"),
            consecutive_losses=0,
            minutes_since_exit=120,
            open_positions=1 if self.broker.position is not None else 0,
            data_healthy=features.sufficient_history and features.contiguous,
            spread_acceptable=features.spread_rate <= 0.0015,
            event_blackout=False,
            lease_owned=True,
            promotion_churn=0,
            quota_exhausted=False,
            gateway_degraded=False,
            genome_status="active",
            genome_hash=current_g_hash,
        )

        risk_decision: RiskDecision = self.risk_engine.plan_entry(risk_context)
        if not risk_decision.approved or risk_decision.plan is None:
            self._processed_candles.add(candle_key)
            return DecisionOutcome(
                False,
                "RISK_REJECTED",
                risk_decision.reason_codes,
                decision_chain_id=decision_chain_id,
                ai_assessment=ai_assessment,
                risk_decision=risk_decision,
            )

        # Execute entry fill on broker
        fill = self.broker.open_long(
            risk_decision.plan,
            quote,
            client_order_id=f"entry-{int(closed_at.timestamp())}",
        )
        self._processed_candles.add(candle_key)
        return DecisionOutcome(
            True,
            "ENTRY_FILLED",
            ("PAPER_ENTRY_FILLED",),
            decision_chain_id=decision_chain_id,
            plan=risk_decision.plan,
            fill=fill,
            ai_assessment=ai_assessment,
            risk_decision=risk_decision,
        )

    def monitor_open_position(self, quote: Quote) -> ExitOutcome | None:
        """Instantaneous deterministic protection path.

        Evaluates stop loss and take profit triggers directly against current quote.
        Never calls AI, web search, or the gateway.
        """
        position = self.broker.position
        if position is None:
            return None

        # Check Stop Loss
        if quote.bid <= position.plan.stop:
            closed = self.broker.exit_long(
                quote,
                client_order_id=f"sl-{int(quote.observed_at.timestamp())}",
                reason=ExitReason.STOP_LOSS,
            )
            return ExitOutcome(closed_trade=closed, reason="STOP_LOSS_TRIGGERED")

        # Check Take Profit
        if quote.bid >= position.plan.target:
            closed = self.broker.exit_long(
                quote,
                client_order_id=f"tp-{int(quote.observed_at.timestamp())}",
                reason=ExitReason.TAKE_PROFIT,
            )
            return ExitOutcome(closed_trade=closed, reason="TAKE_PROFIT_TRIGGERED")

        return None
