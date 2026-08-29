from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from goldguard.domain.enums import (
    AutonomousProfileKind,
    ExecutionMode,
    StrategyMode,
)
from goldguard.domain.profile import (
    ActiveProfile,
    AutonomousProfile,
    NotificationPreferences,
    RiskCeilings,
)
from goldguard.services.settings_service import SettingsPreview


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class TotpVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, StringConstraints(min_length=6, max_length=16)]


class AuthSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authenticated: bool
    username: str | None = None
    totp_required: bool = True
    totp_verified: bool = False
    csrf_token: str | None = None
    expires_at: str | None = None
    absolute_expires_at: str | None = None


class RiskCeilingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_capital_per_trade_rate: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    max_futures_leverage: int = Field(ge=1, le=125)
    max_total_exposure_rate: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    rolling_24h_loss_limit_rate: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))

    def to_domain(self) -> RiskCeilings:
        return RiskCeilings(
            max_capital_per_trade_rate=self.max_capital_per_trade_rate,
            max_futures_leverage=self.max_futures_leverage,
            max_total_exposure_rate=self.max_total_exposure_rate,
            rolling_24h_loss_limit_rate=self.rolling_24h_loss_limit_rate,
        )


class NotificationPreferencesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    telegram_enabled: bool = False
    notify_on_entry: bool = True
    notify_on_exit: bool = True
    notify_on_error: bool = True

    def to_domain(self) -> NotificationPreferences:
        return NotificationPreferences(
            telegram_enabled=self.telegram_enabled,
            notify_on_entry=self.notify_on_entry,
            notify_on_exit=self.notify_on_exit,
            notify_on_error=self.notify_on_error,
        )


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_mode: ExecutionMode
    strategy_mode: StrategyMode
    autonomous_profile: AutonomousProfileKind
    spot_enabled: bool
    futures_enabled: bool
    spot_pairs: list[str] = Field(default_factory=list)
    futures_pairs: list[str] = Field(default_factory=list)
    risk: RiskCeilingsPayload
    notifications: NotificationPreferencesPayload = Field(
        default_factory=NotificationPreferencesPayload
    )

    def to_domain(self) -> AutonomousProfile:
        return AutonomousProfile(
            execution_mode=self.execution_mode,
            strategy_mode=self.strategy_mode,
            autonomous_profile=self.autonomous_profile,
            spot_enabled=self.spot_enabled,
            futures_enabled=self.futures_enabled,
            spot_pairs=tuple(sorted(set(self.spot_pairs))),
            futures_pairs=tuple(sorted(set(self.futures_pairs))),
            risk=self.risk.to_domain(),
            notifications=self.notifications.to_domain(),
        )

    @classmethod
    def from_domain(cls, domain: AutonomousProfile) -> ProfileUpdate:
        return cls(
            execution_mode=domain.execution_mode,
            strategy_mode=domain.strategy_mode,
            autonomous_profile=domain.autonomous_profile,
            spot_enabled=domain.spot_enabled,
            futures_enabled=domain.futures_enabled,
            spot_pairs=list(domain.spot_pairs),
            futures_pairs=list(domain.futures_pairs),
            risk=RiskCeilingsPayload(
                max_capital_per_trade_rate=domain.risk.max_capital_per_trade_rate,
                max_futures_leverage=domain.risk.max_futures_leverage,
                max_total_exposure_rate=domain.risk.max_total_exposure_rate,
                rolling_24h_loss_limit_rate=domain.risk.rolling_24h_loss_limit_rate,
            ),
            notifications=NotificationPreferencesPayload(
                telegram_enabled=domain.notifications.telegram_enabled,
                notify_on_entry=domain.notifications.notify_on_entry,
                notify_on_exit=domain.notifications.notify_on_exit,
                notify_on_error=domain.notifications.notify_on_error,
            ),
        )


class ProfileEquivalents(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_capital_per_trade_usdt: str | None = None
    max_total_exposure_usdt: str | None = None
    rolling_24h_loss_limit_usdt: str | None = None
    account_equity_usdt: str | None = None


class ProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: ProfileUpdate
    hash: str
    created_at: str
    created_by: str
    correlation_id: str
    equivalents: ProfileEquivalents
    blockers: list[str] = Field(default_factory=list)

    @classmethod
    def from_active(
        cls,
        active: ActiveProfile,
        equity: Decimal | None = None,
        blockers: tuple[str, ...] | list[str] = (),
    ) -> ProfileResponse:
        domain = active.profile
        if equity is not None and equity >= 0:
            max_capital = (domain.risk.max_capital_per_trade_rate * equity).quantize(
                Decimal("0.01")
            )
            max_total = (domain.risk.max_total_exposure_rate * equity).quantize(
                Decimal("0.01")
            )
            rolling_loss = (domain.risk.rolling_24h_loss_limit_rate * equity).quantize(
                Decimal("0.01")
            )
            eq_str = str(equity.quantize(Decimal("0.01")))
            equivalents = ProfileEquivalents(
                max_capital_per_trade_usdt=str(max_capital),
                max_total_exposure_usdt=str(max_total),
                rolling_24h_loss_limit_usdt=str(rolling_loss),
                account_equity_usdt=eq_str,
            )
        else:
            equivalents = ProfileEquivalents()

        return cls(
            profile=ProfileUpdate.from_domain(domain),
            hash=active.hash,
            created_at=active.created_at,
            created_by=active.created_by,
            correlation_id=active.correlation_id,
            equivalents=equivalents,
            blockers=list(blockers),
        )


class ProfilePreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: ProfileUpdate
    equivalents: ProfileEquivalents
    blockers: list[str] = Field(default_factory=list)

    @classmethod
    def from_preview(
        cls, preview: SettingsPreview, equity: Decimal | None = None
    ) -> ProfilePreviewResponse:
        eq_str = (
            str(equity.quantize(Decimal("0.01")))
            if equity is not None and equity >= 0
            else None
        )
        return cls(
            profile=ProfileUpdate.from_domain(preview.profile),
            equivalents=ProfileEquivalents(
                max_capital_per_trade_usdt=(
                    str(preview.max_capital_per_trade_usdt)
                    if preview.max_capital_per_trade_usdt is not None
                    else None
                ),
                max_total_exposure_usdt=(
                    str(preview.max_total_exposure_usdt)
                    if preview.max_total_exposure_usdt is not None
                    else None
                ),
                rolling_24h_loss_limit_usdt=(
                    str(preview.rolling_24h_loss_limit_usdt)
                    if preview.rolling_24h_loss_limit_usdt is not None
                    else None
                ),
                account_equity_usdt=eq_str,
            ),
            blockers=list(preview.blockers),
        )

