from decimal import Decimal

import pytest
from goldguard.config import Settings
from pydantic import SecretStr


def test_safe_paper_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    for name in (
        "GOLDGUARD_MODE",
        "GOLDGUARD_SYMBOL",
        "GOLDGUARD_ENTRY_TIMEFRAME",
        "GOLDGUARD_REGIME_TIMEFRAME",
        "GOLDGUARD_PAPER_STARTING_BALANCE",
        "GOLDGUARD_LIVE_CAPABILITY_ENABLED",
        "GOLDGUARD_LIVE_MAX_CAPITAL",
        "GOLDGUARD_GATEWAY_BASE_URL",
        "GOLDGUARD_GATEWAY_DATA_TOKEN",
        "GOLDGUARD_GATEWAY_MANAGEMENT_TOKEN",
        "GOLDGUARD_HERMES_BRIDGE_TOKEN",
        "GOLDGUARD_HERMES_BASE_URL",
        "GOLDGUARD_AUTOPROMOTION_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))

    settings = Settings(_env_file=None)

    assert settings.mode == "paper"
    assert settings.symbol == "PAXGUSDT"
    assert settings.entry_timeframe == "15m"
    assert settings.regime_timeframe == "1h"
    assert settings.paper_starting_balance == Decimal("100")
    assert settings.paper_risk_per_trade == Decimal("0.005")
    assert settings.live_capability_enabled is False
    assert settings.live_max_capital == Decimal("0")
    assert settings.data_dir == tmp_path

    # Configuration v2 fields
    assert settings.gateway_base_url is None
    assert settings.gateway_data_token is None
    assert settings.gateway_management_token is None
    assert settings.hermes_bridge_token is None
    assert settings.hermes_base_url is None
    assert settings.research_backtest_max_per_day == 8
    assert settings.research_backtest_seconds_per_call == 300
    assert settings.research_candles_max_per_call == 50_000
    assert settings.research_web_calls_max_per_day == 50
    assert settings.autopromotion_enabled is False


def test_live_capability_requires_positive_capital(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDGUARD_LIVE_CAPABILITY_ENABLED", "true")
    monkeypatch.setenv("GOLDGUARD_LIVE_MAX_CAPITAL", "0")

    with pytest.raises(ValueError, match="positive live capital ceiling"):
        Settings(_env_file=None)


def test_live_mode_requires_gateway_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDGUARD_MODE", "live")
    monkeypatch.setenv("GOLDGUARD_LIVE_CAPABILITY_ENABLED", "true")
    monkeypatch.setenv("GOLDGUARD_LIVE_MAX_CAPITAL", "500")
    monkeypatch.delenv("GOLDGUARD_GATEWAY_DATA_TOKEN", raising=False)
    monkeypatch.delenv("OPENCODEX_API_AUTH_TOKEN", raising=False)

    with pytest.raises(ValueError, match="gateway"):
        Settings(_env_file=None)


def test_secret_values_are_not_in_repr(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-gemini-secret")
    monkeypatch.setenv("GOLDGUARD_GATEWAY_DATA_TOKEN", "synthetic-gateway-token")
    monkeypatch.setenv("GOLDGUARD_GATEWAY_MANAGEMENT_TOKEN", "synthetic-mgmt-token")
    monkeypatch.setenv("GOLDGUARD_HERMES_BRIDGE_TOKEN", "synthetic-hermes-token")

    settings = Settings(
        _env_file=None,
        session_secret=SecretStr("synthetic-session-secret"),
    )

    repr_str = repr(settings)
    for secret in (
        "synthetic-gemini-secret",
        "synthetic-gateway-token",
        "synthetic-mgmt-token",
        "synthetic-hermes-token",
        "synthetic-session-secret",
    ):
        assert secret not in repr_str
