from decimal import Decimal

import pytest
from goldguard.strategy.genome import (
    ExitRules,
    IndicatorSpec,
    StrategyGenome,
    genome_hash,
    trend_pullback_v1,
)
from pydantic import ValidationError


def test_genome_validates_required_fields_and_bounds() -> None:
    genome = trend_pullback_v1()
    assert genome.genome_id == "trend-pullback-v1"
    assert len(genome.hypothesis) >= 20
    assert len(genome.entry) >= 2
    assert len(genome.evidence_refs) >= 1
    assert genome.exit.r_multiple_min == Decimal("2")
    assert genome.exit.stop_atr_multiple == Decimal("1.5")


def test_genome_rejects_unknown_fields() -> None:
    valid_dump = trend_pullback_v1().model_dump(mode="json")
    with pytest.raises(ValidationError, match=r"extra_forbidden|Extra inputs are not permitted"):
        StrategyGenome.model_validate({**valid_dump, "illegal_field": "hacked"})


def test_genome_rejects_float_literals() -> None:
    with pytest.raises(ValidationError, match="decimal string or Decimal"):
        ExitRules(
            r_multiple_min=2.0,  # type: ignore[arg-type]
            stop_atr_multiple=Decimal("1.5"),
        )


def test_genome_rejects_out_of_bound_lookback_and_r_multiple() -> None:
    with pytest.raises(ValidationError):
        IndicatorSpec(indicator="ema", timeframe="15m", period=0)

    with pytest.raises(ValidationError):
        IndicatorSpec(indicator="ema", timeframe="15m", period=501)

    with pytest.raises(ValidationError):
        ExitRules(
            r_multiple_min=Decimal("5"),  # max is 4
            stop_atr_multiple=Decimal("1.5"),
        )

    with pytest.raises(ValidationError):
        ExitRules(
            r_multiple_min=Decimal("2"),
            stop_atr_multiple=Decimal("0.2"),  # min is 0.5
        )


def test_genome_rejects_empty_evidence_or_short_hypothesis() -> None:
    base = trend_pullback_v1()
    dump = base.model_dump()

    with pytest.raises(ValidationError):
        StrategyGenome.model_validate({**dump, "evidence_refs": ()})

    with pytest.raises(ValidationError):
        StrategyGenome.model_validate({**dump, "hypothesis": "too short"})


def test_genome_hash_is_deterministic_and_canonical() -> None:
    g1 = trend_pullback_v1()
    g2 = trend_pullback_v1()

    h1 = genome_hash(g1)
    h2 = genome_hash(g2)

    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex string

    # Modifying title or condition changes hash
    dump = g1.model_dump()
    dump["title"] = "Modified Title"
    g_modified = StrategyGenome.model_validate(dump)
    assert genome_hash(g_modified) != h1
