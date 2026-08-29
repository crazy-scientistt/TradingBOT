from dataclasses import replace

import pytest
from goldguard.domain.defaults import SAFE_DEFAULT_V1
from goldguard.domain.enums import CandidateAction
from goldguard.strategy.engine import StrategyEngine, StrategyFeatures


def valid_features() -> StrategyFeatures:
    return StrategyFeatures(
        previous_close=2498.0,
        latest_close=2504.0,
        ema20_15m=2500.0,
        ema50_15m=2488.0,
        previous_rsi14=44.0,
        rsi14=50.0,
        atr14=12.0,
        atr_rate=0.0048,
        volume_ratio=1.1,
        spread_rate=0.0004,
        latest_close_1h=2502.0,
        ema50_1h=2475.0,
        ema200_1h=2400.0,
        ema50_slope_1h=0.002,
        consecutive_closes_below_ema50=0,
        sufficient_history=True,
        contiguous=True,
        quote_fresh=True,
    )


def test_all_conditions_produce_one_entry_candidate() -> None:
    result = StrategyEngine(SAFE_DEFAULT_V1).evaluate(valid_features(), has_position=False)

    assert result.action is CandidateAction.ENTRY_CANDIDATE
    assert result.reason_codes == ("TREND_PULLBACK_RECOVERY",)
    assert result.strategy_version == "strategy-v1"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("ema50_1h", 2390.0, "REGIME_NOT_LONG"),
        ("latest_close_1h", 2390.0, "REGIME_NOT_LONG"),
        ("ema50_slope_1h", 0.0, "REGIME_NOT_LONG"),
        ("previous_close", 2501.0, "NO_PULLBACK_RECOVERY"),
        ("latest_close", 2499.0, "NO_PULLBACK_RECOVERY"),
        ("previous_rsi14", 45.0, "NO_RSI_RECOVERY"),
        ("rsi14", 68.0, "NO_RSI_RECOVERY"),
        ("volume_ratio", 0.79, "LOW_VOLUME"),
        ("atr_rate", 0.0004, "ATR_OUT_OF_RANGE"),
        ("atr_rate", 0.016, "ATR_OUT_OF_RANGE"),
        ("spread_rate", 0.0016, "SPREAD_TOO_WIDE"),
        ("atr_rate", 0.0006, "COST_EDGE"),
        ("sufficient_history", False, "INSUFFICIENT_HISTORY"),
        ("contiguous", False, "DATA_NOT_CONTIGUOUS"),
        ("quote_fresh", False, "STALE_QUOTE"),
    ],
)
def test_each_missing_condition_produces_no_action(field: str, value: object, reason: str) -> None:
    result = StrategyEngine(SAFE_DEFAULT_V1).evaluate(
        replace(valid_features(), **{field: value}),
        has_position=False,
    )

    assert result.action is CandidateAction.NO_ACTION
    assert reason in result.reason_codes


def test_open_position_exits_on_regime_invalidation() -> None:
    result = StrategyEngine(SAFE_DEFAULT_V1).evaluate(
        replace(valid_features(), ema50_1h=2390.0),
        has_position=True,
    )

    assert result.action is CandidateAction.EXIT_CANDIDATE
    assert result.reason_codes == ("REGIME_INVALIDATION",)


def test_open_position_exits_after_two_closes_below_ema50() -> None:
    result = StrategyEngine(SAFE_DEFAULT_V1).evaluate(
        replace(valid_features(), consecutive_closes_below_ema50=2),
        has_position=True,
    )

    assert result.action is CandidateAction.EXIT_CANDIDATE
    assert result.reason_codes == ("TWO_CLOSES_BELOW_EMA50",)


def test_existing_position_can_never_create_an_additional_entry() -> None:
    result = StrategyEngine(SAFE_DEFAULT_V1).evaluate(valid_features(), has_position=True)

    assert result.action is CandidateAction.NO_ACTION
    assert result.reason_codes == ("POSITION_ALREADY_OPEN",)
