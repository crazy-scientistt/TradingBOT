"""Chronological, cost-aware strategy evaluation."""

from goldguard.backtest.engine import (
    BacktestEngine,
    BacktestResult,
    FrictionConfig,
)
from goldguard.backtest.metrics import PerformanceReport, calculate_metrics
from goldguard.backtest.replay import (
    ChronologicalPartitions,
    ReplayEngine,
    ReplayResult,
    chronological_partitions,
)
from goldguard.backtest.reports import report_to_dict

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "ChronologicalPartitions",
    "FrictionConfig",
    "PerformanceReport",
    "ReplayEngine",
    "ReplayResult",
    "calculate_metrics",
    "chronological_partitions",
    "report_to_dict",
]
