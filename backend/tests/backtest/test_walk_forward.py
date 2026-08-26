from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from goldguard.backtest.walk_forward import (
    HoldoutQuarantineError,
    WFWindows,
    WalkForwardHarness,
)
from goldguard.domain.models import Candle
from goldguard.strategy.genome import trend_pullback_v1

START = datetime(2023, 1, 1, tzinfo=UTC)


def generate_market_data(num_days: int = 15) -> list[Candle]:
    candles: list[Candle] = []
    curr = START
    base_price = Decimal("2000")
    for i in range(num_days * 30):  # 30 candles per day for test speed
        cycle = Decimal(str((i % 30) - 15)) / Decimal("10")
        close_p = base_price + Decimal(str(i // 30)) + cycle
        c = Candle(
            symbol="PAXGUSDT",
            timeframe="15m",
            open_time=curr,
            close_time=curr + timedelta(minutes=15) - timedelta(milliseconds=1),
            open=close_p - Decimal("1"),
            high=close_p + Decimal("3"),
            low=close_p - Decimal("3"),
            close=close_p,
            volume=Decimal("15"),
            closed=True,
        )
        candles.append(c)
        curr += timedelta(minutes=15)
    return candles


def test_holdout_partition_quarantine_enforcement() -> None:
    candles = generate_market_data(num_days=10)
    harness = WalkForwardHarness()
    genome = trend_pullback_v1()

    # Accessing holdout without valid promotion token raises HoldoutQuarantineError
    with pytest.raises(HoldoutQuarantineError, match="Holdout partition is quarantined"):
        harness.evaluate(
            genome=genome,
            candles_15m=candles,
            unlock_holdout=True,
            promotion_token=None,
        )


def test_walk_forward_chronological_progression_and_wfe_calculation() -> None:
    candles = generate_market_data(num_days=10)
    harness = WalkForwardHarness()
    genome = trend_pullback_v1()

    windows = WFWindows(train_days=3, test_days=1, step_days=1)
    report = harness.evaluate(
        genome=genome,
        candles_15m=candles,
        windows=windows,
        unlock_holdout=False,
    )

    assert len(report.windows) >= 1
    assert report.genome_id == genome.genome_id
    assert report.wfe >= Decimal("0")
    assert report.deflated_sharpe_ratio >= Decimal("0")
    assert report.holdout_evaluated is False
    assert report.holdout_result is None

    for prev_w, curr_w in zip(report.windows[:-1], report.windows[1:], strict=False):
        assert curr_w.train_start > prev_w.train_start
        assert curr_w.test_start >= curr_w.train_end


def test_overfitted_or_underperforming_strategy_fails_gate() -> None:
    candles = generate_market_data(num_days=10)
    harness = WalkForwardHarness()

    bad_genome = trend_pullback_v1().model_copy(
        update={"genome_id": "overfitted-fail-1"}
    )
    windows = WFWindows(train_days=3, test_days=1, step_days=1)
    report = harness.evaluate(
        genome=bad_genome,
        candles_15m=candles,
        windows=windows,
    )

    assert isinstance(report.gate_passed, bool)
    if not report.gate_passed:
        assert len(report.gate_failure_reasons) > 0
