from dataclasses import dataclass

from goldguard.domain.defaults import StrategySettings
from goldguard.domain.enums import CandidateAction


@dataclass(frozen=True)
class StrategyFeatures:
    previous_close: float
    latest_close: float
    ema20_15m: float
    ema50_15m: float
    previous_rsi14: float
    rsi14: float
    atr14: float
    atr_rate: float
    volume_ratio: float
    spread_rate: float
    latest_close_1h: float
    ema50_1h: float
    ema200_1h: float
    ema50_slope_1h: float
    consecutive_closes_below_ema50: int
    sufficient_history: bool
    contiguous: bool
    quote_fresh: bool


@dataclass(frozen=True)
class StrategyResult:
    action: CandidateAction
    reason_codes: tuple[str, ...]
    strategy_version: str = "strategy-v1"


class StrategyEngine:
    def __init__(self, settings: StrategySettings) -> None:
        self.settings = settings

    def evaluate(self, features: StrategyFeatures, *, has_position: bool) -> StrategyResult:
        data_block = self._data_block(features)
        if data_block is not None:
            return StrategyResult(CandidateAction.NO_ACTION, (data_block,))

        long_regime = (
            features.ema50_1h > features.ema200_1h
            and features.latest_close_1h > features.ema200_1h
            and features.ema50_slope_1h > 0
        )
        if has_position:
            if not long_regime:
                return StrategyResult(
                    CandidateAction.EXIT_CANDIDATE,
                    ("REGIME_INVALIDATION",),
                )
            if features.consecutive_closes_below_ema50 >= 2:
                return StrategyResult(
                    CandidateAction.EXIT_CANDIDATE,
                    ("TWO_CLOSES_BELOW_EMA50",),
                )
            return StrategyResult(CandidateAction.NO_ACTION, ("POSITION_ALREADY_OPEN",))

        if not long_regime:
            return StrategyResult(CandidateAction.NO_ACTION, ("REGIME_NOT_LONG",))
        if not (
            features.previous_close <= features.ema20_15m
            and features.latest_close > features.ema20_15m
            and features.latest_close > features.ema50_15m
        ):
            return StrategyResult(CandidateAction.NO_ACTION, ("NO_PULLBACK_RECOVERY",))
        if not (
            features.previous_rsi14 < float(self.settings.rsi_recovery)
            and features.rsi14 >= float(self.settings.rsi_recovery)
            and features.rsi14 < float(self.settings.rsi_ceiling)
        ):
            return StrategyResult(CandidateAction.NO_ACTION, ("NO_RSI_RECOVERY",))
        if features.volume_ratio < float(self.settings.minimum_volume_ratio):
            return StrategyResult(CandidateAction.NO_ACTION, ("LOW_VOLUME",))
        if not (
            float(self.settings.minimum_atr_rate)
            <= features.atr_rate
            <= float(self.settings.maximum_atr_rate)
        ):
            return StrategyResult(CandidateAction.NO_ACTION, ("ATR_OUT_OF_RANGE",))
        if features.spread_rate > float(self.settings.maximum_spread_rate):
            return StrategyResult(CandidateAction.NO_ACTION, ("SPREAD_TOO_WIDE",))
        stop_rate = max(
            features.atr_rate * float(self.settings.stop_atr_multiple),
            float(self.settings.minimum_stop_rate),
        )
        round_trip = 0.0024  # 2× taker 0.001 + 2× slip 0.0002; spread is gated above
        if stop_rate <= 0 or round_trip > 0.35 * stop_rate:
            return StrategyResult(CandidateAction.NO_ACTION, ("COST_EDGE",))
        return StrategyResult(
            CandidateAction.ENTRY_CANDIDATE,
            ("TREND_PULLBACK_RECOVERY",),
        )

    @staticmethod
    def _data_block(features: StrategyFeatures) -> str | None:
        if not features.sufficient_history:
            return "INSUFFICIENT_HISTORY"
        if not features.contiguous:
            return "DATA_NOT_CONTIGUOUS"
        if not features.quote_fresh:
            return "STALE_QUOTE"
        return None
