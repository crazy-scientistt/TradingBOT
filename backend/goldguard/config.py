from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
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

    live_capability_enabled: bool = False
    live_max_capital: Decimal = Field(default=Decimal("0"), ge=0)

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
        if self.mode == "live" and not self.live_capability_enabled:
            raise ValueError("live mode requires the server live-capability gate")
        if (
            self.environment == "production"
            and self.session_secret.get_secret_value() == "development-only-change-me"
        ):
            raise ValueError("production requires a non-default session secret")
        return self
