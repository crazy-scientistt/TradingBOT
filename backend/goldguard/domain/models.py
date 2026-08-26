from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from goldguard.domain.enums import AiDecision, CandidateAction


def _reject_binary_float(value: Any) -> Any:
    if isinstance(value, float):
        raise ValueError("money must be supplied as a decimal string or Decimal")
    return value


class Candle(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(ge=0)
    closed: bool

    @field_validator("open", "high", "low", "close", "volume", mode="before")
    @classmethod
    def reject_float_money(cls, value: Any) -> Any:
        return _reject_binary_float(value)

    @field_validator("open_time", "close_time")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_interval_and_prices(self) -> Self:
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be after open_time")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must cover open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must cover open, close, and high")
        return self


class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)

    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    observed_at: datetime

    @field_validator("bid", "ask", mode="before")
    @classmethod
    def reject_float_money(cls, value: Any) -> Any:
        return _reject_binary_float(value)

    @field_validator("observed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("timestamps must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_spread(self) -> Self:
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        return self

    @property
    def spread_rate(self) -> Decimal:
        midpoint = (self.ask + self.bid) / Decimal("2")
        return (self.ask - self.bid) / midpoint


class TradePlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry: Decimal = Field(gt=0)
    stop: Decimal = Field(gt=0)
    target: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    risk_amount: Decimal = Field(gt=0)
    expected_fees: Decimal = Field(ge=0)

    @field_validator(
        "entry",
        "stop",
        "target",
        "quantity",
        "risk_amount",
        "expected_fees",
        mode="before",
    )
    @classmethod
    def reject_float_money(cls, value: Any) -> Any:
        return _reject_binary_float(value)

    @model_validator(mode="after")
    def validate_long_plan(self) -> Self:
        if self.stop >= self.entry:
            raise ValueError("long-only stop must be below entry")
        if self.target <= self.entry:
            raise ValueError("long-only target must be above entry")
        return self

    def with_stop(self, new_stop: Decimal) -> "TradePlan":
        _reject_binary_float(new_stop)
        if new_stop < self.stop:
            raise ValueError("stop widening is prohibited")
        return self.model_copy(update={"stop": new_stop})


def ai_decision_is_compatible(candidate: CandidateAction, decision: AiDecision) -> bool:
    allowed = {
        CandidateAction.ENTRY_CANDIDATE: {
            AiDecision.APPROVE_ENTRY,
            AiDecision.REJECT_ENTRY,
            AiDecision.HOLD,
        },
        CandidateAction.EXIT_CANDIDATE: {AiDecision.EXIT, AiDecision.HOLD},
        CandidateAction.NO_ACTION: {AiDecision.HOLD},
    }
    return decision in allowed[candidate]
