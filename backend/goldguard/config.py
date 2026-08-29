from __future__ import annotations

import secrets
from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
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
    # Disable to run the API without reaching the public market endpoints (tests, offline demos).
    market_ingestion_enabled: bool = True
    # Binance's public market-data mirror: identical REST paths, no key, and it answers
    # from regions where api.binance.com returns HTTP 451. Point at api.binance.com when
    # the deployment region is eligible.
    market_base_url: str = "https://data-api.binance.vision"

    paper_starting_balance: Decimal = Field(default=Decimal("10000"), gt=0)
    paper_risk_per_trade: Decimal = Field(
        default=Decimal("0.005"),
        ge=Decimal("0.0005"),
        le=Decimal("0.01"),
    )
    paper_cash_utilization: Decimal = Field(default=Decimal("0.95"), gt=0, le=1)
    taker_fee_rate: Decimal = Field(default=Decimal("0.001"), ge=0, le=Decimal("0.01"))
    slippage_rate: Decimal = Field(default=Decimal("0.0002"), ge=0, le=Decimal("0.01"))
    maximum_spread_rate: Decimal = Field(default=Decimal("0.0015"), gt=0, le=Decimal("0.01"))

    # CORS configuration
    cors_origins: str | tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    )

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

    # Session secret
    session_secret: SecretStr = Field(
        default_factory=lambda: SecretStr(secrets.token_urlsafe(32)),
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

    @field_validator("cors_origins", mode="after")
    @classmethod
    def normalize_cors_origins(cls, value: str | tuple[str, ...]) -> tuple[str, ...]:
        if isinstance(value, str):
            parts = [origin.strip() for origin in value.split(",") if origin.strip()]
            return tuple(parts)
        if isinstance(value, (list, tuple, set)):
            return tuple(str(origin).strip() for origin in value if str(origin).strip())
        return ()

    @model_validator(mode="after")
    def validate_safety_gates(self) -> Self:
        if self.live_capability_enabled and self.live_max_capital <= 0:
            raise ValueError("live capability requires a positive live capital ceiling")
        if self.mode == "live":
            if not self.live_capability_enabled:
                raise ValueError("live mode requires the server live-capability gate")
            if not self.gateway_data_token:
                raise ValueError("live mode requires gateway data token to route decisions")

        if self.environment == "production":
            origins = (
                self.cors_origins
                if isinstance(self.cors_origins, tuple)
                else (self.cors_origins,)
            )
            if "*" in origins or any("*" in origin for origin in origins):
                raise ValueError("wildcard CORS origins are not permitted in production")
            for origin in origins:
                if not origin.startswith("https://"):
                    raise ValueError(
                        f"production CORS origins must use HTTPS: {origin!r}"
                    )
        return self
