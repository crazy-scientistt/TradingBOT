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
from goldguard.strategy.runtime import EngineResult, FeatureSnapshot, GenomeRuntime

__all__ = [
    "Condition",
    "EngineResult",
    "ExitRules",
    "FeatureSnapshot",
    "GenomeRuntime",
    "GuardBounds",
    "IndicatorSpec",
    "StrategyEngine",
    "StrategyFeatures",
    "StrategyGenome",
    "StrategyResult",
    "genome_hash",
    "trend_pullback_v1",
]
