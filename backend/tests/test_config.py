from decimal import Decimal

import pytest
from goldguard.config import Settings


def test_safe_paper_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    for name in (
        "GOLDGUARD_MODE",
        "GOLDGUARD_SYMBOL",
        "GOLDGUARD_ENTRY_TIMEFRAME",
        "GOLDGUARD_REGIME_TIMEFRAME",
        "GOLDGUARD_PAPER_STARTING_BALANCE",
        "GOLDGUARD_LIVE_CAPABILITY_ENABLED",
        "GOLDGUARD_LIVE_MAX_CAPITAL",
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


def test_live_capability_requires_positive_capital(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOLDGUARD_LIVE_CAPABILITY_ENABLED", "true")
    monkeypatch.setenv("GOLDGUARD_LIVE_MAX_CAPITAL", "0")

    with pytest.raises(ValueError, match="positive live capital ceiling"):
        Settings(_env_file=None)


def test_secret_values_are_not_in_repr(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("GOLDGUARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-secret")

    settings = Settings(_env_file=None)

    assert "synthetic-secret" not in repr(settings)
