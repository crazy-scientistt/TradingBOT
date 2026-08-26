import ast
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from goldguard.domain.enums import CandidateAction
from goldguard.strategy.engine import StrategyFeatures
from goldguard.strategy.genome import (
    Condition,
    ExitRules,
    GuardBounds,
    IndicatorSpec,
    StrategyGenome,
    trend_pullback_v1,
)
from goldguard.strategy.runtime import FeatureSnapshot, GenomeRuntime


def valid_features() -> FeatureSnapshot:
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


def test_runtime_ast_safety_scan() -> None:
    """Scan runtime.py AST to verify no eval, exec, dynamic getattr, os, or subprocess."""
    runtime_path = Path(__file__).resolve().parents[2] / "goldguard" / "strategy" / "runtime.py"
    content = runtime_path.read_text(encoding="utf-8")
    tree = ast.parse(content)

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("eval", "exec")
        ):
            pytest.fail(f"Disallowed call to {node.func.id} found in runtime.py")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("os", "subprocess", "sys"):
                    pytest.fail(f"Disallowed import {alias.name} found in runtime.py")
        elif isinstance(node, ast.ImportFrom) and node.module in ("os", "subprocess", "sys"):
            pytest.fail(f"Disallowed import from {node.module} found in runtime.py")


def test_trend_pullback_v1_parity_with_all_engine_test_cases() -> None:
    runtime = GenomeRuntime()
    genome = trend_pullback_v1()
    features = valid_features()

    result = runtime.evaluate(genome, features, has_position=False)
    assert result.action is CandidateAction.ENTRY_CANDIDATE
    assert "TREND_PULLBACK_RECOVERY" in result.reason_codes
    assert result.strategy_version == "trend-pullback-v1"


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
        ("sufficient_history", False, "INSUFFICIENT_HISTORY"),
        ("contiguous", False, "DATA_NOT_CONTIGUOUS"),
        ("quote_fresh", False, "STALE_QUOTE"),
    ],
)
def test_runtime_reproduces_all_missing_conditions(field: str, value: object, reason: str) -> None:
    runtime = GenomeRuntime()
    genome = trend_pullback_v1()
    features = replace(valid_features(), **{field: value})

    result = runtime.evaluate(genome, features, has_position=False)
    assert result.action is CandidateAction.NO_ACTION
    assert reason in result.reason_codes


def test_runtime_position_exits() -> None:
    runtime = GenomeRuntime()
    genome = trend_pullback_v1()

    # Regime invalidation
    r_exit = runtime.evaluate(
        genome, replace(valid_features(), ema50_1h=2390.0), has_position=True
    )
    assert r_exit.action is CandidateAction.EXIT_CANDIDATE
    assert "REGIME_INVALIDATION" in r_exit.reason_codes

    # Two closes below EMA50
    r_ema_exit = runtime.evaluate(
        genome, replace(valid_features(), consecutive_closes_below_ema50=2), has_position=True
    )
    assert r_ema_exit.action is CandidateAction.EXIT_CANDIDATE
    assert "TWO_CLOSES_BELOW_EMA50" in r_ema_exit.reason_codes

    # Flat position when already open
    r_open = runtime.evaluate(genome, valid_features(), has_position=True)
    assert r_open.action is CandidateAction.NO_ACTION
    assert "POSITION_ALREADY_OPEN" in r_open.reason_codes


def test_runtime_handles_malformed_condition_gracefully() -> None:
    runtime = GenomeRuntime()
    malformed_genome = StrategyGenome(
        genome_id="malformed-v1",
        title="Malformed Genome",
        hypothesis="Testing error boundary resilience for corrupted genomes.",
        regime=(),
        entry=(
            Condition(
                left="unknown_indicator_symbol",
                op="gt",
                right=Decimal("100"),
            ),
            Condition(
                left=IndicatorSpec(indicator="close", timeframe="15m", period=1),
                op="gt",
                right=Decimal("2000"),
            ),
        ),
        exit=ExitRules(),
        guard=GuardBounds(),
        evidence_refs=("test-ref",),
    )

    result = runtime.evaluate(malformed_genome, valid_features(), has_position=False)
    assert result.action is CandidateAction.NO_ACTION
    assert "GENOME_RUNTIME_ERROR" in result.reason_codes
