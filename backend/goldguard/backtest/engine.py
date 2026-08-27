from __future__ import annotations

import hashlib
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
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
from goldguard.strategy.indicators import (
    atr_wilder,
    ema_series,
    median_volume_ratio,
    rsi_wilder,
)
from goldguard.strategy.runtime import GenomeRuntime


@dataclass(frozen=True)
class FrictionConfig:
    commission_rate: Decimal = Decimal("0.001")  # 0.1% taker fee
    slippage_rate: Decimal = Decimal("0.0002")  # 2 bps slippage
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


@dataclass(frozen=True)
class _IndicatorSeries:
    """Every indicator the strategy reads, computed once per series and indexed by bar."""

    ema20_15m: list[float]
    ema50_15m: list[float]
    rsi14: list[float | None]
    atr14: list[float | None]
    volumes: list[float]
    below_ema50: list[int]
    contiguous: list[bool]
    closes_1h: list[float]
    ema50_1h: list[float]
    ema200_1h: list[float]
    # For each 15m bar, the index of the newest 1h bar that had already closed, or None.
    hour_index: list[int | None]

    @classmethod
    def build(
        cls,
        candles_15m: Sequence[Candle],
        candles_1h: Sequence[Candle] | None,
    ) -> _IndicatorSeries:
        closes = [float(candle.close) for candle in candles_15m]
        highs = [float(candle.high) for candle in candles_15m]
        lows = [float(candle.low) for candle in candles_15m]
        volumes = [float(candle.volume) for candle in candles_15m]
        ema50_15m = ema_series(closes, 50)

        below: list[int] = []
        streak = 0
        for close, average in zip(closes, ema50_15m, strict=True):
            streak = streak + 1 if close < average else 0
            below.append(streak)

        gap = timedelta(minutes=15)
        contiguous: list[bool] = []
        run = 1
        for position, candle in enumerate(candles_15m):
            if position and candle.close_time - candles_15m[position - 1].close_time == gap:
                run += 1
            elif position:
                run = 1
            contiguous.append(run >= min(position + 1, 50))

        hourly = list(candles_1h or ())
        closes_1h = [float(candle.close) for candle in hourly]
        hour_closes = [candle.close_time for candle in hourly]
        hour_index: list[int | None] = []
        for candle in candles_15m:
            position = bisect_right(hour_closes, candle.close_time) - 1
            hour_index.append(position if position >= 0 else None)

        return cls(
            ema20_15m=ema_series(closes, 20),
            ema50_15m=ema50_15m,
            rsi14=rsi_wilder(closes, 14),
            atr14=atr_wilder(highs, lows, closes, 14),
            volumes=volumes,
            below_ema50=below,
            contiguous=contiguous,
            closes_1h=closes_1h,
            ema50_1h=ema_series(closes_1h, 50),
            ema200_1h=ema_series(closes_1h, 200),
            hour_index=hour_index,
        )


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

        # Indicators are computed once over the whole series instead of per bar: the
        # per-bar recomputation this replaces was O(n^2) and was seeded from a truncated
        # tail, so warm-up values disagreed with the live runtime's.
        series = _IndicatorSeries.build(candles, candles_1h)

        for idx in range(25, len(candles)):
            curr_candle = candles[idx]

            features = self._extract_features(candles, idx, series)

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
        index: int,
        series: _IndicatorSeries,
    ) -> StrategyFeatures:
        """Features as of the close of ``candles_15m[index]``, mirroring the live runtime."""
        latest = candles_15m[index]
        prev = candles_15m[index - 1] if index > 0 else latest
        latest_close = float(latest.close)

        atr14 = series.atr14[index]
        if atr14 is None:
            atr14 = float(latest.high - latest.low)
        rsi14 = series.rsi14[index]
        previous_rsi14 = series.rsi14[index - 1] if index > 0 else None

        hour = series.hour_index[index]
        if hour is None:
            # No 1h bar has closed yet: report the 15m close for both averages so the
            # regime filter sees a flat trend and holds instead of inventing one.
            latest_close_1h = latest_close
            ema50_1h = latest_close
            ema200_1h = latest_close
            ema50_slope_1h = 0.0
        else:
            latest_close_1h = series.closes_1h[hour]
            ema50_1h = series.ema50_1h[hour]
            ema200_1h = series.ema200_1h[hour]
            prior = series.ema50_1h[hour - 5] if hour >= 5 else ema50_1h
            ema50_slope_1h = (ema50_1h - prior) / 5

        return StrategyFeatures(
            previous_close=float(prev.close),
            latest_close=latest_close,
            ema20_15m=series.ema20_15m[index],
            ema50_15m=series.ema50_15m[index],
            previous_rsi14=previous_rsi14 if previous_rsi14 is not None else 50.0,
            rsi14=rsi14 if rsi14 is not None else 50.0,
            atr14=atr14,
            atr_rate=atr14 / latest_close if latest_close > 0 else 0.0,
            volume_ratio=(
                median_volume_ratio(series.volumes[index - 19 : index + 1], 20)
                if index >= 19
                else 0.0
            ),
            # Backtests replay closed candles, so the only friction that exists is the
            # configured half-spread; there is no historical order book to read.
            spread_rate=float(self.friction.half_spread_rate * 2),
            latest_close_1h=latest_close_1h,
            ema50_1h=ema50_1h,
            ema200_1h=ema200_1h,
            ema50_slope_1h=ema50_slope_1h,
            consecutive_closes_below_ema50=series.below_ema50[index],
            sufficient_history=index >= 49 and hour is not None and hour >= 49,
            contiguous=series.contiguous[index],
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
