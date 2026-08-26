import hashlib
import json
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _reject_binary_float(value: Any) -> Any:
    if isinstance(value, float):
        msg = "money and indicator thresholds must be supplied as a decimal string or Decimal"
        raise ValueError(msg)
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_binary_float(item)
    return value


IndicatorName = Literal[
    "ema",
    "rsi",
    "atr",
    "atr_rate",
    "volume_ratio",
    "spread_rate",
    "close",
    "open",
    "high",
    "low",
    "slope",
    "consecutive_closes_below_ema50",
]

Timeframe = Literal["15m", "1h"]

Operator = Literal[
    "crosses_above",
    "crosses_below",
    "gt",
    "gte",
    "lt",
    "lte",
    "within",
]


class IndicatorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    indicator: IndicatorName
    timeframe: Timeframe = "15m"
    period: int = Field(default=14, ge=1, le=500)
    offset: int = Field(default=0, ge=0, le=50)


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    left: IndicatorSpec | str
    op: Operator
    right: IndicatorSpec | Decimal | str | tuple[Decimal, Decimal]

    @field_validator("right", mode="before")
    @classmethod
    def reject_floats_in_right(cls, value: Any) -> Any:
        return _reject_binary_float(value)


class ExitRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    regime_invalidation: bool = True
    r_multiple_min: Decimal = Field(default=Decimal("2"), ge=Decimal("1"), le=Decimal("4"))
    stop_atr_multiple: Decimal = Field(default=Decimal("1.5"), ge=Decimal("0.5"), le=Decimal("3"))
    max_hold_bars: int | None = Field(default=None, ge=1, le=2000)

    @field_validator("r_multiple_min", "stop_atr_multiple", mode="before")
    @classmethod
    def reject_float_exit(cls, value: Any) -> Any:
        return _reject_binary_float(value)


class GuardBounds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min_atr_rate: Decimal = Field(default=Decimal("0.0005"), ge=Decimal("0"), le=Decimal("0.02"))
    max_atr_rate: Decimal = Field(default=Decimal("0.015"), gt=Decimal("0"), le=Decimal("0.05"))
    max_spread_rate: Decimal = Field(default=Decimal("0.0015"), gt=Decimal("0"), le=Decimal("0.01"))

    @field_validator("min_atr_rate", "max_atr_rate", "max_spread_rate", mode="before")
    @classmethod
    def reject_float_guard(cls, value: Any) -> Any:
        return _reject_binary_float(value)


class StrategyGenome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    genome_id: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    parent_id: str | None = None
    title: str = Field(min_length=5, max_length=120)
    hypothesis: str = Field(min_length=20, max_length=1000)
    regime: tuple[Condition, ...] = Field(default=())
    entry: tuple[Condition, ...] = Field(min_length=2)
    exit: ExitRules = Field(default_factory=ExitRules)
    guard: GuardBounds = Field(default_factory=GuardBounds)
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=10)

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("evidence_refs must be unique")
        for ref in value:
            if not ref.strip():
                raise ValueError("evidence_ref cannot be empty")
        return value


def genome_hash(genome: StrategyGenome) -> str:
    """Compute deterministic SHA-256 canonical hash of a StrategyGenome."""
    dump = genome.model_dump(mode="json")
    canonical_json = json.dumps(dump, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def trend_pullback_v1() -> StrategyGenome:
    """Canonical factory for the baseline trend pullback strategy v1."""
    hypothesis = (
        "In an established 1h uptrend (EMA50 > EMA200 with positive slope), "
        "15m RSI pullbacks recovering above 45 offer favorable risk/reward entries."
    )
    return StrategyGenome(
        genome_id="trend-pullback-v1",
        parent_id=None,
        title="PAXG 15m/1h Trend Pullback Baseline",
        hypothesis=hypothesis,
        regime=(
            Condition(
                left=IndicatorSpec(indicator="ema", timeframe="1h", period=50),
                op="gt",
                right=IndicatorSpec(indicator="ema", timeframe="1h", period=200),
            ),
            Condition(
                left=IndicatorSpec(indicator="close", timeframe="1h", period=1),
                op="gt",
                right=IndicatorSpec(indicator="ema", timeframe="1h", period=200),
            ),
            Condition(
                left=IndicatorSpec(indicator="slope", timeframe="1h", period=50),
                op="gt",
                right=Decimal("0"),
            ),
        ),
        entry=(
            Condition(
                left=IndicatorSpec(indicator="close", timeframe="15m", period=1, offset=1),
                op="lte",
                right=IndicatorSpec(indicator="ema", timeframe="15m", period=20),
            ),
            Condition(
                left=IndicatorSpec(indicator="close", timeframe="15m", period=1, offset=0),
                op="gt",
                right=IndicatorSpec(indicator="ema", timeframe="15m", period=20),
            ),
            Condition(
                left=IndicatorSpec(indicator="close", timeframe="15m", period=1, offset=0),
                op="gt",
                right=IndicatorSpec(indicator="ema", timeframe="15m", period=50),
            ),
            Condition(
                left=IndicatorSpec(indicator="rsi", timeframe="15m", period=14, offset=1),
                op="lt",
                right=Decimal("45"),
            ),
            Condition(
                left=IndicatorSpec(indicator="rsi", timeframe="15m", period=14, offset=0),
                op="gte",
                right=Decimal("45"),
            ),
            Condition(
                left=IndicatorSpec(indicator="rsi", timeframe="15m", period=14, offset=0),
                op="lt",
                right=Decimal("68"),
            ),
            Condition(
                left=IndicatorSpec(indicator="volume_ratio", timeframe="15m", period=20),
                op="gte",
                right=Decimal("0.80"),
            ),
        ),
        exit=ExitRules(
            regime_invalidation=True,
            r_multiple_min=Decimal("2"),
            stop_atr_multiple=Decimal("1.5"),
            max_hold_bars=None,
        ),
        guard=GuardBounds(
            min_atr_rate=Decimal("0.0005"),
            max_atr_rate=Decimal("0.015"),
            max_spread_rate=Decimal("0.0015"),
        ),
        evidence_refs=("baseline-trend-pullback-v1",),
    )
