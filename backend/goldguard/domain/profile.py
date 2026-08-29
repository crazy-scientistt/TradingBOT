from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from goldguard.domain.enums import (
    AutonomousProfileKind,
    ExecutionMode,
    StrategyMode,
)


class RiskCeilings(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_capital_per_trade_rate: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    max_futures_leverage: int = Field(ge=1, le=125)
    max_total_exposure_rate: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    rolling_24h_loss_limit_rate: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))


class NotificationPreferences(BaseModel):
    model_config = ConfigDict(frozen=True)
    telegram_enabled: bool = False
    notify_on_entry: bool = True
    notify_on_exit: bool = True
    notify_on_error: bool = True


class AutonomousProfile(BaseModel):
    model_config = ConfigDict(frozen=True)
    execution_mode: ExecutionMode
    strategy_mode: StrategyMode
    autonomous_profile: AutonomousProfileKind
    spot_enabled: bool
    futures_enabled: bool
    spot_pairs: tuple[str, ...]
    futures_pairs: tuple[str, ...]
    risk: RiskCeilings
    notifications: NotificationPreferences = NotificationPreferences()

    def enabled_product_labels(self) -> tuple[str, ...]:
        labels: list[str] = []
        if self.spot_enabled:
            labels.append("SPOT")
        if self.futures_enabled:
            labels.append("FUTURES")
        return tuple(labels) if labels else ("NONE",)


class ActiveProfile(BaseModel):
    model_config = ConfigDict(frozen=True)
    profile: AutonomousProfile
    hash: str
    created_at: str
    created_by: str
    correlation_id: str


def default_autonomous_profile() -> AutonomousProfile:
    return AutonomousProfile(
        execution_mode=ExecutionMode.PAPER,
        strategy_mode=StrategyMode.AUTONOMOUS,
        autonomous_profile=AutonomousProfileKind.STANDARD,
        spot_enabled=True,
        futures_enabled=True,
        spot_pairs=("PAXGUSDT",),
        futures_pairs=("BTCUSDT", "SOLUSDT"),
        risk=RiskCeilings(
            max_capital_per_trade_rate=Decimal("0.005"),
            max_futures_leverage=2,
            max_total_exposure_rate=Decimal("0.20"),
            rolling_24h_loss_limit_rate=Decimal("0.03"),
        ),
        notifications=NotificationPreferences(),
    )

