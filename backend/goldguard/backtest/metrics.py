import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import pairwise


@dataclass(frozen=True)
class EquityPoint:
    observed_at: datetime
    equity: Decimal


@dataclass(frozen=True)
class TradePerformance:
    net_pnl: Decimal
    gross_pnl: Decimal
    fees: Decimal
    opened_at: datetime
    closed_at: datetime


@dataclass(frozen=True)
class PerformanceReport:
    initial_equity: Decimal
    final_equity: Decimal
    net_pnl: Decimal
    gross_pnl: Decimal
    fee_drag: Decimal
    net_return: Decimal
    annualized_return: Decimal | None
    trade_count: int
    win_rate: Decimal
    profit_factor: Decimal | None
    expectancy: Decimal
    maximum_drawdown: Decimal
    exposure_rate: Decimal
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    calmar_ratio: Decimal | None
    buy_and_hold_return: Decimal
    sample_sufficient: bool


def _as_decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _maximum_drawdown(curve: tuple[EquityPoint, ...]) -> Decimal:
    if not curve:
        return Decimal("0")
    peak = curve[0].equity
    maximum = Decimal("0")
    for point in curve:
        peak = max(peak, point.equity)
        if peak > 0:
            maximum = max(maximum, (peak - point.equity) / peak)
    return maximum


def _period_returns(curve: tuple[EquityPoint, ...]) -> tuple[float, ...]:
    values: list[float] = []
    for previous, current in pairwise(curve):
        if previous.equity > 0:
            values.append(float((current.equity - previous.equity) / previous.equity))
    return tuple(values)


def _annualized_return(
    initial: Decimal,
    final: Decimal,
    periods: int,
    annualization_periods: int,
) -> Decimal | None:
    if initial <= 0 or final < 0 or periods <= 0:
        return None
    total_return = final / initial - Decimal("1")
    if periods == annualization_periods:
        return total_return
    return _as_decimal(math.pow(float(final / initial), annualization_periods / periods) - 1)


def _risk_adjusted_ratios(
    returns: tuple[float, ...],
    annualization_periods: int,
) -> tuple[Decimal | None, Decimal | None]:
    if len(returns) < 2:
        return None, None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    standard_deviation = math.sqrt(variance)
    sharpe = (
        _as_decimal(mean / standard_deviation * math.sqrt(annualization_periods))
        if standard_deviation > 0
        else None
    )
    downside_deviation = math.sqrt(sum(min(value, 0.0) ** 2 for value in returns) / len(returns))
    sortino = (
        _as_decimal(mean / downside_deviation * math.sqrt(annualization_periods))
        if downside_deviation > 0
        else None
    )
    return sharpe, sortino


def _exposure_rate(
    trades: tuple[TradePerformance, ...],
    curve: tuple[EquityPoint, ...],
) -> Decimal:
    if len(curve) < 2:
        return Decimal("0")
    total_seconds = Decimal(str((curve[-1].observed_at - curve[0].observed_at).total_seconds()))
    if total_seconds <= 0:
        return Decimal("0")
    exposed_seconds = sum(
        (Decimal(str((trade.closed_at - trade.opened_at).total_seconds())) for trade in trades),
        start=Decimal("0"),
    )
    return min(exposed_seconds / total_seconds, Decimal("1"))


def calculate_metrics(
    *,
    initial_equity: Decimal,
    trades: tuple[TradePerformance, ...],
    equity_curve: tuple[EquityPoint, ...],
    benchmark_start: Decimal,
    benchmark_end: Decimal,
    annualization_periods: int = 365,
    minimum_sample_size: int = 100,
) -> PerformanceReport:
    if initial_equity <= 0:
        raise ValueError("initial equity must be positive")
    if annualization_periods <= 0 or minimum_sample_size <= 0:
        raise ValueError("period and sample settings must be positive")
    if benchmark_start <= 0:
        raise ValueError("benchmark start must be positive")

    final_equity = equity_curve[-1].equity if equity_curve else initial_equity
    net_pnl = sum((trade.net_pnl for trade in trades), start=Decimal("0"))
    gross_pnl = sum((trade.gross_pnl for trade in trades), start=Decimal("0"))
    fees = sum((trade.fees for trade in trades), start=Decimal("0"))
    wins = tuple(trade.net_pnl for trade in trades if trade.net_pnl > 0)
    losses = tuple(trade.net_pnl for trade in trades if trade.net_pnl < 0)
    trade_count = len(trades)
    gross_wins = sum(wins, start=Decimal("0"))
    gross_losses = abs(sum(losses, start=Decimal("0")))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else None
    returns = _period_returns(equity_curve)
    annualized = _annualized_return(
        initial_equity,
        final_equity,
        len(returns),
        annualization_periods,
    )
    maximum_drawdown = _maximum_drawdown(equity_curve)
    sharpe, sortino = _risk_adjusted_ratios(returns, annualization_periods)
    calmar = (
        annualized / maximum_drawdown if annualized is not None and maximum_drawdown > 0 else None
    )
    return PerformanceReport(
        initial_equity=initial_equity,
        final_equity=final_equity,
        net_pnl=net_pnl,
        gross_pnl=gross_pnl,
        fee_drag=fees,
        net_return=final_equity / initial_equity - Decimal("1"),
        annualized_return=annualized,
        trade_count=trade_count,
        win_rate=Decimal(len(wins)) / Decimal(trade_count) if trade_count else Decimal("0"),
        profit_factor=profit_factor,
        expectancy=net_pnl / Decimal(trade_count) if trade_count else Decimal("0"),
        maximum_drawdown=maximum_drawdown,
        exposure_rate=_exposure_rate(trades, equity_curve),
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        buy_and_hold_return=benchmark_end / benchmark_start - Decimal("1"),
        sample_sufficient=trade_count >= minimum_sample_size,
    )
