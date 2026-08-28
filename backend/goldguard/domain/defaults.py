from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class StrategySettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str = "safe-default-v1"
    paper_starting_balance: Decimal = Field(default=Decimal("100"), gt=0)
    risk_per_trade: Decimal = Field(
        default=Decimal("0.005"),
        ge=Decimal("0.0005"),
        le=Decimal("0.01"),
    )
    cash_utilization: Decimal = Field(default=Decimal("0.95"), gt=0, le=Decimal("0.95"))
    daily_loss_halt: Decimal = Field(
        default=Decimal("0.03"),
        ge=Decimal("0.005"),
        le=Decimal("0.03"),
    )
    emergency_drawdown_halt: Decimal = Field(
        default=Decimal("0.05"),
        ge=Decimal("0.01"),
        le=Decimal("0.05"),
    )
    cooldown_minutes: int = Field(default=60, ge=15, le=1_440)
    consecutive_loss_limit: int = Field(default=3, ge=1, le=10)
    loss_cooldown_minutes: int = Field(default=360, ge=15, le=1_440)
    maximum_positions: int = Field(default=1, ge=1, le=1)
    stop_atr_multiple: Decimal = Field(default=Decimal("1.5"), ge=Decimal("0.5"), le=3)
    minimum_stop_rate: Decimal = Field(default=Decimal("0.0035"), gt=0, le=Decimal("0.02"))
    maximum_stop_rate: Decimal = Field(default=Decimal("0.0125"), gt=0, le=Decimal("0.03"))
    reward_r_multiple: Decimal = Field(default=Decimal("2"), ge=1, le=4)
    rsi_recovery: Decimal = Field(default=Decimal("45"), ge=20, le=70)
    rsi_ceiling: Decimal = Field(default=Decimal("68"), ge=40, le=90)
    minimum_volume_ratio: Decimal = Field(default=Decimal("0.80"), ge=0, le=5)
    minimum_atr_rate: Decimal = Field(default=Decimal("0.0005"), ge=0, le=Decimal("0.02"))
    maximum_atr_rate: Decimal = Field(default=Decimal("0.015"), gt=0, le=Decimal("0.05"))
    maximum_spread_rate: Decimal = Field(default=Decimal("0.0015"), gt=0, le=Decimal("0.01"))
    ai_minimum_confidence: int = Field(default=65, ge=0, le=100)

    @model_validator(mode="after")
    def validate_relationships(self) -> Self:
        if self.emergency_drawdown_halt <= self.daily_loss_halt:
            raise ValueError("emergency drawdown must be greater than daily loss halt")
        if self.maximum_stop_rate < self.minimum_stop_rate:
            raise ValueError("maximum stop must be at least the minimum stop")
        if self.maximum_atr_rate < self.minimum_atr_rate:
            raise ValueError("maximum ATR must be at least the minimum ATR")
        if self.rsi_ceiling <= self.rsi_recovery:
            raise ValueError("RSI ceiling must exceed the recovery threshold")
        return self


SAFE_DEFAULT_V1 = StrategySettings()


def strategy_settings_from_app(settings: object) -> StrategySettings:
    """Copy live app knobs onto the frozen risk preset without loosening hard ceilings."""
    paper_balance = getattr(settings, "paper_starting_balance", SAFE_DEFAULT_V1.paper_starting_balance)
    risk = getattr(settings, "paper_risk_per_trade", SAFE_DEFAULT_V1.risk_per_trade)
    cash = getattr(settings, "paper_cash_utilization", SAFE_DEFAULT_V1.cash_utilization)
    spread = getattr(settings, "maximum_spread_rate", SAFE_DEFAULT_V1.maximum_spread_rate)
    daily = getattr(settings, "daily_loss_halt", SAFE_DEFAULT_V1.daily_loss_halt)
    drawdown = getattr(settings, "emergency_drawdown_halt", SAFE_DEFAULT_V1.emergency_drawdown_halt)
    payload = SAFE_DEFAULT_V1.model_dump()
    payload.update(
        {
            "paper_starting_balance": paper_balance,
            "risk_per_trade": risk,
            "cash_utilization": min(cash, Decimal("0.95")),
            "maximum_spread_rate": spread,
            "daily_loss_halt": daily,
            "emergency_drawdown_halt": drawdown,
        }
    )
    return StrategySettings.model_validate(payload)

