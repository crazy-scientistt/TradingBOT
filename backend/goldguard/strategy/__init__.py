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
from goldguard.strategy.promotion import (
    DevGateConfig,
    GateResult,
    HoldoutGateConfig,
    PromotionPipeline,
    PromotionStage,
    ShadowGateConfig,
    ValGateConfig,
)
from goldguard.strategy.runtime import EngineResult, FeatureSnapshot, GenomeRuntime

__all__ = [
    "Condition",
    "DevGateConfig",
    "EngineResult",
    "ExitRules",
    "FeatureSnapshot",
    "GateResult",
    "GenomeRuntime",
    "GuardBounds",
    "HoldoutGateConfig",
    "IndicatorSpec",
    "PromotionPipeline",
    "PromotionStage",
    "ShadowGateConfig",
    "StrategyEngine",
    "StrategyFeatures",
    "StrategyGenome",
    "StrategyResult",
    "ValGateConfig",
    "genome_hash",
    "trend_pullback_v1",
]
