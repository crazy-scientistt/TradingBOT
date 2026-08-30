"""Deterministic Autonomous entry planner. Never invents a price or protection."""

from __future__ import annotations

from decimal import Decimal

from goldguard.domain.defaults import SAFE_DEFAULT_V1
from goldguard.domain.enums import CandidateAction, OrderSide, PositionSide, ProductKind
from goldguard.domain.models import Candle
from goldguard.execution.models import MarketScope
from goldguard.services.execution_coordinator import EntryPlan
from goldguard.strategy.engine import StrategyEngine, StrategyFeatures
from goldguard.strategy.genome import StrategyGenome
from goldguard.strategy.indicators import atr_wilder, ema_series, median_volume_ratio, rsi_wilder
from goldguard.strategy.runtime import GenomeRuntime


class GenomeEntryPlanner:
    def __init__(
        self,
        books: dict[str, dict[str, list[Candle]]],
        cash: Decimal,
        genome_repo: object | None = None,
    ) -> None:
        self._books = books
        self._cash = cash
        self._engine = StrategyEngine(SAFE_DEFAULT_V1)
        self._runtime = GenomeRuntime()
        self._genome_repo = genome_repo
        self._open_symbols: set[str] = set()

    def set_cash(self, cash: Decimal) -> None:
        self._cash = cash

    def mark_open(self, symbol: str) -> None:
        self._open_symbols.add(symbol)

    def mark_flat(self, symbol: str) -> None:
        self._open_symbols.discard(symbol)

    def __call__(self, scope: MarketScope, candle: Candle) -> EntryPlan:
        if scope.product != ProductKind.SPOT:
            return EntryPlan(approved=False, reason="futures_out_of_qualification_universe")
        if self._open_symbols:
            return EntryPlan(approved=False, reason="MAX_POSITIONS")
        book = self._books.setdefault(candle.symbol, {"15m": [], "1h": []})
        series = book["15m"]
        if not series or series[-1].close_time != candle.close_time:
            series.append(candle)
        features = self._features(candle.symbol)
        if features is None:
            return EntryPlan(approved=False, reason="INSUFFICIENT_HISTORY")
        genome = None
        getter = getattr(self._genome_repo, "get_active_genome", None)
        if callable(getter):
            genome = getter()
        if isinstance(genome, StrategyGenome):
            result = self._runtime.evaluate(genome, features, has_position=False)
            stop_mult = float(genome.exit.stop_atr_multiple)
            reward = float(genome.exit.r_multiple_min)
        else:
            result = self._engine.evaluate(features, has_position=False)
            stop_mult = float(SAFE_DEFAULT_V1.stop_atr_multiple)
            reward = float(SAFE_DEFAULT_V1.reward_r_multiple)
        if result.action is not CandidateAction.ENTRY_CANDIDATE:
            return EntryPlan(
                approved=False,
                reason=result.reason_codes[0] if result.reason_codes else "HOLD",
            )
        stop_rate = max(
            features.atr_rate * stop_mult,
            float(SAFE_DEFAULT_V1.minimum_stop_rate),
        )
        stop_rate = min(stop_rate, float(SAFE_DEFAULT_V1.maximum_stop_rate))
        take_rate = stop_rate * reward
        entry = candle.close
        stop = entry * (Decimal("1") - Decimal(str(stop_rate)))
        take = entry * (Decimal("1") + Decimal(str(take_rate)))
        risk_cash = self._cash * SAFE_DEFAULT_V1.risk_per_trade
        distance = entry - stop
        if distance <= 0:
            return EntryPlan(approved=False, reason="STOP_DISTANCE_INVALID")
        quantity = (risk_cash / distance).quantize(Decimal("0.0001"))
        if quantity <= 0:
            return EntryPlan(approved=False, reason="QTY_TOO_SMALL")
        return EntryPlan(
            approved=True,
            reason="TREND_PULLBACK_RECOVERY",
            side=OrderSide.BUY,
            position_side=PositionSide.LONG,
            quantity=quantity,
            leverage=1,
            stop_loss_price=stop,
            take_profit_price=take,
        )

    def _features(self, symbol: str) -> StrategyFeatures | None:
        book = self._books.get(symbol) or {}
        c15 = book.get("15m") or []
        c1h = book.get("1h") or []
        if len(c15) < 50 or len(c1h) < 50:
            return None
        closes = [float(item.close) for item in c15]
        highs = [float(item.high) for item in c15]
        lows = [float(item.low) for item in c15]
        volumes = [float(item.volume) for item in c15]
        ema50 = ema_series(closes, 50)
        rsi = rsi_wilder(closes, 14)
        atr = atr_wilder(highs, lows, closes, 14)
        if rsi[-1] is None or atr[-1] is None:
            return None
        closes_1h = [float(item.close) for item in c1h]
        ema50_1h = ema_series(closes_1h, 50)[-1]
        ema200_1h = ema_series(closes_1h, 200)[-1]
        prior = ema_series(closes_1h, 50)[-5] if len(closes_1h) >= 5 else ema50_1h
        try:
            vol_ratio = median_volume_ratio(volumes[-20:], 20) if len(volumes) >= 20 else 0.0
        except ValueError:
            vol_ratio = 0.0
        streak = 0
        for close, avg in zip(closes, ema50, strict=True):
            streak = streak + 1 if close < avg else 0
        latest = c15[-1]
        prev = c15[-2]
        atr14 = atr[-1]
        return StrategyFeatures(
            previous_close=float(prev.close),
            latest_close=float(latest.close),
            ema20_15m=ema_series(closes, 20)[-1],
            ema50_15m=ema50[-1],
            previous_rsi14=rsi[-2] if rsi[-2] is not None else 50.0,
            rsi14=rsi[-1],
            atr14=atr14,
            atr_rate=atr14 / float(latest.close) if latest.close else 0.0,
            volume_ratio=vol_ratio,
            spread_rate=0.0004,
            latest_close_1h=closes_1h[-1],
            ema50_1h=ema50_1h,
            ema200_1h=ema200_1h,
            ema50_slope_1h=(ema50_1h - prior) / 5,
            consecutive_closes_below_ema50=streak,
            sufficient_history=True,
            contiguous=True,
            quote_fresh=True,
        )
