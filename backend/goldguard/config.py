from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated process configuration with paper-safe defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="GOLDGUARD_",
        extra="ignore",
        frozen=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    mode: Literal["paper", "live"] = "paper"
    symbol: Literal["PAXGUSDT"] = "PAXGUSDT"
    entry_timeframe: Literal["15m"] = "15m"
    regime_timeframe: Literal["1h"] = "1h"
    data_dir: Path = Path("/data")

    paper_starting_balance: Decimal = Field(default=Decimal("100"), gt=0)
    paper_risk_per_trade: Decimal = Field(
        default=Decimal("0.005"),
        ge=Decimal("0.0005"),
        le=Decimal("0.01"),
    )
    paper_cash_utilization: Decimal = Field(default=Decimal("0.95"), gt=0, le=1)
    taker_fee_rate: Decimal = Field(default=Decimal("0.001"), ge=0, le=Decimal("0.01"))
    slippage_rate: Decimal = Field(default=Decimal("0.0002"), ge=0, le=Decimal("0.01"))
    maximum_spread_rate: Decimal = Field(default=Decimal("0.0015"), gt=0, le=Decimal("0.01"))

    # Autonomy & research bounds
    autopromotion_enabled: bool = False
    research_backtest_max_per_day: int = Field(default=8, ge=1)
    research_backtest_seconds_per_call: int = Field(default=300, ge=10)
    research_candles_max_per_call: int = Field(default=50_000, ge=100)
    research_web_calls_max_per_day: int = Field(default=50, ge=1)

    # Provider Gateway (OpenCodex / unified provider hub)
    gateway_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOLDGUARD_GATEWAY_BASE_URL", "OPENCODEX_BASE_URL"),
    )
    gateway_data_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GOLDGUARD_GATEWAY_DATA_TOKEN", "OPENCODEX_API_AUTH_TOKEN"),
        repr=False,
    )
    gateway_management_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOLDGUARD_GATEWAY_MANAGEMENT_TOKEN", "OPENCODEX_ADMIN_AUTH_TOKEN"
        ),
        repr=False,
    )

    # Hermes Agent service & bridge
    hermes_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOLDGUARD_HERMES_BASE_URL", "HERMES_BASE_URL"),
    )
    hermes_bridge_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GOLDGUARD_HERMES_BRIDGE_TOKEN", "HERMES_API_KEY"),
        repr=False,
    )

    # Live trading constraints
    live_capability_enabled: bool = False
    live_max_capital: Decimal = Field(default=Decimal("0"), ge=0)

    # Legacy & session secrets
    session_secret: SecretStr = Field(
        default=SecretStr("development-only-change-me"),
        repr=False,
    )
    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="GEMINI_API_KEY",
        repr=False,
    )
    binance_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="BINANCE_API_KEY",
        repr=False,
    )
    binance_api_secret: SecretStr | None = Field(
        default=None,
        validation_alias="BINANCE_API_SECRET",
        repr=False,
    )
    hermes_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="HERMES_API_KEY",
        repr=False,
    )

    @model_validator(mode="after")
    def validate_safety_gates(self) -> Self:
        if self.live_capability_enabled and self.live_max_capital <= 0:
            raise ValueError("live capability requires a positive live capital ceiling")
        if self.mode == "live":
            if not self.live_capability_enabled:
                raise ValueError("live mode requires the server live-capability gate")
            if not self.gateway_data_token:
                raise ValueError("live mode requires gateway data token to route decisions")
        if (
            self.environment == "production"
            and self.session_secret.get_secret_value() == "development-only-change-me"
        ):
            raise ValueError("production requires a non-default session secret")
        return self
