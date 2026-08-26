"""Chronological, cost-aware strategy evaluation."""

from goldguard.backtest.metrics import PerformanceReport, calculate_metrics
from goldguard.backtest.replay import ReplayEngine, ReplayResult, chronological_partitions

__all__ = [
    "PerformanceReport",
    "ReplayEngine",
    "ReplayResult",
    "calculate_metrics",
    "chronological_partitions",
]
