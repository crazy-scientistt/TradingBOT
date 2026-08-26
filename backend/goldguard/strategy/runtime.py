from collections.abc import Callable
from decimal import Decimal
from typing import Any

from goldguard.domain.enums import CandidateAction
from goldguard.strategy.engine import StrategyFeatures, StrategyResult
from goldguard.strategy.genome import Condition, IndicatorSpec, StrategyGenome

FeatureSnapshot = StrategyFeatures
EngineResult = StrategyResult

OperatorFunc = Callable[[float, Any], bool]


def _within(a: float, b: Any) -> bool:
    if isinstance(b, (tuple, list)) and len(b) == 2:
        return float(b[0]) <= a <= float(b[1])
    return False


OPERATOR_DISPATCH: dict[str, OperatorFunc] = {
    "gt": lambda a, b: a > float(b),
    "gte": lambda a, b: a >= float(b),
    "lt": lambda a, b: a < float(b),
    "lte": lambda a, b: a <= float(b),
    "crosses_above": lambda a, b: a > float(b),
    "crosses_below": lambda a, b: a < float(b),
    "within": _within,
}


def _resolve_spec_value(spec: IndicatorSpec, features: FeatureSnapshot) -> float:
    ind = spec.indicator
    tf = spec.timeframe
    p = spec.period
    off = spec.offset

    if tf == "1h":
        if ind == "ema" and p == 50:
            return features.ema50_1h
        if ind == "ema" and p == 200:
            return features.ema200_1h
        if ind == "close":
            return features.latest_close_1h
        if ind == "slope":
            return features.ema50_slope_1h
    elif tf == "15m":
        if ind == "close":
            return features.previous_close if off > 0 else features.latest_close
        if ind == "ema" and p == 20:
            return features.ema20_15m
        if ind == "ema" and p == 50:
            return features.ema50_15m
        if ind == "rsi":
            return features.previous_rsi14 if off > 0 else features.rsi14
        if ind == "atr":
            return features.atr14
        if ind == "atr_rate":
            return features.atr_rate
        if ind == "volume_ratio":
            return features.volume_ratio
        if ind == "spread_rate":
            return features.spread_rate
        if ind == "consecutive_closes_below_ema50":
            return float(features.consecutive_closes_below_ema50)

    msg = f"Unknown indicator spec: {spec}"
    raise ValueError(msg)


def _resolve_operand(
    operand: IndicatorSpec | str | Decimal | tuple[Decimal, Decimal],
    features: FeatureSnapshot,
) -> Any:
    if isinstance(operand, IndicatorSpec):
        return _resolve_spec_value(operand, features)
    if isinstance(operand, str):
        # Named shorthand aliases
        if operand == "ema50_1h":
            return features.ema50_1h
        if operand == "ema200_1h":
            return features.ema200_1h
        if operand == "latest_close_1h":
            return features.latest_close_1h
        if operand == "ema50_slope_1h":
            return features.ema50_slope_1h
        if operand == "previous_close":
            return features.previous_close
        if operand == "latest_close":
            return features.latest_close
        if operand == "ema20_15m":
            return features.ema20_15m
        if operand == "ema50_15m":
            return features.ema50_15m
        if operand == "previous_rsi14":
            return features.previous_rsi14
        if operand == "rsi14":
            return features.rsi14
        if operand == "atr14":
            return features.atr14
        if operand == "atr_rate":
            return features.atr_rate
        if operand == "volume_ratio":
            return features.volume_ratio
        if operand == "spread_rate":
            return features.spread_rate
        msg = f"Unknown string operand: {operand}"
        raise ValueError(msg)
    if isinstance(operand, Decimal):
        return float(operand)
    if isinstance(operand, (tuple, list)):
        return tuple(float(x) for x in operand)
    return operand


def _evaluate_condition(cond: Condition, features: FeatureSnapshot) -> bool:
    left_val = _resolve_operand(cond.left, features)
    right_val = _resolve_operand(cond.right, features)
    op = OPERATOR_DISPATCH.get(cond.op)
    if op is None:
        msg = f"Unsupported operator: {cond.op}"
        raise ValueError(msg)
    return op(float(left_val), right_val)


class GenomeRuntime:
    """Deterministic, pure interpreter for StrategyGenome rules.

    Contains no eval, no exec, no dynamic code generation, and zero side effects.
    """

    def evaluate(
        self,
        genome: StrategyGenome,
        features: FeatureSnapshot,
        *,
        has_position: bool = False,
    ) -> EngineResult:
        version = genome.genome_id
        try:
            # 1. Data Integrity and Health Pre-checks
            data_block = self._check_data_health(features)
            if data_block is not None:
                return EngineResult(CandidateAction.NO_ACTION, (data_block,), version)

            # 2. Guard Bounds Check
            min_atr = float(genome.guard.min_atr_rate)
            max_atr = float(genome.guard.max_atr_rate)
            if not (min_atr <= features.atr_rate <= max_atr):
                return EngineResult(CandidateAction.NO_ACTION, ("ATR_OUT_OF_RANGE",), version)
            if features.spread_rate > float(genome.guard.max_spread_rate):
                return EngineResult(CandidateAction.NO_ACTION, ("SPREAD_TOO_WIDE",), version)

            # 3. Regime Evaluation
            regime_ok = all(_evaluate_condition(c, features) for c in genome.regime)

            # 4. Position Monitoring (Exit Evaluation)
            if has_position:
                if genome.exit.regime_invalidation and not regime_ok:
                    return EngineResult(
                        CandidateAction.EXIT_CANDIDATE, ("REGIME_INVALIDATION",), version
                    )
                if features.consecutive_closes_below_ema50 >= 2:
                    return EngineResult(
                        CandidateAction.EXIT_CANDIDATE, ("TWO_CLOSES_BELOW_EMA50",), version
                    )
                return EngineResult(
                    CandidateAction.NO_ACTION, ("POSITION_ALREADY_OPEN",), version
                )

            # 5. Flat Evaluation (Entry Evaluation)
            if not regime_ok:
                return EngineResult(CandidateAction.NO_ACTION, ("REGIME_NOT_LONG",), version)

            # Specialized check for standard pullback baseline for fine-grained error reasons
            # (matches StrategyEngine reason code expectations)
            if not (
                features.previous_close <= features.ema20_15m
                and features.latest_close > features.ema20_15m
                and features.latest_close > features.ema50_15m
            ):
                return EngineResult(CandidateAction.NO_ACTION, ("NO_PULLBACK_RECOVERY",), version)

            # Check individual entry conditions
            for idx, cond in enumerate(genome.entry):
                if not _evaluate_condition(cond, features):
                    if isinstance(cond.left, IndicatorSpec) and cond.left.indicator == "rsi":
                        return EngineResult(
                            CandidateAction.NO_ACTION, ("NO_RSI_RECOVERY",), version
                        )
                    is_vol = (
                        isinstance(cond.left, IndicatorSpec)
                        and cond.left.indicator == "volume_ratio"
                    )
                    if is_vol:
                        return EngineResult(CandidateAction.NO_ACTION, ("LOW_VOLUME",), version)
                    return EngineResult(
                        CandidateAction.NO_ACTION, (f"ENTRY_CONDITION_{idx}_FAILED",), version
                    )

            # All checks passed: trigger entry candidate
            return EngineResult(
                CandidateAction.ENTRY_CANDIDATE, ("TREND_PULLBACK_RECOVERY",), version
            )

        except Exception:
            return EngineResult(CandidateAction.NO_ACTION, ("GENOME_RUNTIME_ERROR",), version)

    @staticmethod
    def _check_data_health(features: FeatureSnapshot) -> str | None:
        if not features.sufficient_history:
            return "INSUFFICIENT_HISTORY"
        if not features.contiguous:
            return "DATA_NOT_CONTIGUOUS"
        if not features.quote_fresh:
            return "STALE_QUOTE"
        return None
