from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from goldguard.backtest.metrics import EquityPoint, TradePerformance, calculate_metrics

START = datetime(2026, 1, 1, tzinfo=UTC)


def test_metrics_match_a_hand_calculated_ledger() -> None:
    trades = (
        TradePerformance(
            net_pnl=Decimal("10"),
            gross_pnl=Decimal("12"),
            fees=Decimal("2"),
            opened_at=START,
            closed_at=START + timedelta(hours=12),
        ),
        TradePerformance(
            net_pnl=Decimal("-5"),
            gross_pnl=Decimal("-3"),
            fees=Decimal("2"),
            opened_at=START + timedelta(hours=24),
            closed_at=START + timedelta(hours=36),
        ),
    )
    curve = (
        EquityPoint(START, Decimal("100")),
        EquityPoint(START + timedelta(hours=24), Decimal("110")),
        EquityPoint(START + timedelta(hours=48), Decimal("105")),
    )

    report = calculate_metrics(
        initial_equity=Decimal("100"),
        trades=trades,
        equity_curve=curve,
        benchmark_start=Decimal("100"),
        benchmark_end=Decimal("105"),
        annualization_periods=2,
        minimum_sample_size=100,
    )

    assert report.net_pnl == Decimal("5")
    assert report.gross_pnl == Decimal("9")
    assert report.fee_drag == Decimal("4")
    assert report.net_return == Decimal("0.05")
    assert report.win_rate == Decimal("0.5")
    assert report.profit_factor == Decimal("2")
    assert report.expectancy == Decimal("2.5")
    assert float(report.maximum_drawdown) == pytest.approx(5 / 110)
    assert float(report.exposure_rate) == pytest.approx(0.5)
    assert float(report.calmar_ratio) == pytest.approx(1.1)
    assert report.buy_and_hold_return == Decimal("0.05")
    assert report.sample_sufficient is False


def test_metrics_handle_no_trades_without_fabricating_ratios() -> None:
    curve = (EquityPoint(START, Decimal("100")),)

    report = calculate_metrics(
        initial_equity=Decimal("100"),
        trades=(),
        equity_curve=curve,
        benchmark_start=Decimal("100"),
        benchmark_end=Decimal("100"),
    )

    assert report.trade_count == 0
    assert report.profit_factor is None
    assert report.sharpe_ratio is None
    assert report.sortino_ratio is None
    assert report.calmar_ratio is None
    assert report.sample_sufficient is False
