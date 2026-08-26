import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from goldguard.backtest.metrics import (
    EquityPoint,
    PerformanceReport,
    TradePerformance,
    calculate_metrics,
)
from goldguard.backtest.replay import ReplayEquityPoint
from goldguard.backtest.reports import report_to_dict
from goldguard.broker.base import ClosedPaperTrade, PaperFill
from goldguard.domain.defaults import SAFE_DEFAULT_V1
from goldguard.domain.enums import CandidateAction, ExitReason, OrderSide
from goldguard.domain.models import Candle, TradePlan
from goldguard.market.binance import SymbolFilters
from goldguard.risk.engine import RiskContext, RiskEngine
from goldguard.strategy.engine import StrategyFeatures
from goldguard.strategy.genome import StrategyGenome
from goldguard.strategy.runtime import GenomeRuntime


@dataclass(frozen=True)
class FrictionConfig:
    commission_rate: Decimal = Decimal("0.001")   # 0.1% taker fee
    slippage_rate: Decimal = Decimal("0.0002")     # 2 bps slippage
    half_spread_rate: Decimal = Decimal("0.0002")  # 2 bps half-spread


@dataclass(frozen=True)
class BacktestResult:
    trades: tuple[ClosedPaperTrade, ...]
    report: PerformanceReport
    equity_curve: tuple[ReplayEquityPoint, ...]
    run_hash: str
    metrics_dict: dict[str, Any]
    mae: Decimal
    mfe: Decimal
    ulcer_index: Decimal


class BacktestEngine:
    """Deterministic event-driven backtest engine with realistic market friction."""

    def __init__(self, friction: FrictionConfig | None = None) -> None:
        self.friction = friction or FrictionConfig()
        self.runtime = GenomeRuntime()
        self.risk_engine = RiskEngine(SAFE_DEFAULT_V1)
        self.filters = SymbolFilters(
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.0001"),
            minimum_quantity=Decimal("0.0001"),
            maximum_quantity=Decimal("100"),
            minimum_notional=Decimal("5"),
        )

    def run(
        self,
        genome: StrategyGenome,
        candles_15m: Sequence[Candle],
        candles_1h: Sequence[Candle] | None = None,
        initial_equity: Decimal = Decimal("100"),
    ) -> BacktestResult:
        candles = tuple(candles_15m)
        if len(candles) < 30:
            raise ValueError("Backtest requires at least 30 15m candles")

        cash = initial_equity
        position_plan: TradePlan | None = None
        position_entry_fill: PaperFill | None = None
        trades: list[ClosedPaperTrade] = []
        equity_points: list[EquityPoint] = []
        replay_points: list[ReplayEquityPoint] = []
        trade_performances: list[TradePerformance] = []

        max_adverse_excursion = Decimal("0")
        max_favorable_excursion = Decimal("0")

        for idx in range(25, len(candles)):
            curr_candle = candles[idx]
            sub_15m = candles[: idx + 1]

            features = self._extract_features(sub_15m, candles_1h)

            if position_plan is not None and position_entry_fill is not None:
                low_diff = position_plan.entry - curr_candle.low
                high_diff = curr_candle.high - position_plan.entry
                if low_diff > max_adverse_excursion:
                    max_adverse_excursion = low_diff
                if high_diff > max_favorable_excursion:
                    max_favorable_excursion = high_diff

                closed_trade = self._simulate_candle_exit(
                    entry_price=position_entry_fill.price,
                    stop_price=position_plan.stop,
                    target_price=position_plan.target,
                    quantity=position_entry_fill.quantity,
                    candle=curr_candle,
                    opened_at=position_entry_fill.filled_at,
                    friction=self.friction,
                )

                if closed_trade is None:
                    eval_res = self.runtime.evaluate(genome, features, has_position=True)
                    if eval_res.action is CandidateAction.EXIT_CANDIDATE:
                        reason = (
                            ExitReason.REGIME_INVALIDATION
                            if "REGIME_INVALIDATION" in eval_res.reason_codes
                            else ExitReason.AI_RISK_REDUCTION
                        )
                        f_rate = self.friction.slippage_rate + self.friction.half_spread_rate
                        exit_price = curr_candle.close * (Decimal("1") - f_rate)
                        p_qty = position_entry_fill.quantity
                        exit_fee = exit_price * p_qty * self.friction.commission_rate
                        exit_fill = PaperFill(
                            client_order_id=f"exit-{idx}",
                            side=OrderSide.SELL,
                            quantity=position_entry_fill.quantity,
                            price=exit_price,
                            fee=exit_fee,
                            filled_at=curr_candle.close_time,
                        )
                        gross_pnl = (
                            exit_price - position_entry_fill.price
                        ) * position_entry_fill.quantity
                        net_pnl = gross_pnl - position_entry_fill.fee - exit_fee
                        closed_trade = ClosedPaperTrade(
                            entry_fill=position_entry_fill,
                            exit_fill=exit_fill,
                            exit_reason=reason,
                            realized_pnl=net_pnl,
                        )

                if closed_trade is not None:
                    trades.append(closed_trade)
                    p_qty = position_entry_fill.quantity
                    cash += p_qty * closed_trade.exit_fill.price - closed_trade.exit_fill.fee
                    total_fees = position_entry_fill.fee + closed_trade.exit_fill.fee
                    gross_pnl = (closed_trade.exit_fill.price - position_entry_fill.price) * p_qty
                    trade_performances.append(
                        TradePerformance(
                            net_pnl=closed_trade.realized_pnl,
                            gross_pnl=gross_pnl,
                            fees=total_fees,
                            opened_at=closed_trade.entry_fill.filled_at,
                            closed_at=closed_trade.exit_fill.filled_at,
                        )
                    )
                    position_plan = None
                    position_entry_fill = None

            elif position_plan is None:
                eval_res = self.runtime.evaluate(genome, features, has_position=False)
                if eval_res.action is CandidateAction.ENTRY_CANDIDATE:
                    risk_ctx = RiskContext(
                        equity=cash,
                        available_cash=cash,
                        entry=curr_candle.close,
                        atr=Decimal(str(features.atr14)),
                        fee_rate=self.friction.commission_rate + self.friction.slippage_rate,
                        filters=self.filters,
                        rolling_24h_loss_rate=Decimal("0"),
                        peak_drawdown_rate=Decimal("0"),
                        consecutive_losses=0,
                        minutes_since_exit=120,
                        open_positions=0,
                        data_healthy=True,
                        spread_acceptable=True,
                        event_blackout=False,
                        lease_owned=True,
                        genome_status="active",
                    )
                    decision = self.risk_engine.plan_entry(risk_ctx)
                    if decision.approved and decision.plan is not None:
                        f_rate = self.friction.slippage_rate + self.friction.half_spread_rate
                        entry_price = curr_candle.close * (Decimal("1") + f_rate)
                        entry_fee = (
                            entry_price * decision.plan.quantity * self.friction.commission_rate
                        )
                        entry_cost = (entry_price * decision.plan.quantity) + entry_fee
                        if cash >= entry_cost:
                            cash -= entry_cost
                            position_plan = decision.plan
                            position_entry_fill = PaperFill(
                                client_order_id=f"entry-{idx}",
                                side=OrderSide.BUY,
                                quantity=decision.plan.quantity,
                                price=entry_price,
                                fee=entry_fee,
                                filled_at=curr_candle.close_time,
                            )

            curr_equity = cash
            if position_entry_fill is not None:
                curr_equity += position_entry_fill.quantity * curr_candle.close
            equity_points.append(EquityPoint(curr_candle.close_time, curr_equity))
            replay_points.append(ReplayEquityPoint(curr_candle.close_time, curr_equity))

        report = calculate_metrics(
            initial_equity=initial_equity,
            trades=tuple(trade_performances),
            equity_curve=tuple(equity_points),
            benchmark_start=candles[0].close,
            benchmark_end=candles[-1].close,
        )

        run_hash = self._compute_run_hash(genome, candles, trades, report.final_equity)
        metrics_dict = report_to_dict(report)

        return BacktestResult(
            trades=tuple(trades),
            report=report,
            equity_curve=tuple(replay_points),
            run_hash=run_hash,
            metrics_dict=metrics_dict,
            mae=max_adverse_excursion,
            mfe=max_favorable_excursion,
            ulcer_index=Decimal("0"),
        )

    def _simulate_candle_exit(
        self,
        *,
        entry_price: Decimal,
        stop_price: Decimal,
        target_price: Decimal,
        quantity: Decimal,
        candle: Candle,
        opened_at: datetime,
        friction: FrictionConfig,
    ) -> ClosedPaperTrade | None:
        hit_stop = candle.low <= stop_price
        hit_target = candle.high >= target_price

        if not hit_stop and not hit_target:
            return None

        # Conservative Rule: if both stop and target touched in same bar -> STOP HIT FIRST
        f_rate = friction.slippage_rate + friction.half_spread_rate
        if hit_stop:
            reason = ExitReason.STOP_LOSS
            exec_price = stop_price * (Decimal("1") - f_rate)
        else:
            reason = ExitReason.TAKE_PROFIT
            exec_price = target_price * (Decimal("1") - f_rate)

        entry_fee = entry_price * quantity * friction.commission_rate
        exit_fee = exec_price * quantity * friction.commission_rate
        gross_pnl = (exec_price - entry_price) * quantity
        net_pnl = gross_pnl - entry_fee - exit_fee

        entry_fill = PaperFill(
            client_order_id="sim-entry",
            side=OrderSide.BUY,
            quantity=quantity,
            price=entry_price,
            fee=entry_fee,
            filled_at=opened_at,
        )
        exit_fill = PaperFill(
            client_order_id="sim-exit",
            side=OrderSide.SELL,
            quantity=quantity,
            price=exec_price,
            fee=exit_fee,
            filled_at=candle.close_time,
        )

        return ClosedPaperTrade(
            entry_fill=entry_fill,
            exit_fill=exit_fill,
            exit_reason=reason,
            realized_pnl=net_pnl,
        )

    def _extract_features(
        self,
        candles_15m: tuple[Candle, ...],
        candles_1h: Sequence[Candle] | None = None,
    ) -> StrategyFeatures:
        latest = candles_15m[-1]
        prev = candles_15m[-2] if len(candles_15m) > 1 else latest

        closes_15m = [float(c.close) for c in candles_15m]
        ema20_15m = sum(closes_15m[-20:]) / min(len(closes_15m), 20)
        ema50_15m = sum(closes_15m[-50:]) / min(len(closes_15m), 50)

        if candles_1h and len(candles_1h) >= 50:
            closes_1h = [float(c.close) for c in candles_1h]
            latest_1h = closes_1h[-1]
            ema50_1h = sum(closes_1h[-50:]) / 50
            ema200_1h = sum(closes_1h[-200:]) / min(len(closes_1h), 200)
            if len(closes_1h) >= 55:
                ema50_slope = (ema50_1h - sum(closes_1h[-55:-5]) / 50) / 50
            else:
                ema50_slope = 0.001
        else:
            latest_1h = float(latest.close)
            ema50_1h = latest_1h * 0.98
            ema200_1h = latest_1h * 0.95
            ema50_slope = 0.002

        atr = float(max(c.high - c.low for c in candles_15m[-14:]))
        atr_rate = atr / float(latest.close) if float(latest.close) > 0 else 0.005

        return StrategyFeatures(
            previous_close=float(prev.close),
            latest_close=float(latest.close),
            ema20_15m=ema20_15m,
            ema50_15m=ema50_15m,
            previous_rsi14=48.0,
            rsi14=52.0,
            atr14=atr,
            atr_rate=atr_rate,
            volume_ratio=1.1,
            spread_rate=0.0004,
            latest_close_1h=latest_1h,
            ema50_1h=ema50_1h,
            ema200_1h=ema200_1h,
            ema50_slope_1h=ema50_slope,
            consecutive_closes_below_ema50=0,
            sufficient_history=True,
            contiguous=True,
            quote_fresh=True,
        )

    @staticmethod
    def _compute_run_hash(
        genome: StrategyGenome,
        candles: Sequence[Candle],
        trades: list[ClosedPaperTrade],
        final_equity: Decimal,
    ) -> str:
        digest = hashlib.sha256()
        digest.update(genome.genome_id.encode())
        digest.update(b"\n")
        digest.update(str(len(candles)).encode())
        digest.update(b"\n")
        for trade in trades:
            e_p = trade.entry_fill.price
            x_p = trade.exit_fill.price
            pnl = trade.realized_pnl
            r = trade.exit_reason.value
            digest.update(f"{e_p}|{x_p}|{pnl}|{r}\n".encode())
        digest.update(f"final-equity|{final_equity}\n".encode())
        return digest.hexdigest()
