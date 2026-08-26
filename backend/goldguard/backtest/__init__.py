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
from goldguard.backtest.walk_forward import (
    HoldoutQuarantineError,
    WalkForwardHarness,
    WalkForwardReport,
    WFWindows,
    WindowResult,
)

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "ChronologicalPartitions",
    "FrictionConfig",
    "HoldoutQuarantineError",
    "PerformanceReport",
    "ReplayEngine",
    "ReplayResult",
    "WFWindows",
    "WalkForwardHarness",
    "WalkForwardReport",
    "WindowResult",
    "calculate_metrics",
    "chronological_partitions",
    "report_to_dict",
]
