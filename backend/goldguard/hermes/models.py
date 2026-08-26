from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StrategyParameter = Literal[
    "rsi_recovery",
    "rsi_ceiling",
    "minimum_volume_ratio",
    "stop_atr_multiple",
    "reward_r_multiple",
    "minimum_atr_rate",
    "maximum_atr_rate",
]

PARAMETER_BOUNDS: dict[StrategyParameter, tuple[Decimal, Decimal]] = {
    "rsi_recovery": (Decimal("20"), Decimal("70")),
    "rsi_ceiling": (Decimal("40"), Decimal("90")),
    "minimum_volume_ratio": (Decimal("0"), Decimal("5")),
    "stop_atr_multiple": (Decimal("0.5"), Decimal("3")),
    "reward_r_multiple": (Decimal("1"), Decimal("4")),
    "minimum_atr_rate": (Decimal("0"), Decimal("0.02")),
    "maximum_atr_rate": (Decimal("0.0001"), Decimal("0.05")),
}


class StrategyChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parameter: StrategyParameter
    value: Decimal

    @field_validator("value", mode="before")
    @classmethod
    def reject_binary_float(cls, value: Any) -> Any:
        if isinstance(value, float):
            raise ValueError("proposal values must be exact decimal strings")
        return value

    @model_validator(mode="after")
    def enforce_safe_bounds(self) -> Self:
        minimum, maximum = PARAMETER_BOUNDS[self.parameter]
        if not minimum <= self.value <= maximum:
            raise ValueError(f"{self.parameter} is outside its safe bounds")
        return self


class StrategyProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_id: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    parent_version: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=5, max_length=120)
    rationale: str = Field(min_length=20, max_length=1_000)
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=10)
    change: StrategyChange

    @field_validator("evidence_refs")
    @classmethod
    def evidence_must_be_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("evidence references must be unique")
        if any(not item.strip() or len(item) > 120 for item in value):
            raise ValueError("evidence references must be short non-empty identifiers")
        return value


class SanitizedResearchPacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    market_digest: str = Field(min_length=1, max_length=2_000)
    recent_trade_summaries: tuple[str, ...] = Field(max_length=100)
    evaluation_summaries: tuple[str, ...] = Field(max_length=30)
    evidence_catalog: tuple[str, ...] = Field(min_length=1, max_length=200)


class EvaluationPartition(str):
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    HOLDOUT = "holdout"
