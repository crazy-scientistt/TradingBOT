"""Deterministic indicators and strategy candidates."""

from goldguard.strategy.engine import StrategyEngine, StrategyFeatures, StrategyResult
from goldguard.strategy.genome import (
    Condition,
    ExitRules,
    GuardBounds,
    IndicatorSpec,
    StrategyGenome,
    genome_hash,
    trend_pullback_v1,
)

__all__ = [
    "Condition",
    "ExitRules",
    "GuardBounds",
    "IndicatorSpec",
    "StrategyEngine",
    "StrategyFeatures",
    "StrategyGenome",
    "StrategyResult",
    "genome_hash",
    "trend_pullback_v1",
]
